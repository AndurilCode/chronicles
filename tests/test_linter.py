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


def test_semantic_dedup_merges_similar_articles(chronicles_dir):
    """Semantic dedup merges articles with similar content, adds supersedes relationship."""
    from unittest.mock import patch, MagicMock

    _write_article(chronicles_dir, "token-refresh-pattern",
                   confidence="low", article_type="pattern", tags=["auth", "tokens"],
                   sources=["2026-04-01_session-a"])
    _write_article(chronicles_dir, "oauth-token-refresh",
                   confidence="low", article_type="pattern", tags=["auth", "oauth"],
                   sources=["2026-04-05_session-b"])

    mock_engine = MagicMock()
    mock_engine.batch_score.return_value = [(0, 1, 0.85)]
    mock_engine.config = MagicMock(threshold=0.7)

    with patch("chronicles.linter._get_similarity_engine", return_value=mock_engine):
        report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 1
    content = articles[0].read_text()
    assert "session-a" in content
    assert "session-b" in content
    assert "type: supersedes" in content


def test_semantic_dedup_fallback_without_engine(chronicles_dir):
    """When similarity engine is unavailable, falls back to SequenceMatcher."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "connection-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-01_session-a"])
    _write_article(chronicles_dir, "conn-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-05_session-b"])

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 1


def test_semantic_dedup_respects_type_filter(chronicles_dir):
    """Articles with different types are never merged, even if semantically similar."""
    from unittest.mock import patch, MagicMock

    _write_article(chronicles_dir, "retry-convention",
                   confidence="low", article_type="convention", tags=["retry"],
                   sources=["2026-04-01_s1"])
    _write_article(chronicles_dir, "retry-pattern",
                   confidence="low", article_type="pattern", tags=["retry"],
                   sources=["2026-04-05_s2"])

    mock_engine = MagicMock()
    mock_engine.batch_score.return_value = [(0, 1, 0.95)]
    mock_engine.config = MagicMock(threshold=0.7)

    with patch("chronicles.linter._get_similarity_engine", return_value=mock_engine):
        report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 2


def test_decay_demotes_high_to_medium(chronicles_dir):
    """High-confidence article with old last_confirmed gets demoted to medium."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "old-high", confidence="high",
                   sources=["2025-01-01_ancient", "2025-02-01_old", "2025-03-01_also-old"])
    path = chronicles_dir / "wiki" / "articles" / "old-high.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2025-06-01")
    path.write_text(text)

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = path.read_text()
    assert "confidence: medium" in content
    assert any("old-high" in w and "high -> medium" in w for w in report.warnings)


def test_decay_medium_to_low_requires_no_inbound_links(chronicles_dir):
    """Medium article is NOT demoted to low if other articles link to it."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "referenced-medium", confidence="medium",
                   sources=["2025-01-01_ancient", "2025-02-01_old"])
    path = chronicles_dir / "wiki" / "articles" / "referenced-medium.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2025-01-01")
    path.write_text(text)

    linker = chronicles_dir / "wiki" / "articles" / "linker.md"
    linker.write_text(
        "---\ntype: convention\nconfidence: low\nsources:\n"
        '  - "[[2026-04-01_recent]]"\ntags: [other]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Linker\n\nSee [[referenced-medium]] for details.\n"
    )

    (chronicles_dir / "records" / "2026-04-01_recent.md").write_text(
        "---\ndate: 2026-04-01\n---\n# Recent\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = path.read_text()
    assert "confidence: medium" in content  # NOT demoted


def test_decay_archives_old_low_article(chronicles_dir):
    """Low-confidence article with no links gets archived after archive_after_days."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "ancient-low", confidence="low",
                   sources=["2024-01-01_very-old"])
    path = chronicles_dir / "wiki" / "articles" / "ancient-low.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2024-01-01")
    path.write_text(text)

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    assert not path.exists()
    archived = chronicles_dir / "wiki" / "archived" / "ancient-low.md"
    assert archived.exists()
    content = archived.read_text()
    assert "archived_reason: decay" in content


