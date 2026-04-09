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
from chronicles.cleaner import clean_transcript
from chronicles.enricher import enrich
from chronicles.extractors import get_extractor
from chronicles.linter import lint
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
    ingest_p.add_argument("--no-enrich", action="store_true",
                          help="Skip the enrich step after ingestion")

    lint_p = sub.add_parser("lint", help="Validate wiki, manage confidence, regenerate GOLD.md")
    lint_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                        help="Path to chronicles directory")

    enrich_p = sub.add_parser("enrich", help="LLM-powered wiki enrichment (category summaries)")
    enrich_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                          help="Path to chronicles directory")

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
    import yaml

    articles_dir = chronicles_dir / "wiki" / "articles"
    if not articles_dir.exists():
        return []

    context = []
    for path in sorted(articles_dir.glob("*.md")):
        text = path.read_text()
        import re
        match = re.match(r"^---\n(.+?)\n---", text, re.DOTALL)
        if not match:
            continue
        try:
            fm = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
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


def _ensure_chronicles_dir(chronicles_dir: Path) -> None:
    """Bootstrap chronicles directory structure if it doesn't exist."""
    for subdir in ["records", "archives", "wiki/articles", "wiki/categories", "wiki/queries"]:
        (chronicles_dir / subdir).mkdir(parents=True, exist_ok=True)

    chronicles_md = chronicles_dir / "CHRONICLES.md"
    if not chronicles_md.exists():
        from datetime import date
        chronicles_md.write_text(
            f"---\ntype: chronicles-index\nlast_updated: {date.today().isoformat()}\n"
            f"record_count: 0\n---\n\n# Chronicles\n"
        )

    gold_md = chronicles_dir / "GOLD.md"
    if not gold_md.exists():
        from datetime import date
        gold_md.write_text(
            f"---\ntype: gold-index\nlast_updated: {date.today().isoformat()}\n"
            f"promoted_count: 0\n---\n\n# Gold Notes\n\n"
            f"> High-confidence, validated knowledge for this repository. Read before acting.\n"
        )


def _run_ingest(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    _ensure_chronicles_dir(chronicles_dir)
    config = load_config(chronicles_dir)
    renderer = TemplateRenderer()
    extractor = get_extractor(config.llm)

    paths: list[Path] = list(args.paths) if args.paths else []

    if args.since:
        days = int(args.since.rstrip("d"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for source in ALL_SOURCES:
            if source.key in config.sources and source.available():
                paths.extend(source.discover_sessions(since=cutoff))

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

    log.info("Extracting via %s (model: %s)...", config.llm.provider, config.llm.model)
    with ThreadPoolExecutor(max_workers=config.llm.max_concurrent) as pool:
        extract_fn = functools.partial(extractor.extract, wiki_context=wiki_context)
        results = list(pool.map(extract_fn, cleaned_transcripts))

    # Check for already-ingested sessions (idempotency)
    existing_records = {p.stem for p in (chronicles_dir / "records").glob("*.md")}

    written = 0
    for cleaned, result in zip(cleaned_transcripts, results):
        date_str = cleaned.metadata.timestamp_start[:10]
        source_key = cleaned.metadata.source
        record_stem = f"{date_str}_{result.slug}"

        if record_stem in existing_records:
            log.info("Skipping %s (already ingested)", record_stem)
            continue

        log.info("Extracted: branch=%s, status=%s, %d decisions, %d problems, %d discovered, %d wiki articles",
                 result.branch, result.status,
                 len(result.decisions), len(result.problems),
                 len(result.discovered), len(result.wiki_instructions))

        record_path = write_record(chronicles_dir, result, source_key, date_str, renderer)
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
    _ensure_chronicles_dir(chronicles_dir)
    _run_lint_internal(chronicles_dir)


def _run_enrich(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    _ensure_chronicles_dir(chronicles_dir)
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


if __name__ == "__main__":
    main()
