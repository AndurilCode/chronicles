"""CLI entry point — chronicles ingest and chronicles lint."""
from __future__ import annotations

import argparse
import functools
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chronicles.config import load_config
from chronicles.init import run_init, ensure_dir
from chronicles.cleaner import clean_transcript
from chronicles.enricher import enrich
from chronicles.extractor import Extractor
from chronicles.linter import lint
from chronicles.signals_cleaner import clean_transcript_for_signals
from chronicles.signals_extractor import SignalsExtractor
from chronicles.signals_writer import update_signals_file, load_active_signals
from chronicles.sources import detect_source, get_source, ALL_SOURCES
from chronicles.templates import TemplateRenderer
from chronicles.writer import write_record, append_chronicles_entry, write_wiki_pages

log = logging.getLogger("chronicles")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="chronicles",
        description="Automatic knowledge extraction from agent session transcripts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_p = sub.add_parser("ingest", help="Parse, clean, extract, and write records")
    ingest_p.add_argument("paths", nargs="*", type=Path, help="Transcript file paths")
    ingest_p.add_argument("--source", type=str, default=None, help="Force source type")
    ingest_p.add_argument("--since", type=str, default=None, help="Discover sessions since Nd (e.g. 7d)")
    ingest_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                          help="Path to chronicles directory")
    ingest_p.add_argument("--last", type=int, default=None, metavar="N",
                          help="Only process the N most recent discovered sessions")
    ingest_p.add_argument("--no-enrich", action="store_true",
                          help="Skip the enrich step after ingestion")

    lint_p = sub.add_parser("lint", help="Validate wiki, manage confidence, regenerate GOLD.md")
    lint_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                        help="Path to chronicles directory")

    enrich_p = sub.add_parser("enrich", help="LLM-powered wiki enrichment (category summaries)")
    enrich_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                          help="Path to chronicles directory")

    signals_p = sub.add_parser("signals", help="Extract agentic operational signals")
    signals_p.add_argument("paths", nargs="*", type=Path, help="Transcript file paths")
    signals_p.add_argument("--source", type=str, default=None, help="Force source type")
    signals_p.add_argument("--since", type=str, default=None, help="Discover sessions since Nd")
    signals_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                          help="Path to chronicles directory")
    signals_p.add_argument("--last", type=int, default=None, metavar="N",
                          help="Only process the N most recent discovered sessions")

    init_p = sub.add_parser("init", help="Scaffold chronicles directory and generate config.yaml")
    init_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                        help="Path to chronicles directory")
    init_p.add_argument("--provider", type=str, default=None,
                        choices=["claude-code", "copilot-cli", "ollama"],
                        help="LLM provider")
    init_p.add_argument("--model", type=str, default=None,
                        help="LLM model name")
    init_p.add_argument("--source", type=str, action="append", default=None,
                        dest="sources",
                        choices=["claude-code", "copilot-cli", "copilot-vscode"],
                        help="Transcript source (repeatable)")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
    )

    if args.command == "ingest":
        _run_ingest(args)
    elif args.command == "lint":
        _run_lint(args)
    elif args.command == "enrich":
        _run_enrich(args)
    elif args.command == "signals":
        _run_signals(args)
    elif args.command == "init":
        _run_init(args)


def _parse_and_clean_one(args: tuple[Path, str | None]):
    """Parse and clean a single transcript. Module-level for pickling."""
    _log = logging.getLogger("chronicles")
    path, source_override = args
    if source_override:
        source = get_source(source_override)
        _log.info("Parsing %s (forced: %s)", path.name, source.key)
    else:
        source = detect_source(path)
        _log.info("Parsing %s (detected: %s)", path.name, source.key)
    transcript = source.parse_session(path)
    _log.info("Parsed %d messages, model=%s, cwd=%s",
              len(transcript.messages), transcript.model or "unknown", transcript.cwd)
    cleaned = clean_transcript(transcript)
    total_msgs = sum(len(c) for c in cleaned.chunks)
    stripped = len(transcript.messages) - total_msgs
    _log.info("Cleaned → %d messages in %d turn(s) (filtered %d)",
              total_msgs, len(cleaned.chunks), stripped)
    return cleaned


def _parse_and_clean_all(paths: list[Path], source_override: str | None):
    """Parse and clean transcripts, using ProcessPool for multiple files."""
    if len(paths) == 1:
        yield _parse_and_clean_one((paths[0], source_override))
    else:
        with ProcessPoolExecutor() as pool:
            yield from pool.map(_parse_and_clean_one, [(p, source_override) for p in paths])


def _load_wiki_context(chronicles_dir: Path) -> list[dict]:
    """Load existing wiki article titles, tags, and types for extractor context."""
    from chronicles.frontmatter import parse_frontmatter

    articles_dir = chronicles_dir / "wiki" / "articles"
    if not articles_dir.exists():
        return []

    context = []
    for path in sorted(articles_dir.glob("*.md")):
        text = path.read_text()
        fm = parse_frontmatter(text)
        if fm is None:
            continue

        # Extract title from first heading
        title = path.stem.replace("-", " ").title()
        for line in text.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        context.append({
            "title": title,
            "type": fm.get("type", ""),
            "tags": tags,
            "path": f"wiki/articles/{path.name}",
            "confidence": fm.get("confidence", ""),
        })

    return context



