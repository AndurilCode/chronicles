"""Tests for the linter."""
from pathlib import Path
from chronicles.linter import lint, LintReport


def _write_article(chronicles_dir: Path, name: str, confidence: str = "low",
                   article_type: str = "convention", tags: list[str] | None = None,
                   sources: list[str] | None = None) -> Path:
    tags = tags or ["test"]
    sources = sources or ["2026-04-09_test"]
    path = chronicles_dir / "wiki" / "articles" / f"{name}.md"
    path.write_text(
        f"---\ntype: {article_type}\nconfidence: {confidence}\n"
        f"sources:\n"
        + "".join(f'  - "[[{s}]]"\n' for s in sources)
        + f"first_seen: 2026-04-01\nlast_confirmed: 2026-04-09\n"
        f"tags: {tags}\n---\n\n# {name}\n\nSome content.\n"
    )
    return path


def test_lint_valid_structure(chronicles_dir):
    _write_article(chronicles_dir, "test-article")
    report = lint(chronicles_dir)
    assert isinstance(report, LintReport)
    assert len(report.errors) == 0


def test_lint_detects_missing_frontmatter(chronicles_dir):
    path = chronicles_dir / "wiki" / "articles" / "bad.md"
    path.write_text("# No frontmatter\nJust content.\n")
    report = lint(chronicles_dir)
    assert any("frontmatter" in e.lower() for e in report.errors)


def test_lint_detects_broken_wikilinks(chronicles_dir):
    path = chronicles_dir / "wiki" / "articles" / "test.md"
    path.write_text(
        "---\ntype: convention\nconfidence: low\n"
        'sources:\n  - "[[2026-04-09_test]]"\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-09\ntags: [test]\n---\n\n"
        "# Test\n\nSee [[nonexistent-article]].\n"
    )
    report = lint(chronicles_dir)
    assert any("nonexistent-article" in w for w in report.warnings)


def test_lint_promotes_low_to_medium(chronicles_dir):
    _write_article(chronicles_dir, "multi-source",
                   confidence="low",
                   sources=["2026-04-01_session-a", "2026-04-05_session-b"])
    report = lint(chronicles_dir)
    content = (chronicles_dir / "wiki" / "articles" / "multi-source.md").read_text()
    assert "confidence: medium" in content


def test_lint_promotes_medium_to_high(chronicles_dir):
    _write_article(chronicles_dir, "well-confirmed",
                   confidence="medium",
                   sources=["s1", "s2", "s3"])
    report = lint(chronicles_dir)
    content = (chronicles_dir / "wiki" / "articles" / "well-confirmed.md").read_text()
    assert "confidence: high" in content


def test_lint_regenerates_gold(chronicles_dir):
    _write_article(chronicles_dir, "gold-article",
                   confidence="high", article_type="convention")
    report = lint(chronicles_dir)
    gold = (chronicles_dir / "GOLD.md").read_text()
    assert "gold-article" in gold


def test_lint_gold_excludes_low_confidence(chronicles_dir):
    _write_article(chronicles_dir, "low-article", confidence="low")
    report = lint(chronicles_dir)
    gold = (chronicles_dir / "GOLD.md").read_text()
    assert "low-article" not in gold


def test_lint_detects_and_merges_duplicates(chronicles_dir):
    _write_article(chronicles_dir, "connection-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-01_session-a"])
    _write_article(chronicles_dir, "conn-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-05_session-b"])
    report = lint(chronicles_dir)
    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 1
    content = articles[0].read_text()
    assert "session-a" in content
    assert "session-b" in content


def test_lint_no_merge_for_different_topics(chronicles_dir):
    _write_article(chronicles_dir, "auth-pattern", confidence="low",
                   article_type="convention", tags=["auth"])
    _write_article(chronicles_dir, "retry-pattern", confidence="low",
                   article_type="pattern", tags=["retry"])
    report = lint(chronicles_dir)
    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 2
