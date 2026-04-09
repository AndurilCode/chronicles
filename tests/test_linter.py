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


def test_lint_marks_contested(chronicles_dir):
    path = chronicles_dir / "wiki" / "articles" / "old-convention.md"
    path.write_text(
        "---\ntype: convention\nconfidence: high\n"
        'sources:\n  - "[[2026-03-01_session-a]]"\n  - "[[2026-03-10_session-b]]"\n'
        "  - \"[[2026-03-20_session-c]]\"\n"
        "first_seen: 2026-03-01\nlast_confirmed: 2026-03-20\n"
        "tags: [test]\n---\n\n# old-convention\n\nUse snake_case.\n"
    )
    record = chronicles_dir / "records" / "2026-04-05_refactor.md"
    record.write_text(
        "---\ndate: 2026-04-05\nbranch: refactor\nstatus: complete\ntags: [test]\n"
        "agent: claude-code\nduration: 10min\nfiles_changed:\n  - src/a.py\n---\n\n"
        "# refactor\n\n## Discovered\n"
        "- [convention] Use camelCase, not snake_case — contradicts [[old-convention]]\n"
    )
    report = lint(chronicles_dir)
    content = path.read_text()
    assert "confidence: contested" in content
    assert "previous_confidence: high" in content


def test_lint_flags_stale_articles(chronicles_dir):
    _write_article(chronicles_dir, "stale-article",
                   confidence="high",
                   sources=["2025-01-01_ancient"])
    report = lint(chronicles_dir)
    assert any("stale" in w.lower() for w in report.warnings)


def test_lint_infers_contradicts_relationship(chronicles_dir):
    """When an article is contested, a contradicts relationship is added."""
    articles_dir = chronicles_dir / "wiki" / "articles"

    (articles_dir / "refresh-strategy.md").write_text(
        "---\ntype: decision\nconfidence: high\nsources:\n"
        '  - "[[2026-04-01_initial]]"\ntags: [auth]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Refresh Strategy\n\nRefresh before expiry.\n"
    )

    records_dir = chronicles_dir / "records"
    (records_dir / "2026-04-15_refactor-auth.md").write_text(
        "---\ndate: 2026-04-15\n---\n\n# Refactor Auth\n\n"
        "This contradicts [[refresh-strategy]].\n"
    )

    report = lint(chronicles_dir)

    content = (articles_dir / "refresh-strategy.md").read_text()
    assert "confidence: contested" in content
    assert "relationships:" in content
    assert "type: contradicts" in content
    assert "target: 2026-04-15_refactor-auth" in content


def test_lint_infers_related_to_from_tags(chronicles_dir):
    """Articles with overlapping tags get related-to relationships."""
    articles_dir = chronicles_dir / "wiki" / "articles"

    (articles_dir / "article-a.md").write_text(
        "---\ntype: convention\nconfidence: medium\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\ntags: [auth, oauth]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Article A\n\nContent A.\n"
    )
    (articles_dir / "article-b.md").write_text(
        "---\ntype: convention\nconfidence: medium\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\ntags: [auth, tokens]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Article B\n\nContent B.\n"
    )

    lint(chronicles_dir)

    content_a = (articles_dir / "article-a.md").read_text()
    assert "relationships:" in content_a
    assert "type: related-to" in content_a
    assert "target: article-b" in content_a
