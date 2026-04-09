"""Tests for template rendering."""
from pathlib import Path

from chronicles.templates import TemplateRenderer


def test_render_record(tmp_path):
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "branch": "feat/oauth",
        "status": "complete",
        "tags": ["oauth", "auth"],
        "source": "claude-code",
        "duration": "30min",
        "files_changed": ["src/auth.py"],
        "objective": "Add OAuth",
        "outcome": "OAuth works",
        "decisions": [
            {"description": "Use refresh tokens", "rationale": "more secure"}
        ],
        "problems": [
            {"description": "403 on scope", "root_cause": "wrong delimiter", "dead_end": False}
        ],
        "discovered": [
            {"type": "convention", "description": "Use _connection suffix"}
        ],
        "continuity": {
            "unfinished": ["Error UX"],
            "open_questions": ["Auto-disconnect?"],
            "next": ["Add backoff"],
        },
    }
    result = renderer.render("record", data)
    assert "date: 2026-04-09" in result
    assert "feat/oauth" in result
    assert "Add OAuth" in result
    assert "Use refresh tokens" in result
    assert "[convention]" in result
    assert "Error UX" in result


def test_render_wiki_article():
    renderer = TemplateRenderer()
    data = {
        "type": "convention",
        "confidence": "low",
        "sources": ["2026-04-09_feat-oauth"],
        "first_seen": "2026-04-09",
        "last_confirmed": "2026-04-09",
        "tags": ["naming"],
        "title": "Connection Suffix Pattern",
        "body": "All configs use _connection suffix.",
        "evidence": ["Found in oauth session"],
        "implications": ["Must follow pattern"],
    }
    result = renderer.render("wiki_article", data)
    assert "type: convention" in result
    assert "confidence: low" in result
    assert "Connection Suffix Pattern" in result
    assert "[[2026-04-09_feat-oauth]]" in result


def test_render_chronicles_entry():
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "slug": "feat-oauth",
        "branch": "feat/oauth",
        "status_icon": "✅",
        "status_label": "Complete",
        "objective": "Add OAuth",
        "outcome": "OAuth works",
        "tags_as_hashtags": "#oauth #auth",
    }
    result = renderer.render("chronicles_entry", data)
    assert "[[2026-04-09_feat-oauth|feat/oauth]]" in result
    assert "✅" in result
    assert "#oauth #auth" in result


def test_render_gold():
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "count": 2,
        "groups": [
            ("Conventions", [
                {"title": "Suffix Pattern", "summary": "use _connection suffix"},
            ]),
            ("Workarounds", [
                {"title": "Retry Backoff", "summary": "hardcoded 60s"},
            ]),
        ],
    }
    result = renderer.render("gold", data)
    assert "promoted_count: 2" in result
    assert "## Conventions" in result
    assert "[[Suffix Pattern]]" in result
    assert "## Workarounds" in result


def test_render_wiki_query():
    renderer = TemplateRenderer()
    data = {
        "asked_by": "human",
        "date": "2026-04-09",
        "answered_from": ["Article A", "Article B"],
        "tags": ["onboarding"],
        "question": "How do I add a connection?",
        "answer": "Follow the suffix pattern.",
    }
    result = renderer.render("wiki_query", data)
    assert "type: query" in result
    assert "[[Article A]]" in result
    assert "How do I add a connection?" in result


def test_render_wiki_category():
    renderer = TemplateRenderer()
    data = {
        "tags": ["mcp"],
        "title": "MCP Conventions",
        "articles": ["Suffix Pattern", "Token Storage"],
        "open_questions": ["Auto-disconnect?"],
    }
    result = renderer.render("wiki_category", data)
    assert "type: category" in result
    assert "[[Suffix Pattern]]" in result
    assert "## Open Questions" in result


def test_render_wiki_article_with_relationships():
    renderer = TemplateRenderer()
    data = {
        "type": "convention",
        "confidence": "medium",
        "sources": ["2026-04-09_feat-oauth"],
        "first_seen": "2026-04-09",
        "last_confirmed": "2026-04-09",
        "tags": ["naming"],
        "title": "New Convention",
        "body": "This replaces the old convention.",
        "evidence": ["Found in session"],
        "implications": ["Follow new pattern"],
        "relationships": [
            {"type": "supersedes", "target": "old-convention", "source": "[[2026-04-09_feat-oauth]]"},
            {"type": "depends-on", "target": "base-pattern"},
        ],
    }
    result = renderer.render("wiki_article", data)
    assert "relationships:" in result
    assert "type: supersedes" in result
    assert "target: old-convention" in result
    assert "type: depends-on" in result
    assert "target: base-pattern" in result
    assert "source: [[2026-04-09_feat-oauth]]" in result


def test_render_wiki_article_without_relationships():
    """Relationships block is omitted when empty."""
    renderer = TemplateRenderer()
    data = {
        "type": "convention",
        "confidence": "low",
        "sources": ["2026-04-09_test"],
        "first_seen": "2026-04-09",
        "last_confirmed": "2026-04-09",
        "tags": ["test"],
        "title": "No Relationships",
        "body": "Simple article.",
        "evidence": ["evidence"],
        "implications": ["implication"],
        "relationships": [],
    }
    result = renderer.render("wiki_article", data)
    assert "relationships:" not in result


def test_render_contested():
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "count": 1,
        "articles": [
            {
                "title": "refresh-strategy",
                "original_claim": "Refresh tokens before expiry",
                "contested_by": "2026-04-15_refactor-auth",
                "contested_reason": "claims refresh-on-401 is better",
                "evidence_for": 2,
                "evidence_against": 1,
            },
        ],
    }
    result = renderer.render("contested", data)
    assert "contested_count: 1" in result
    assert "[[refresh-strategy]]" in result
    assert "Refresh tokens before expiry" in result
    assert "[[2026-04-15_refactor-auth]]" in result
    assert "2 sessions" in result


def test_custom_template_dir(tmp_path):
    """User-provided template dir overrides defaults."""
    custom = tmp_path / "templates"
    custom.mkdir()
    (custom / "record.md.j2").write_text("CUSTOM: {{ branch }}")
    renderer = TemplateRenderer(template_dir=custom)
    result = renderer.render("record", {"branch": "main"})
    assert result == "CUSTOM: main"
