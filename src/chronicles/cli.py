"""CLI entry point — chronicles ingest and chronicles lint."""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chronicles.config import load_config
from chronicles.cleaner import clean_transcript
from chronicles.extractors import get_extractor
from chronicles.linter import lint
from chronicles.sources import detect_source, get_source, ALL_SOURCES
from chronicles.templates import TemplateRenderer
from chronicles.writer import write_record, append_chronicles_entry, write_wiki_pages


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

    lint_p = sub.add_parser("lint", help="Validate wiki, manage confidence, regenerate GOLD.md")
    lint_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                        help="Path to chronicles directory")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        _run_ingest(args)
    elif args.command == "lint":
        _run_lint(args)


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

    def parse_and_clean(path: Path):
        if args.source:
            source = get_source(args.source)
        else:
            source = detect_source(path)
        transcript = source.parse_session(path)
        cleaned = clean_transcript(transcript)
        return cleaned

    with ProcessPoolExecutor() as pool:
        cleaned_transcripts = list(pool.map(parse_and_clean, paths))

    with ThreadPoolExecutor(max_workers=config.llm.max_concurrent) as pool:
        results = list(pool.map(extractor.extract, cleaned_transcripts))

    for cleaned, result in zip(cleaned_transcripts, results):
        date_str = cleaned.metadata.timestamp_start[:10]
        source_key = cleaned.metadata.source

        write_record(chronicles_dir, result, source_key, date_str, renderer)
        append_chronicles_entry(chronicles_dir, result, date_str, renderer)
        write_wiki_pages(chronicles_dir, result, date_str, renderer)

    print(f"Ingested {len(results)} session(s).")
    _run_lint_internal(chronicles_dir)


def _run_lint(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    _ensure_chronicles_dir(chronicles_dir)
    _run_lint_internal(chronicles_dir)


def _run_lint_internal(chronicles_dir: Path) -> None:
    report = lint(chronicles_dir)

    if report.errors:
        print(f"\nErrors ({len(report.errors)}):")
        for e in report.errors:
            print(f"  - {e}")

    if report.warnings:
        print(f"\nWarnings ({len(report.warnings)}):")
        for w in report.warnings:
            print(f"  - {w}")

    if report.promotions:
        print(f"\nPromotions ({len(report.promotions)}):")
        for p in report.promotions:
            print(f"  - {p}")

    print(f"\nGOLD.md: {report.gold_count} high-confidence articles.")


if __name__ == "__main__":
    main()
