"""Linter — validates wiki structure, manages confidence lifecycle, regenerates GOLD.md."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from chronicles.archiver import rotate_records
from chronicles.config import load_config
from chronicles.templates import TemplateRenderer

log = logging.getLogger("chronicles")

# Maps article types to GOLD.md section names
TYPE_TO_SECTION: dict[str, str] = {
    "convention": "Conventions",
    "pattern": "Patterns",
    "decision": "Decisions",
    "constraint": "Constraints",
    "preference": "Preferences",
    "tool": "Tools",
    "workflow": "Workflows",
    "concept": "Concepts",
}

_DEFAULT_SECTION = "Other"


@dataclass
class LintReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)
    gold_count: int = 0


def _today() -> str:
    """Return current date as ISO string."""
    return date.today().isoformat()


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Extract and parse YAML frontmatter from markdown text. Returns None if absent."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None


def _load_articles(articles_dir: Path) -> tuple[list[dict], list[str]]:
    """Load wiki articles and validate frontmatter.

    Returns (articles, errors) where each article dict contains path, frontmatter, and body.
    """
    articles: list[dict] = []
    errors: list[str] = []

    if not articles_dir.exists():
        return articles, errors

    required_fields = ["type", "confidence"]

    for path in sorted(articles_dir.glob("*.md")):
        text = path.read_text()
        fm = _parse_frontmatter(text)
        if fm is None:
            errors.append(f"{path.name}: missing or invalid frontmatter")
            continue

        for field_name in required_fields:
            if not fm.get(field_name):
                errors.append(f"{path.name}: missing required field '{field_name}'")

        sources = fm.get("sources")
        if not sources or (isinstance(sources, list) and len(sources) == 0):
            errors.append(f"{path.name}: empty 'sources' — no record references this article")

        articles.append({"path": path, "frontmatter": fm, "text": text})

    return articles, errors


def _check_wikilinks(articles: list[dict]) -> list[str]:
    """Check for broken [[wikilinks]] in article bodies.

    Returns list of warnings for links pointing to non-existent articles.
    """
    # Build set of known article names (stem without .md)
    known = {a["path"].stem for a in articles}
    warnings: list[str] = []

    for article in articles:
        text = article["text"]
        # Strip frontmatter before scanning body
        body_match = re.match(r"^---\n.*?\n---\n(.*)", text, re.DOTALL)
        body = body_match.group(1) if body_match else text

        # Find all [[wikilinks]] in the body
        links = re.findall(r"\[\[([^\]]+)\]\]", body)
        for link in links:
            # Wikilinks in body (not inside sources in frontmatter) should resolve
            if link not in known:
                warnings.append(
                    f"{article['path'].name}: broken wikilink [[{link}]]"
                )

    return warnings


def _manage_confidence(
    articles: list[dict],
    promotion_threshold: int,
) -> list[str]:
    """Promote article confidence levels based on source count.

    - low -> medium: 2+ sources
    - medium -> high: promotion_threshold+ sources

    Returns list of promotion messages. Mutates article frontmatter and writes files.
    """
    promotions: list[str] = []

    for article in articles:
        fm = article["frontmatter"]
        path: Path = article["path"]
        confidence = fm.get("confidence", "low")
        sources = fm.get("sources", []) or []
        source_count = len(sources)

        new_confidence = confidence

        if confidence == "low" and source_count >= 2:
            new_confidence = "medium"
        elif confidence == "medium" and source_count >= promotion_threshold:
            new_confidence = "high"

        if new_confidence != confidence:
            # Update the file text — replace confidence line in frontmatter
            old_text = article["text"]
            new_text = re.sub(
                r"^confidence: \S+",
                f"confidence: {new_confidence}",
                old_text,
                count=1,
                flags=re.MULTILINE,
            )
            path.write_text(new_text)
            article["text"] = new_text
            article["frontmatter"] = {**fm, "confidence": new_confidence}
            promotions.append(
                f"{path.stem}: {confidence} -> {new_confidence} ({source_count} sources)"
            )

    return promotions


def _detect_and_merge_duplicates(articles: list[dict], report: LintReport) -> list[dict]:
    if len(articles) < 2:
        return articles
    merged_indices: set[int] = set()
    for i, a in enumerate(articles):
        if i in merged_indices:
            continue
        for j in range(i + 1, len(articles)):
            if j in merged_indices:
                continue
            b = articles[j]
            if a["frontmatter"].get("type") != b["frontmatter"].get("type"):
                continue
            ratio = SequenceMatcher(None, a["path"].stem, b["path"].stem).ratio()
            if ratio < 0.6:
                continue
            a_tags = set(a["frontmatter"].get("tags", []))
            b_tags = set(b["frontmatter"].get("tags", []))
            if not a_tags & b_tags:
                continue
            report.warnings.append(f"Merged duplicate: {b['path'].stem} into {a['path'].stem}")
            _merge_article(a, b)
            merged_indices.add(j)
            b["path"].unlink()
    return [a for i, a in enumerate(articles) if i not in merged_indices]


def _merge_article(target: dict, source: dict) -> None:
    target_fm = target["frontmatter"]
    source_fm = source["frontmatter"]
    existing_sources = target_fm.get("sources", [])
    new_sources = source_fm.get("sources", [])
    all_sources = list(dict.fromkeys(existing_sources + new_sources))
    existing_tags = set(target_fm.get("tags", []))
    new_tags = set(source_fm.get("tags", []))
    all_tags = sorted(existing_tags | new_tags)
    content = target["text"]
    content = re.sub(
        r"sources:\n(  - .+\n)+",
        "sources:\n" + "".join(f'  - "{s}"\n' if "[[" not in s else f"  - {s}\n" for s in all_sources),
        content,
    )
    content = re.sub(r"tags: \[.+\]", f"tags: {all_tags}", content)
    target["path"].write_text(content)
    target["text"] = content
    target["frontmatter"]["sources"] = all_sources
    target["frontmatter"]["tags"] = all_tags


def _detect_contested(chronicles_dir: Path, articles: list[dict], report: LintReport) -> None:
    records_dir = chronicles_dir / "records"
    if not records_dir.exists():
        return
    for record_path in records_dir.glob("*.md"):
        content = record_path.read_text()
        contradicts_re = re.compile(r"contradicts?\s+\[\[([^\]]+)\]\]", re.IGNORECASE)
        for match in contradicts_re.finditer(content):
            target_name = match.group(1).strip()
            for article in articles:
                if article["path"].stem == target_name and article["frontmatter"].get("confidence") == "high":
                    art_content = article["text"]
                    art_content = art_content.replace(
                        "confidence: high",
                        'confidence: contested\ncontested_by: "[[' + record_path.stem + ']]"\nprevious_confidence: high',
                        1,
                    )
                    article["path"].write_text(art_content)
                    article["text"] = art_content
                    article["frontmatter"]["confidence"] = "contested"
                    report.warnings.append(f"Contested: {article['path'].stem} (by {record_path.stem})")


def _detect_stale(chronicles_dir: Path, articles: list[dict], report: LintReport) -> None:
    records_dir = chronicles_dir / "records"
    if not records_dir.exists():
        return
    all_references: set[str] = set()
    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
    for record_path in records_dir.glob("*.md"):
        content = record_path.read_text()
        for match in wikilink_re.finditer(content):
            all_references.add(match.group(1).strip())
    for article in articles:
        if article["frontmatter"].get("confidence") != "high":
            continue
        sources = article["frontmatter"].get("sources", [])
        has_recent = False
        for source in sources:
            source_match = re.search(r"\[\[([^\]]+)\]\]", str(source))
            if source_match:
                stem = source_match.group(1)
                if (records_dir / f"{stem}.md").exists():
                    has_recent = True
                    break
        if not has_recent and article["path"].stem not in all_references:
            report.warnings.append(
                f"Stale high-confidence article: {article['path'].stem} (no active records reference it)"
            )


def _regenerate_categories(
    chronicles_dir: Path,
    articles: list[dict[str, Any]],
    renderer: TemplateRenderer,
) -> None:
    """Rebuild wiki/categories/ index pages by grouping articles by tag."""
    categories_dir = chronicles_dir / "wiki" / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)

    # Group articles by tag
    tag_to_articles: dict[str, list[str]] = {}
    tag_to_questions: dict[str, list[str]] = {}
    for article in articles:
        fm = article["frontmatter"]
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        title = article["path"].stem
        for tag in tags:
            tag_to_articles.setdefault(tag, []).append(title)

    # Also scan queries
    queries_dir = chronicles_dir / "wiki" / "queries"
    if queries_dir.exists():
        for query_path in queries_dir.glob("*.md"):
            content = query_path.read_text()
            fm_match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
            if fm_match:
                try:
                    fm = yaml.safe_load(fm_match.group(1))
                    tags = fm.get("tags", [])
                    if isinstance(tags, str):
                        tags = [tags]
                    for tag in tags:
                        tag_to_questions.setdefault(tag, []).append(query_path.stem)
                except yaml.YAMLError:
                    pass

    # Remove old category files
    for old in categories_dir.glob("*.md"):
        old.unlink()

    # Generate one category page per tag
    all_tags = sorted(set(list(tag_to_articles.keys()) + list(tag_to_questions.keys())))
    for tag in all_tags:
        article_list = sorted(tag_to_articles.get(tag, []))
        question_list = sorted(tag_to_questions.get(tag, []))

        # Title: capitalize and replace hyphens
        title = tag.replace("-", " ").replace("_", " ").title()

        data = {
            "tags": [tag],
            "title": title,
            "articles": article_list,
            "open_questions": question_list,
        }
        cat_path = categories_dir / f"{tag}.md"
        cat_path.write_text(renderer.render("wiki_category", data))


def _regenerate_gold(
    chronicles_dir: Path,
    articles: list[dict],
    renderer: TemplateRenderer,
) -> int:
    """Rebuild GOLD.md from high-confidence articles.

    Returns count of promoted (high-confidence) articles written to GOLD.md.
    """
    high_articles = [
        a for a in articles if a["frontmatter"].get("confidence") == "high"
    ]

    # Group by article type -> section name
    groups_dict: dict[str, list[dict]] = {}
    for article in high_articles:
        article_type = article["frontmatter"].get("type", "")
        section = TYPE_TO_SECTION.get(article_type, _DEFAULT_SECTION)
        groups_dict.setdefault(section, []).append(article)

    # Build list of (section_name, article_data_list) sorted by section name
    groups = []
    for section_name, section_articles in sorted(groups_dict.items()):
        article_data = []
        for a in section_articles:
            fm = a["frontmatter"]
            # Extract first line of body as summary (after the heading)
            body_match = re.match(r"^---\n.*?\n---\n\s*#[^\n]*\n\n(.+?)(\n|$)", a["text"], re.DOTALL)
            summary = ""
            if body_match:
                summary = body_match.group(1).strip().split("\n")[0]
            article_data.append({
                "title": a["path"].stem,
                "summary": summary,
                "type": fm.get("type", ""),
                "confidence": fm.get("confidence", "high"),
            })
        groups.append((section_name, article_data))

    gold_path = chronicles_dir / "GOLD.md"
    content = renderer.render(
        "gold",
        {
            "date": _today(),
            "count": len(high_articles),
            "groups": groups,
        },
    )
    gold_path.write_text(content)
    return len(high_articles)


def lint(chronicles_dir: Path) -> LintReport:
    """Main linter function.

    Loads config, loads articles, checks wikilinks, manages confidence, regenerates GOLD.md.
    """
    report = LintReport()

    config = load_config(chronicles_dir)

    # Archive old records before validation
    moved = rotate_records(chronicles_dir, config.archive.after_days)
    if moved:
        log.info("Archived %d old record(s)", len(moved))
        report.warnings.append(f"Archived {len(moved)} old record(s)")

    renderer = TemplateRenderer()

    articles_dir = chronicles_dir / "wiki" / "articles"
    articles, load_errors = _load_articles(articles_dir)
    report.errors.extend(load_errors)
    log.info("Loaded %d wiki article(s)", len(articles))

    articles = _detect_and_merge_duplicates(articles, report)

    warnings = _check_wikilinks(articles)
    report.warnings.extend(warnings)
    if warnings:
        log.info("Found %d broken wikilink(s)", len(warnings))

    promotions = _manage_confidence(articles, config.confidence.promotion_threshold)
    report.promotions.extend(promotions)
    if promotions:
        log.info("Promoted %d article(s): %s", len(promotions), ", ".join(promotions))

    _detect_contested(chronicles_dir, articles, report)
    _detect_stale(chronicles_dir, articles, report)

    _regenerate_categories(chronicles_dir, articles, renderer)
    cat_dir = chronicles_dir / "wiki" / "categories"
    cat_count = len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0
    log.info("Regenerated %d category page(s)", cat_count)

    gold_count = _regenerate_gold(chronicles_dir, articles, renderer)
    report.gold_count = gold_count
    log.info("GOLD.md: %d high-confidence article(s)", gold_count)

    return report