def _run_ingest(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    ensure_dir(chronicles_dir)
    config = load_config(chronicles_dir)
    renderer = TemplateRenderer()
    extractor = Extractor(config.llm.for_step("extract"))

    paths: list[Path] = list(args.paths) if args.paths else []

    if args.since:
        days = int(args.since.rstrip("d"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for source in ALL_SOURCES:
            if source.key in config.sources and source.available():
                paths.extend(source.discover_sessions(since=cutoff))

    if args.last is not None and paths:
        paths = sorted(paths, key=lambda p: p.stat().st_mtime)[-args.last:]

    if not paths:
        print("No transcript files to process.", file=sys.stderr)
        sys.exit(1)

    log.info("Processing %d transcript(s)", len(paths))

    source_override = args.source
    cleaned_transcripts = list(_parse_and_clean_all(paths, source_override))

    # Load existing wiki articles for context
    wiki_context = _load_wiki_context(chronicles_dir)
    if wiki_context:
        log.info("Loaded %d existing wiki article(s) for context", len(wiki_context))

    extract_llm = config.llm.for_step("extract")
    log.info("Extracting via %s (model: %s)...", extract_llm.provider, extract_llm.model)
    with ThreadPoolExecutor(max_workers=config.llm.max_concurrent) as pool:
        extract_fn = functools.partial(extractor.extract, wiki_context=wiki_context)
        results = list(pool.map(extract_fn, cleaned_transcripts))

    # Index existing records by session_id for idempotency
    existing_records = {}
    for p in (chronicles_dir / "records").glob("*.md"):
        # Filename format: YYYY-MM-DD_SESSION-ID-SHORT_slug.md
        parts = p.stem.split("_", 2)
        if len(parts) >= 2:
            existing_records[parts[1]] = p

    written = 0
    for cleaned, result in zip(cleaned_transcripts, results):
        date_str = cleaned.metadata.timestamp_start[:10]
        source_key = cleaned.metadata.source
        session_short = cleaned.metadata.session_id[:8]

        if session_short in existing_records:
            old_record = existing_records[session_short]
            log.info("Replacing %s (resumed session)", old_record.name)
            old_record.unlink()

        log.info("Extracted: branch=%s, status=%s, %d decisions, %d problems, %d discovered, %d wiki articles",
                 result.branch, result.status,
                 len(result.decisions), len(result.problems),
                 len(result.discovered), len(result.wiki_instructions))

        record_path = write_record(chronicles_dir, result, source_key, date_str, renderer,
                                   session_id=cleaned.metadata.session_id)
        log.info("Wrote record: %s", record_path.relative_to(chronicles_dir))

        append_chronicles_entry(chronicles_dir, result, date_str, renderer)
        log.info("Updated CHRONICLES.md")

        wiki_count = write_wiki_pages(chronicles_dir, result, date_str, renderer)
        log.info("Wrote %d wiki page(s)", wiki_count)
        written += 1

    log.info("Ingested %d session(s) (%d skipped). Running lint...",
             written, len(results) - written)
    _run_lint_internal(chronicles_dir)

    # Chain enrich unless disabled
    skip_enrich = args.no_enrich or not config.enrich.enabled
    if not skip_enrich and written > 0:
        _run_enrich_internal(chronicles_dir, config)


def _run_lint(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    ensure_dir(chronicles_dir)
    _run_lint_internal(chronicles_dir)


def _run_enrich(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    ensure_dir(chronicles_dir)
    config = load_config(chronicles_dir)
    _run_enrich_internal(chronicles_dir, config)


def _run_enrich_internal(chronicles_dir: Path, config) -> None:
    log.info("Enriching wiki...")
    count = enrich(chronicles_dir, config)
    log.info("Enriched %d item(s)", count)


def _run_lint_internal(chronicles_dir: Path) -> None:
    report = lint(chronicles_dir)

    if report.errors:
        for e in report.errors:
            log.error("  %s", e)

    if report.warnings:
        for w in report.warnings:
            log.warning("  %s", w)


def _run_signals(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    ensure_dir(chronicles_dir)
    config = load_config(chronicles_dir)

    paths: list[Path] = list(args.paths) if args.paths else []

    if args.since:
        days = int(args.since.rstrip("d"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for source in ALL_SOURCES:
            if source.key in config.sources and source.available():
                paths.extend(source.discover_sessions(since=cutoff))

    if args.last is not None and paths:
        paths = sorted(paths, key=lambda p: p.stat().st_mtime)[-args.last:]

    if not paths:
        print("No transcript files to process.", file=sys.stderr)
        sys.exit(1)

    log.info("Processing %d transcript(s) for signals", len(paths))

    signals_path = chronicles_dir / "SIGNALS.md"
    existing_signals = load_active_signals(signals_path)

    extractor = SignalsExtractor(config.llm.for_step("signals"))

    for path in paths:
        source_override = args.source
        if source_override:
            source = get_source(source_override)
        else:
            source = detect_source(path)

        log.info("Parsing %s (source: %s)", path.name, source.key)
        transcript = source.parse_session(path)
        cleaned = clean_transcript_for_signals(transcript)
        total_msgs = sum(len(c) for c in cleaned.chunks)
        log.info("Cleaned → %d messages in %d chunk(s)", total_msgs, len(cleaned.chunks))

        signals_llm = config.llm.for_step("signals")
        log.info("Extracting signals via %s (model: %s)...", signals_llm.provider, signals_llm.model)
        result = extractor.extract(cleaned, existing_signals=existing_signals)

        log.info("Found %d signal(s), %d demotion(s)",
                 len(result.signals), len(result.demotions))

        update_signals_file(
            signals_path, result,
            session_id=cleaned.metadata.session_id,
            max_active=config.signals.max_active,
        )
        log.info("Updated %s", signals_path.relative_to(chronicles_dir))


def _run_init(args: argparse.Namespace) -> None:
    run_init(
        chronicles_dir=args.chronicles_dir,
        provider=args.provider,
        model=args.model,
        sources=args.sources,
    )


if __name__ == "__main__":
    main()
