"""Tests for the writer — records, CHRONICLES.md, wiki pages."""
from pathlib import Path
from chronicles.models import ExtractionResult
from chronicles.templates import TemplateRenderer
from chronicles.writer import write_record, append_chronicles_entry, write_wiki_pages

def _make_result() -> ExtractionResult:
    return ExtractionResult(
        branch="feat/oauth",
        status="complete",
        tags=["oauth", "auth"],
        duration="30min",
        files_changed=["src/auth.py"],
        objective="Add OAuth",
        outcome="OAuth works",
        decisions=[{"description": "Use refresh tokens", "rationale": "more secure"}],
        problems=[],
        discovered=[{"type": "convention", "description": "Use _conn suffix"}],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[
            {
                "action": "create",
                "path": "wiki/articles/conn-suffix.md",
                "data": {
                    "title": "Connection Suffix",
                    "type": "convention",
                    "confidence": "low",
                    "tags": ["naming"],
                    "body": "Use _conn suffix.",
                    "evidence": ["Found in oauth session"],
                    "implications": ["Must follow"],
                },
            }
        ],
    )

def test_write_record(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    path = write_record(chronicles_dir, result, "claude-code", "2026-04-09", renderer)
    assert path.exists()
    assert path.name == "2026-04-09_feat-oauth.md"
    content = path.read_text()
    assert "feat/oauth" in content
    assert "Add OAuth" in content

def test_append_chronicles_entry(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    append_chronicles_entry(chronicles_dir, result, "2026-04-09", renderer)
    content = (chronicles_dir / "CHRONICLES.md").read_text()
    assert "feat-oauth" in content
    assert "Add OAuth" in content

def test_write_wiki_pages(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    write_wiki_pages(chronicles_dir, result, "2026-04-09", renderer)
    article = chronicles_dir / "wiki" / "articles" / "conn-suffix.md"
    assert article.exists()
    content = article.read_text()
    assert "Connection Suffix" in content
    assert "confidence: low" in content

def test_write_wiki_pages_with_relationships(chronicles_dir):
    """Relationships from wiki_instructions are passed to template."""
    from chronicles.models import ExtractionResult
    from chronicles.templates import TemplateRenderer
    from chronicles.writer import write_wiki_pages

    renderer = TemplateRenderer()
    result = ExtractionResult(
        branch="feat/test",
        status="complete",
        tags=["test"],
        duration="10min",
        files_changed=[],
        objective="Test",
        outcome="Tested",
        decisions=[],
        problems=[],
        discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[{
            "action": "create",
            "path": "wiki/articles/new-pattern.md",
            "data": {
                "title": "New Pattern",
                "type": "pattern",
                "confidence": "medium",
                "tags": ["test"],
                "body": "A new pattern.",
                "evidence": ["evidence"],
                "implications": ["implication"],
            },
            "relationships": [
                {"type": "supersedes", "target": "old-pattern"},
            ],
        }],
    )
    count = write_wiki_pages(chronicles_dir, result, "2026-04-09", renderer)
    assert count == 1
    content = (chronicles_dir / "wiki" / "articles" / "new-pattern.md").read_text()
    assert "relationships:" in content
    assert "type: supersedes" in content
    assert "target: old-pattern" in content


def test_write_record_updates_frontmatter_count(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    append_chronicles_entry(chronicles_dir, result, "2026-04-09", renderer)
    content = (chronicles_dir / "CHRONICLES.md").read_text()
    assert "record_count: 1" in content
