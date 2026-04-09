"""Writer — produces records, CHRONICLES.md entries, and wiki pages."""
from __future__ import annotations

import re
from pathlib import Path

from chronicles.models import ExtractionResult
from chronicles.templates import TemplateRenderer

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
) -> Path:
    """Render and write a session record to records/YYYY-MM-DD_slug.md."""
    filename = f"{date}_{result.slug}.md"
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
) -> None:
    """Process wiki_instructions from ExtractionResult and write wiki pages."""
    for instruction in result.wiki_instructions:
        action = instruction.get("action", "create")
        rel_path = instruction.get("path", "")
        data = instruction.get("data", {})

        out_path = chronicles_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        template_name = _template_name_from_path(rel_path)

        # Build template context with defaults for required fields
        context = _build_wiki_context(data, date)

        if action in ("create", "update"):
            content = renderer.render(template_name, context)
            out_path.write_text(content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        folder_singular = folder.rstrip("s")  # articles -> article, queries -> query
        if folder == "categories":
            folder_singular = "category"
        elif folder == "queries":
            folder_singular = "query"
        elif folder == "articles":
            folder_singular = "article"
        return f"wiki_{folder_singular}"
    return "wiki_article"


def _build_wiki_context(data: dict, date: str) -> dict:
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
