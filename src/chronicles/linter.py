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
from chronicles.similarity import get_similarity_engine
from chronicles.similarity.base import BaseSimilarityEngine
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
        # Skip articles that were just decayed — don't re-promote them
        if article.get("decayed"):
            continue

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


def _get_similarity_engine(config) -> BaseSimilarityEngine | None:
    """Try to instantiate the configured similarity engine; return None on failure."""
    try:
        return get_similarity_engine(config.similarity, llm_config=config.llm)
    except (ValueError, Exception) as e:
        log.warning("Similarity engine unavailable, using fallback: %s", e)
        return None


def _detect_and_merge_duplicates(
    articles: list[dict], report: LintReport, similarity_engine: BaseSimilarityEngine | None = None,
) -> list[dict]:
    """Dispatcher: use semantic dedup when engine is available, else fallback."""
    if len(articles) < 2:
        return articles
    if similarity_engine is not None:
        try:
            return _semantic_dedup(articles, report, similarity_engine)
        except Exception as e:
            log.warning("Semantic dedup failed, using fallback: %s", e)
    return _fallback_dedup(articles, report)


def _semantic_dedup(
    articles: list[dict], report: LintReport, engine: BaseSimilarityEngine,
) -> list[dict]:
    """Merge duplicate articles using semantic similarity via the engine."""
    # Build comparison texts: "title: first_paragraph"
    texts: list[str] = []
    for article in articles:
        title = article["path"].stem
        body_match = re.match(r"^---\n.*?\n---\n\s*#[^\n]*\n\n(.+?)(\n\n|$)", article["text"], re.DOTALL)
        first_para = body_match.group(1).strip() if body_match else ""
        texts.append(f"{title}: {first_para}")

    pairs = engine.batch_score(texts, engine.config.threshold)
    # Sort by score descending so highest-similarity pairs merge first
    pairs.sort(key=lambda t: t[2], reverse=True)

    merged_indices: set[int] = set()
    for i, j, score in pairs:
        if i in merged_indices or j in merged_indices:
            continue
        a, b = articles[i], articles[j]
        # Same type filter: never merge articles of different types
        if a["frontmatter"].get("type") != b["frontmatter"].get("type"):
            continue
        report.warnings.append(f"Merged duplicate: {b['path'].stem} into {a['path'].stem}")
        _merge_article(a, b)
        # Add supersedes relationship on the surviving article
        existing_rels = _parse_relationships(a["text"])
        existing_rels.append({"type": "supersedes", "target": b["path"].stem})
        _write_relationships(a, existing_rels)
        merged_indices.add(j)
        b["path"].unlink()

    return [a for idx, a in enumerate(articles) if idx not in merged_indices]


def _fallback_dedup(articles: list[dict], report: LintReport) -> list[dict]:
    """Fallback dedup using SequenceMatcher on titles and Jaccard tag overlap."""
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
            shared_tags = a_tags & b_tags
            all_tags = a_tags | b_tags
            if not shared_tags or (len(shared_tags) / len(all_tags) < 0.5):
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


VALID_RELATIONSHIP_TYPES = frozenset({
    "contradicts", "supersedes", "depends-on", "generalizes", "related-to",
})


def _parse_relationships(text: str) -> list[dict]:
    """Extract relationships list from article frontmatter text."""
    fm = _parse_frontmatter(text)
    if fm is None:
        return []
    return fm.get("relationships", []) or []


def _write_relationships(article: dict, relationships: list[dict]) -> None:
    """Write or update the relationships block in an article's frontmatter."""
    text = article["text"]
    path: Path = article["path"]

    # Remove existing relationships block if present
    text = re.sub(
        r"relationships:\n(?:  - .+\n(?:    .+\n)*)*",
        "",
        text,
    )

    if not relationships:
        path.write_text(text)
        article["text"] = text
        return

    # Build relationships YAML block
    rel_lines = ["relationships:\n"]
    for r in relationships:
        rel_lines.append(f"  - type: {r['type']}\n")
        rel_lines.append(f"    target: {r['target']}\n")
        if r.get("source"):
            rel_lines.append(f"    source: {r['source']}\n")
    rel_block = "".join(rel_lines)

    # Insert before closing ---
    text = re.sub(r"\n---\n", f"\n{rel_block}---\n", text, count=1)

    path.write_text(text)
    article["text"] = text
    article["frontmatter"]["relationships"] = relationships