def test_calibration_sets_promoted_on(chronicles_dir):
    """When an article is promoted to high, promoted_on is set."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "promoted-article",
                   confidence="medium",
                   sources=["s1", "s2", "s3"])

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = (chronicles_dir / "wiki" / "articles" / "promoted-article.md").read_text()
    assert "confidence: high" in content
    assert "promoted_on:" in content


def test_calibration_warns_on_quick_contestation(chronicles_dir):
    """Warn when a recently promoted article gets contested."""
    from unittest.mock import patch

    path = chronicles_dir / "wiki" / "articles" / "fragile-convention.md"
    path.write_text(
        "---\ntype: convention\nconfidence: high\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\n  - "[[2026-04-03_s3]]"\n'
        "tags: [test]\nfirst_seen: 2026-04-01\nlast_confirmed: 2026-04-03\n"
        "promoted_on: 2026-04-03\n---\n\n# Fragile Convention\n\nContent.\n"
    )

    record = chronicles_dir / "records" / "2026-04-05_challenge.md"
    record.write_text(
        "---\ndate: 2026-04-05\n---\n\n# Challenge\n\n"
        "This contradicts [[fragile-convention]].\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    assert any("fragile-convention" in w and "contested shortly after promotion" in w
               for w in report.warnings)


def test_decay_skips_depends_on_targets(chronicles_dir):
    """Articles that are depends-on targets are never archived."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "depended-upon", confidence="low",
                   sources=["2024-01-01_very-old"])
    path = chronicles_dir / "wiki" / "articles" / "depended-upon.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2024-01-01")
    path.write_text(text)

    depender = chronicles_dir / "wiki" / "articles" / "depender.md"
    depender.write_text(
        "---\ntype: convention\nconfidence: medium\nsources:\n"
        '  - "[[2026-04-01_recent]]"\n  - "[[2026-04-02_recent2]]"\ntags: [other]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n"
        "relationships:\n  - type: depends-on\n    target: depended-upon\n---\n\n"
        "# Depender\n\nDepends on depended-upon.\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    assert path.exists()  # NOT archived
    assert any("depended-upon" in w and "depends-on" in w for w in report.warnings)


def test_resolve_contested_with_evidence(chronicles_dir):
    """Contested article is resolved when 2+ sessions support one side."""
    from unittest.mock import patch

    articles_dir = chronicles_dir / "wiki" / "articles"
    path = articles_dir / "refresh-strategy.md"
    path.write_text(
        "---\ntype: decision\nconfidence: contested\nsources:\n"
        '  - "[[2026-04-01_initial]]"\n  - "[[2026-04-05_confirm]]"\n  - "[[2026-04-10_confirm2]]"\n'
        'contested_by: "[[2026-04-15_refactor-auth]]"\n'
        "previous_confidence: high\ntags: [auth]\n"
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-10\n"
        "resolution_evidence:\n"
        '  - record: "[[2026-04-18_perf-review]]"\n'
        "    supports: original\n"
        '  - record: "[[2026-04-20_auth-fix]]"\n'
        "    supports: original\n"
        "---\n\n# Refresh Strategy\n\nRefresh before expiry.\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = path.read_text()
    assert "confidence: high" in content
    assert "## Resolution History" in content
    assert "Resolved in favor of original" in content


def test_regenerate_contested_md(chronicles_dir):
    """CONTESTED.md is regenerated from contested articles."""
    from unittest.mock import patch

    articles_dir = chronicles_dir / "wiki" / "articles"
    (articles_dir / "some-article.md").write_text(
        "---\ntype: decision\nconfidence: contested\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n'
        'contested_by: "[[2026-04-15_challenge]]"\n'
        "previous_confidence: high\ntags: [auth]\n"
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Some Article\n\nOriginal claim here.\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    contested_md = chronicles_dir / "CONTESTED.md"
    assert contested_md.exists()
    content = contested_md.read_text()
    assert "contested_count: 1" in content
    assert "[[some-article]]" in content
