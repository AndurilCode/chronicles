"""Writer — produces records, CHRONICLES.md entries, and wiki pages."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from chronicles.models import ExtractionResult
from chronicles.templates import TemplateRenderer

log = logging.getLogger("chronicles")

STATUS_ICONS: dict[str, str] = {
    "complete": "✅",
    "partial": "🟡",
    "failed": "❌",
    "exploratory": "🔍",
}

STATUS_LABELS: dict[str, str] = {
    "complete": "Complete",
    "partial": "Partial",
    "failed": "Failed",
    "exploratory": "Exploratory",
}


def write_record(
    chronicles_dir: Path,
    result: ExtractionResult,
    source: str,
    date: str,
    renderer: TemplateRenderer,
    session_id: str = "",
) -> Path:
    """Render and write a session record to records/YYYY-MM-DD_SESSION-SHORT_slug.md."""
    session_short = session_id[:8] if session_id else "unknown"
    filename = f"{date}_{session_short}_{result.slug}.md"
    out_path = chronicles_dir / "records" / filename

    content = renderer.render(
        "record",
        {
            "date": date,
            "branch": result.branch,
            "status": result.status,
            "tags": result.tags,
            "source": source,
            "duration": result.duration,
            "files_changed": result.files_changed,
            "objective": result.objective,
            "outcome": result.outcome,
            "decisions": result.decisions,
            "problems": result.problems,
            "discovered": result.discovered,
            "continuity": result.continuity,
        },
    )
    out_path.write_text(content)
    return out_path


def append_chronicles_entry(
    chronicles_dir: Path,
    result: ExtractionResult,
    date: str,
    renderer: TemplateRenderer,
) -> None:
    """Render a chronicles_entry and append it to CHRONICLES.md, updating frontmatter."""
    chronicles_path = chronicles_dir / "CHRONICLES.md"
    existing = chronicles_path.read_text()

    tags_as_hashtags = " ".join(f"#{t}" for t in result.tags)
    entry = renderer.render(
        "chronicles_entry",
        {
            "date": date,
            "slug": result.slug,
            "branch": result.branch,
            "status_icon": STATUS_ICONS.get(result.status, ""),
            "status_label": STATUS_LABELS.get(result.status, result.status),
            "objective": result.objective,
            "outcome": result.outcome,
            "tags_as_hashtags": tags_as_hashtags,
        },
    )

    # Update frontmatter: record_count and last_updated
    updated = _update_frontmatter(existing, date)

    # Append the entry
    updated = updated.rstrip("\n") + "\n\n" + entry
    chronicles_path.write_text(updated)


def write_wiki_pages(
    chronicles_dir: Path,
    result: ExtractionResult,
    date: str,
    renderer: TemplateRenderer,
) -> int:
    """Process wiki_instructions from ExtractionResult and write wiki pages.

    Returns the number of pages written.
    """
    record_ref = f"{date}_{result.slug}"
    count = 0
    for instruction in result.wiki_instructions:
        action = instruction.get("action", "create")
        rel_path = instruction.get("path", "")
        data = instruction.get("data", {})

        if not rel_path or not rel_path.endswith(".md"):
            log.warning("Skipping wiki instruction with invalid path: %r", rel_path)
            continue

        out_path = chronicles_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        template_name = _template_name_from_path(rel_path)

        # Inject record reference into sources if not already present
        if not data.get("sources"):
            data["sources"] = [record_ref]
        elif record_ref not in data["sources"]:
            data["sources"].append(record_ref)

        # Cap confidence at medium — only the linter promotes to high
        if data.get("confidence") == "high":
            data["confidence"] = "medium"

        # Build template context with defaults for required fields
        relationships = instruction.get("relationships", [])
        context = _build_wiki_context(data, date, relationships=relationships)

        if action in ("create", "update"):
            # Preserve sources from existing article if overwriting
            if out_path.exists():
                existing_text = out_path.read_text()
                existing_fm = _parse_frontmatter(existing_text)
                if existing_fm:
                    existing_sources = existing_fm.get("sources", [])
                    for s in existing_sources:
                        s_norm = _normalize_source_ref(s)
                        if s_norm and s_norm not in context["sources"]:
                            context["sources"].append(s_norm)
            content = renderer.render(template_name, context)
            out_path.write_text(content)
            log.info("  wiki: %s (%s, confidence=%s)",
                     rel_path, data.get("type", "?"), data.get("confidence", "?"))
            count += 1
        elif action == "resolve":
            if not out_path.exists():
                log.warning("Cannot resolve %s — article does not exist", rel_path)
                continue
            existing = out_path.read_text()
            record_ref_link = f'"[[{record_ref}]]"'
            supports = data.get("supports", "original")
            evidence_text = data.get("evidence", "")

            evidence_entry = (
                f"  - record: {record_ref_link}\n"
                f"    supports: {supports}\n"
            )
            if evidence_text:
                evidence_entry += f"    evidence: {evidence_text}\n"

            if "resolution_evidence:" in existing:
                existing = existing.replace(
                    "resolution_evidence:\n",
                    "resolution_evidence:\n" + evidence_entry,
                    1,
                )
            else:
                existing = re.sub(
                    r"\n---\n",
                    f"\nresolution_evidence:\n{evidence_entry}---\n",
                    existing,
                    count=1,
                )
            out_path.write_text(existing)
            log.info("  wiki: %s (resolve evidence, supports=%s)", rel_path, supports)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict | None:
    """Extract and parse YAML frontmatter from markdown text."""
    import yaml
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None


def _normalize_source_ref(source) -> str:
    """Normalize a source reference to a plain string."""
    if isinstance(source, list):
        while isinstance(source, list) and source:
            source = source[0]
    s = str(source).strip('"')
    match = re.search(r"\[\[([^\]]+)\]\]", s)
    if match:
        return match.group(1)
    return s


def _update_frontmatter(text: str, date: str) -> str:
    """Increment record_count and set last_updated in YAML frontmatter."""
    # Match the frontmatter block
    match = re.match(r"^(---\n)(.*?)(---\n)", text, re.DOTALL)
    if not match:
        return text

    prefix, fm, suffix_delim = match.group(1), match.group(2), match.group(3)
    rest = text[match.end():]

    # Update record_count
    count_match = re.search(r"record_count:\s*(\d+)", fm)
    if count_match:
        old_count = int(count_match.group(1))
        fm = fm[: count_match.start()] + f"record_count: {old_count + 1}" + fm[count_match.end():]
    else:
        fm = fm.rstrip("\n") + "\nrecord_count: 1\n"

    # Update last_updated
    date_match = re.search(r"last_updated:.*", fm)
    if date_match:
        fm = fm[: date_match.start()] + f"last_updated: {date}" + fm[date_match.end():]
    else:
        fm = fm.rstrip("\n") + f"\nlast_updated: {date}\n"

    return prefix + fm + suffix_delim + rest


def _template_name_from_path(rel_path: str) -> str:
    """Determine Jinja2 template name from the wiki file path."""
    parts = Path(rel_path).parts
    # e.g. wiki/articles/foo.md -> wiki_article
    #      wiki/categories/foo.md -> wiki_category
    #      wiki/queries/foo.md -> wiki_query
    if len(parts) >= 2:
        folder = parts[-2]  # articles, categories, queries
        if folder == "categories":
            folder_singular = "category"
        elif folder == "queries":
            folder_singular = "query"
        else:
            folder_singular = folder.rstrip("s")
        return f"wiki_{folder_singular}"
    return "wiki_article"


def _build_wiki_context(data: dict, date: str, relationships: list | None = None) -> dict:
    """Build a complete context dict for a wiki template, filling in defaults."""
    return {
        "title": data.get("title", ""),
        "type": data.get("type", "article"),
        "confidence": data.get("confidence", "low"),
        "tags": data.get("tags", []),
        "body": data.get("body", ""),
        "evidence": data.get("evidence", []),
        "implications": data.get("implications", []),
        "sources": data.get("sources", []),
        "first_seen": data.get("first_seen", date),
        "last_confirmed": data.get("last_confirmed", date),
        # relationship fields
        "relationships": relationships or [],
        # category fields
        "articles": data.get("articles", []),
        "open_questions": data.get("open_questions", []),
        # query fields
        "asked_by": data.get("asked_by", ""),
        "date": data.get("date", date),
        "answered_from": data.get("answered_from", []),
        "question": data.get("question", data.get("title", "")),
        "answer": data.get("answer", data.get("body", "")),
    }