def _infer_relationships(
    chronicles_dir: Path,
    articles: list[dict],
    report: LintReport,
) -> None:
    """Infer and write relationships between articles.

    - contradicts: from contested detection results
    - related-to: from tag overlap (replaces ## Related sections)
    """
    # Build tag -> article mapping for related-to inference
    article_tags: dict[str, set[str]] = {}
    for article in articles:
        fm = article["frontmatter"]
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        article_tags[article["path"].stem] = set(tags)

    for article in articles:
        name = article["path"].stem
        existing_rels = _parse_relationships(article["text"])
        new_rels = list(existing_rels)
        existing_targets = {(r["type"], r.get("target")) for r in existing_rels}

        # Add contradicts from contested status — re-parse from text
        # because _detect_contested may have updated the text without updating the dict
        current_fm = _parse_frontmatter(article["text"]) or {}
        if current_fm.get("confidence") == "contested":
            contested_by = current_fm.get("contested_by", "")
            match = re.search(r"\[\[([^\]]+)\]\]", str(contested_by))
            if match:
                target = match.group(1)
                if ("contradicts", target) not in existing_targets:
                    new_rels.append({"type": "contradicts", "target": target})

        # Add related-to from tag overlap
        my_tags = article_tags.get(name, set())
        if my_tags:
            for other_name, other_tags in article_tags.items():
                if other_name == name:
                    continue
                shared = my_tags & other_tags
                if shared and ("related-to", other_name) not in existing_targets:
                    new_rels.append({"type": "related-to", "target": other_name})

        if new_rels != existing_rels:
            _write_relationships(article, new_rels)


def _compute_last_confirmation(article: dict, chronicles_dir: Path) -> str:
    """Return ISO date string of most recent confirmation for an article.

    Checks last_confirmed frontmatter AND scans records for wikilinks to the article
    (most recent record date wins).
    """
    fm = article["frontmatter"]
    best = str(fm.get("last_confirmed", "1970-01-01"))

    records_dir = chronicles_dir / "records"
    if records_dir.exists():
        article_name = article["path"].stem
        wikilink_re = re.compile(r"\[\[" + re.escape(article_name) + r"(?:\|[^\]]+)?\]\]")
        for record_path in sorted(records_dir.glob("*.md")):
            content = record_path.read_text()
            if wikilink_re.search(content):
                # Extract date from record filename (YYYY-MM-DD prefix)
                date_match = re.match(r"(\d{4}-\d{2}-\d{2})", record_path.stem)
                if date_match and date_match.group(1) > best:
                    best = date_match.group(1)

    return best


def _has_inbound_wikilinks(article_name: str, articles: list[dict], chronicles_dir: Path) -> bool:
    """Check if any non-archived article body or record contains [[article_name]]."""
    wikilink_re = re.compile(r"\[\[" + re.escape(article_name) + r"(?:\|[^\]]+)?\]\]")

    for other in articles:
        if other["path"].stem == article_name:
            continue
        # Check body only (strip frontmatter)
        body_match = re.match(r"^---\n.*?\n---\n(.*)", other["text"], re.DOTALL)
        body = body_match.group(1) if body_match else other["text"]
        if wikilink_re.search(body):
            return True

    records_dir = chronicles_dir / "records"
    if records_dir.exists():
        for record_path in records_dir.glob("*.md"):
            if wikilink_re.search(record_path.read_text()):
                return True

    return False


def _is_depends_on_target(article_name: str, articles: list[dict]) -> bool:
    """Check if any article has a depends-on relationship targeting this article."""
    for other in articles:
        rels = other["frontmatter"].get("relationships", []) or []
        for r in rels:
            if r.get("type") == "depends-on" and r.get("target") == article_name:
                return True
    return False


def _apply_decay(
    chronicles_dir: Path,
    articles: list[dict],
    config: Any,
    report: LintReport,
) -> list[dict]:
    """Apply time-based decay: demote stale articles and archive old low-confidence ones.

    Returns the article list with archived articles removed.
    """
    today = date.fromisoformat(_today())
    archived_dir = chronicles_dir / "wiki" / "archived"
    to_remove: set[int] = set()

    for idx, article in enumerate(articles):
        fm = article["frontmatter"]
        confidence = fm.get("confidence", "low")

        # Skip contested articles
        if confidence == "contested":
            continue

        last_confirmed_str = _compute_last_confirmation(article, chronicles_dir)
        try:
            last_confirmed = date.fromisoformat(last_confirmed_str)
        except (ValueError, TypeError):
            continue

        days_stale = (today - last_confirmed).days
        path: Path = article["path"]
        name = path.stem

        if confidence == "high" and days_stale >= config.decay.high_to_medium_days:
            # Demote high -> medium
            old_text = article["text"]
            new_text = re.sub(
                r"^confidence: \S+",
                "confidence: medium",
                old_text,
                count=1,
                flags=re.MULTILINE,
            )
            path.write_text(new_text)
            article["text"] = new_text
            article["frontmatter"] = {**fm, "confidence": "medium"}
            article["decayed"] = True
            report.warnings.append(f"{name}: decayed high -> medium ({days_stale}d stale)")

        elif confidence == "medium" and days_stale >= config.decay.medium_to_low_days:
            # Demote medium -> low only if no inbound wikilinks
            if not _has_inbound_wikilinks(name, articles, chronicles_dir):
                old_text = article["text"]
                new_text = re.sub(
                    r"^confidence: \S+",
                    "confidence: low",
                    old_text,
                    count=1,
                    flags=re.MULTILINE,
                )
                path.write_text(new_text)
                article["text"] = new_text
                article["frontmatter"] = {**fm, "confidence": "low"}
                article["decayed"] = True
                report.warnings.append(f"{name}: decayed medium -> low ({days_stale}d stale)")

        elif confidence == "low" and days_stale >= config.decay.archive_after_days:
            # Archive low articles if no depends-on target and no inbound wikilinks
            if _is_depends_on_target(name, articles):
                report.warnings.append(
                    f"{name}: skipped archival (depends-on target)"
                )
                continue
            if _has_inbound_wikilinks(name, articles, chronicles_dir):
                continue

            # Move to archived
            archived_dir.mkdir(parents=True, exist_ok=True)
            old_text = article["text"]
            # Add archived metadata to frontmatter
            new_text = re.sub(
                r"\n---\n",
                f"\narchived_reason: decay\narchived_on: {_today()}\n---\n",
                old_text,
                count=1,
            )
            archived_path = archived_dir / path.name
            archived_path.write_text(new_text)
            path.unlink()
            to_remove.add(idx)
            report.warnings.append(f"{name}: archived (low, {days_stale}d stale)")

    return [a for i, a in enumerate(articles) if i not in to_remove]


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


