"""Enricher — LLM-powered wiki improvements (category summaries, etc.)."""
from __future__ import annotations

import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from chronicles.config import ChroniclesConfig

log = logging.getLogger("chronicles")

_CATEGORY_SUMMARY_PROMPT = """\
You are writing a short summary for a wiki category page.

Category: {title}
Articles in this category:
{article_list}

Write a 2-3 sentence summary that explains:
1. What this category covers
2. How the articles relate to each other
3. Why this knowledge matters

Return ONLY the summary text — no headings, no markdown, no quotes. Just 2-3 plain sentences.
"""


def enrich(chronicles_dir: Path, config: ChroniclesConfig) -> int:
    """Run LLM-powered enrichment on the wiki. Returns count of enriched items."""
    enriched = 0
    enriched += _enrich_categories(chronicles_dir, config)
    return enriched


def _enrich_categories(chronicles_dir: Path, config: ChroniclesConfig) -> int:
    """Generate summaries for category pages using the LLM, in parallel."""
    categories_dir = chronicles_dir / "wiki" / "categories"
    if not categories_dir.exists():
        return 0

    articles_dir = chronicles_dir / "wiki" / "articles"

    # Collect categories that need enrichment
    jobs: list[dict] = []
    for cat_path in sorted(categories_dir.glob("*.md")):
        content = cat_path.read_text()

        # Skip if already has a summary
        lines = content.split("\n")
        has_summary = False
        past_title = False
        for line in lines:
            if line.startswith("# "):
                past_title = True
                continue
            if past_title and line.strip() and not line.startswith("-") and not line.startswith("#"):
                has_summary = True
                break

        if has_summary:
            continue

        # Extract title
        title = cat_path.stem.replace("-", " ").replace("_", " ").title()
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Collect article summaries
        article_summaries = _collect_article_summaries(content, articles_dir)
        if not article_summaries:
            continue

        prompt = _CATEGORY_SUMMARY_PROMPT.format(
            title=title,
            article_list="\n".join(article_summaries),
        )

        jobs.append({
            "cat_path": cat_path,
            "lines": lines,
            "prompt": prompt,
        })

    if not jobs:
        return 0

    # Run LLM calls in parallel
    max_workers = config.llm.max_concurrent

    def process_job(job: dict) -> bool:
        summary = _call_llm(job["prompt"], config)
        if not summary:
            return False

        # Insert summary after the title line
        new_lines = []
        inserted = False
        for line in job["lines"]:
            new_lines.append(line)
            if line.startswith("# ") and not inserted:
                new_lines.append("")
                new_lines.append(summary.strip())
                inserted = True

        job["cat_path"].write_text("\n".join(new_lines))
        log.info("  enriched category: %s", job["cat_path"].name)
        return True

    count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(process_job, jobs)
        count = sum(1 for r in results if r)

    return count


def _collect_article_summaries(category_content: str, articles_dir: Path) -> list[str]:
    """Extract first-line summaries from articles referenced in a category page."""
    summaries = []
    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
    for match in wikilink_re.finditer(category_content):
        article_name = match.group(1)
        article_path = articles_dir / f"{article_name}.md"
        if not article_path.exists():
            continue

        art_text = article_path.read_text()
        art_title = article_name
        art_summary = ""
        past_fm = False
        past_title = False
        for line in art_text.split("\n"):
            if line.strip() == "---":
                past_fm = not past_fm
                continue
            if past_fm and line.startswith("# "):
                art_title = line[2:].strip()
                past_title = True
                continue
            if past_title and line.strip() and not line.startswith("#"):
                art_summary = line.strip()
                break
        summaries.append(f"- {art_title}: {art_summary}")

    return summaries


def _call_llm(prompt: str, config: ChroniclesConfig) -> str:
    """Call the configured LLM provider."""
    provider = config.llm.provider
    model = config.llm.model

    if provider == "copilot-cli":
        cmd = ["copilot", "-p", prompt, "--model", model]
    elif provider == "claude-code":
        cmd = ["claude", "--print", "--model", model, prompt]
    else:
        log.warning("Unknown LLM provider for enrich: %s", provider)
        return ""

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
        if result.returncode != 0:
            log.warning("LLM call failed: %s", result.stderr[:200])
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.warning("LLM call timed out")
        return ""
