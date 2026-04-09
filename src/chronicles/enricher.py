"""Enricher — LLM-powered wiki improvements (category summaries, etc.)."""
from __future__ import annotations

import logging
import re
import subprocess
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
    """Generate summaries for category pages using the LLM."""
    categories_dir = chronicles_dir / "wiki" / "categories"
    if not categories_dir.exists():
        return 0

    articles_dir = chronicles_dir / "wiki" / "articles"
    count = 0

    for cat_path in sorted(categories_dir.glob("*.md")):
        content = cat_path.read_text()

        # Skip if already has a summary (non-empty line after the title that isn't a list item)
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

        # Collect article summaries (first non-heading line from each)
        article_summaries = []
        wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
        for match in wikilink_re.finditer(content):
            article_name = match.group(1)
            article_path = articles_dir / f"{article_name}.md"
            if article_path.exists():
                art_text = article_path.read_text()
                # Get title and first body line
                art_title = article_name
                art_summary = ""
                past_fm = False
                past_art_title = False
                for art_line in art_text.split("\n"):
                    if art_line.strip() == "---":
                        past_fm = not past_fm
                        continue
                    if past_fm and art_line.startswith("# "):
                        art_title = art_line[2:].strip()
                        past_art_title = True
                        continue
                    if past_art_title and art_line.strip() and not art_line.startswith("#"):
                        art_summary = art_line.strip()
                        break
                article_summaries.append(f"- {art_title}: {art_summary}")

        if not article_summaries:
            continue

        # Generate summary via LLM
        prompt = _CATEGORY_SUMMARY_PROMPT.format(
            title=title,
            article_list="\n".join(article_summaries),
        )

        summary = _call_llm(prompt, config)
        if not summary:
            continue

        # Insert summary after the title line
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if line.startswith("# ") and not inserted:
                new_lines.append("")
                new_lines.append(summary.strip())
                inserted = True

        cat_path.write_text("\n".join(new_lines))
        log.info("  enriched category: %s", cat_path.name)
        count += 1

    return count


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