def _add_related_sections(articles: list[dict[str, Any]]) -> int:
    """Add or update ## Related sections based on tag overlap."""
    # Build tag → article mapping
    tag_to_articles: dict[str, list[str]] = {}
    article_tags: dict[str, set[str]] = {}
    for article in articles:
        fm = article["frontmatter"]
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        name = article["path"].stem
        article_tags[name] = set(tags)
        for tag in tags:
            tag_to_articles.setdefault(tag, []).append(name)

    updated = 0
    for article in articles:
        name = article["path"].stem
        my_tags = article_tags.get(name, set())
        if not my_tags:
            continue

        # Find related articles ranked by tag overlap count
        related_scores: dict[str, int] = {}
        for tag in my_tags:
            for other in tag_to_articles.get(tag, []):
                if other != name:
                    related_scores[other] = related_scores.get(other, 0) + 1

        if not related_scores:
            continue

        # Sort by overlap count descending, then alphabetically
        related = sorted(related_scores.keys(), key=lambda n: (-related_scores[n], n))

        # Build the Related section
        related_lines = ["## Related"]
        for r in related:
            shared = article_tags.get(r, set()) & my_tags
            shared_str = ", ".join(sorted(shared))
            related_lines.append(f"- [[{r}]] ({shared_str})")
        related_section = "\n".join(related_lines) + "\n"

        # Replace existing Related section or append
        text = article["text"]
        related_re = re.compile(r"## Related\n(?:- \[\[.+\]\].*\n)*", re.MULTILINE)
        if related_re.search(text):
            text = related_re.sub(related_section, text)
        else:
            text = text.rstrip("\n") + "\n\n" + related_section

        article["path"].write_text(text)
        article["text"] = text
        updated += 1

    return updated


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

    # Generate category pages only for tags with 2+ articles (or articles + queries)
    all_tags = sorted(set(list(tag_to_articles.keys()) + list(tag_to_questions.keys())))
    for tag in all_tags:
        article_list = sorted(tag_to_articles.get(tag, []))
        question_list = sorted(tag_to_questions.get(tag, []))
        if len(article_list) + len(question_list) < 2:
            continue

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

    similarity_engine = _get_similarity_engine(config)

    articles_dir = chronicles_dir / "wiki" / "articles"
    articles, load_errors = _load_articles(articles_dir)
    report.errors.extend(load_errors)
    log.info("Loaded %d wiki article(s)", len(articles))

    articles = _detect_and_merge_duplicates(articles, report, similarity_engine)

    warnings = _check_wikilinks(articles)
    report.warnings.extend(warnings)
    if warnings:
        log.info("Found %d broken wikilink(s)", len(warnings))

    articles = _apply_decay(chronicles_dir, articles, config, report)

    promotions = _manage_confidence(articles, config.confidence.promotion_threshold)
    report.promotions.extend(promotions)
    if promotions:
        log.info("Promoted %d article(s): %s", len(promotions), ", ".join(promotions))

    _detect_contested(chronicles_dir, articles, report)
    _infer_relationships(chronicles_dir, articles, report)
    _detect_stale(chronicles_dir, articles, report)

    _regenerate_categories(chronicles_dir, articles, renderer)
    cat_dir = chronicles_dir / "wiki" / "categories"
    cat_count = len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0
    log.info("Regenerated %d category page(s)", cat_count)

    related_count = _add_related_sections(articles)
    if related_count:
        log.info("Added Related sections to %d article(s)", related_count)

    gold_count = _regenerate_gold(chronicles_dir, articles, renderer)
    report.gold_count = gold_count
    log.info("GOLD.md: %d high-confidence article(s)", gold_count)

    return report
