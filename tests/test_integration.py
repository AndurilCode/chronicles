"""Integration test — full pipeline from fixture transcript to wiki output."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from chronicles.cli import main


def test_full_ingest_pipeline(chronicles_dir, tmp_path):
    """End-to-end: parse a Claude Code fixture, mock the extractor, verify output."""
    fixtures = Path(__file__).parent / "fixtures"
    transcript_path = fixtures / "claude_code_session.jsonl"

    mock_response = json.dumps({
        "branch": "fix/typo",
        "status": "complete",
        "tags": ["bugfix"],
        "duration": "5min",
        "files_changed": ["src/auth.py"],
        "objective": "Fix typo in auth.py",
        "outcome": "Fixed pasword -> password",
        "decisions": [],
        "problems": [
            {"description": "Typo in variable", "root_cause": "pasword misspelled", "dead_end": False}
        ],
        "discovered": [
            {"type": "trap", "description": "auth.py has typo-prone variable names"}
        ],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [
            {
                "action": "create",
                "path": "wiki/articles/auth-typo-trap.md",
                "data": {
                    "title": "Auth Typo Trap",
                    "type": "trap",
                    "confidence": "low",
                    "tags": ["auth", "typo"],
                    "body": "auth.py has typo-prone variable names.",
                    "evidence": ["Found in fix/typo session"],
                    "implications": ["Review auth.py variable names carefully"],
                },
            }
        ],
    })

    with patch("chronicles.extractors.copilot_cli.subprocess.run") as mock_run, \
         patch("chronicles.cli.ProcessPoolExecutor") as mock_pool_cls:
        # Make ProcessPoolExecutor behave like a simple sequential executor
        mock_pool = MagicMock()
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_pool.map = lambda fn, iterable: list(map(fn, iterable))
        mock_pool_cls.return_value = mock_pool

        mock_run.return_value = MagicMock(returncode=0, stdout=mock_response)
        main([
            "ingest", str(transcript_path),
            "--chronicles-dir", str(chronicles_dir),
        ])

    # Verify record was written
    records = list((chronicles_dir / "records").glob("*.md"))
    assert len(records) == 1
    assert "fix-typo" in records[0].name

    # Verify CHRONICLES.md was updated
    chronicles_content = (chronicles_dir / "CHRONICLES.md").read_text()
    assert "fix-typo" in chronicles_content
    assert "Fix typo" in chronicles_content

    # Verify wiki article was created
    article = chronicles_dir / "wiki" / "articles" / "auth-typo-trap.md"
    assert article.exists()
    assert "Auth Typo Trap" in article.read_text()

    # Verify GOLD.md (should not contain low-confidence article)
    gold = (chronicles_dir / "GOLD.md").read_text()
    assert "auth-typo-trap" not in gold


def test_lint_standalone(chronicles_dir):
    """Lint command runs without errors on empty chronicles."""
    main(["lint", "--chronicles-dir", str(chronicles_dir)])
    # Should not raise


def test_ingest_with_relationships(chronicles_dir):
    """Full pipeline: extractor returns relationships, writer persists them, linter infers more."""
    from unittest.mock import patch, MagicMock
    import json
    from chronicles.cli import _run_ingest

    # Create a pre-existing article for the relationship target
    articles_dir = chronicles_dir / "wiki" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    (articles_dir / "old-pattern.md").write_text(
        "---\ntype: pattern\nconfidence: medium\nsources:\n"
        '  - "[[2026-03-01_initial]]"\n  - "[[2026-03-15_confirm]]"\n'
        "tags: [auth, legacy]\nfirst_seen: 2026-03-01\nlast_confirmed: 2026-03-15\n---\n\n"
        "# Old Pattern\n\nThe old way.\n\n## Evidence\n- evidence\n\n## Implications\n- implication\n"
    )

    # Write a fixture transcript
    fixture = chronicles_dir.parent / "session.jsonl"
    fixture.write_text(
        '{"type":"human","timestamp":"2026-04-09T10:00:00Z","message":{"content":"update the pattern"}}\n'
        '{"type":"assistant","timestamp":"2026-04-09T10:01:00Z","message":{"content":[{"type":"text","text":"Done."}]}}\n'
    )

    extractor_response = json.dumps({
        "branch": "feat/new-pattern",
        "status": "complete",
        "tags": ["auth"],
        "duration": "10min",
        "files_changed": ["src/auth.py"],
        "objective": "Update pattern",
        "outcome": "Pattern updated",
        "decisions": [],
        "problems": [],
        "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [{
            "action": "create",
            "path": "wiki/articles/new-pattern.md",
            "data": {
                "title": "New Pattern",
                "type": "pattern",
                "confidence": "medium",
                "tags": ["auth", "modern"],
                "body": "The new way of doing things.",
                "evidence": ["From this session"],
                "implications": ["Use new pattern"],
            },
            "relationships": [
                {"type": "supersedes", "target": "old-pattern"}
            ],
        }],
    })

    with patch("chronicles.extractors.copilot_cli.subprocess.run") as mock_run, \
         patch("chronicles.linter._get_similarity_engine", return_value=None):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=extractor_response, stderr=""
        )

        args = MagicMock()
        args.paths = [fixture]
        args.source = "claude-code"
        args.since = None
        args.chronicles_dir = chronicles_dir
        args.no_enrich = True

        _run_ingest(args)

    # Verify the new article was written with relationships
    new_article = articles_dir / "new-pattern.md"
    assert new_article.exists()
    content = new_article.read_text()
    assert "relationships:" in content
    assert "type: supersedes" in content
    assert "target: old-pattern" in content

    # Verify related-to was inferred by linter (both articles share "auth" tag)
    assert "type: related-to" in content


def test_conflict_resolution_lifecycle(chronicles_dir):
    """Full lifecycle: article promoted -> contested -> evidence gathered -> resolved."""
    from unittest.mock import patch
    from chronicles.linter import lint

    articles_dir = chronicles_dir / "wiki" / "articles"
    records_dir = chronicles_dir / "records"

    # Step 1: Create a high-confidence article
    (articles_dir / "auth-pattern.md").write_text(
        "---\ntype: pattern\nconfidence: high\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\n  - "[[2026-04-03_s3]]"\n'
        "tags: [auth]\nfirst_seen: 2026-04-01\nlast_confirmed: 2026-04-03\n---\n\n"
        "# Auth Pattern\n\nUse refresh-before-expiry.\n"
    )

    # Step 2: Create a record that contests it
    (records_dir / "2026-04-10_challenge.md").write_text(
        "---\ndate: 2026-04-10\n---\n\n# Challenge\n\n"
        "This contradicts [[auth-pattern]].\n"
    )

    # Run lint — should mark as contested
    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = (articles_dir / "auth-pattern.md").read_text()
    assert "confidence: contested" in content
    assert (chronicles_dir / "CONTESTED.md").exists()
    contested_md = (chronicles_dir / "CONTESTED.md").read_text()
    assert "auth-pattern" in contested_md

    # Step 3: Add resolution evidence (simulating what the writer would do)
    text = (articles_dir / "auth-pattern.md").read_text()
    text = text.replace(
        "\n---\n",
        "\nresolution_evidence:\n"
        '  - record: "[[2026-04-12_evidence1]]"\n'
        "    supports: original\n"
        '  - record: "[[2026-04-14_evidence2]]"\n'
        "    supports: original\n"
        "---\n",
        1,
    )
    (articles_dir / "auth-pattern.md").write_text(text)

    # Run lint again — should resolve
    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report2 = lint(chronicles_dir)

    content = (articles_dir / "auth-pattern.md").read_text()
    assert "confidence: high" in content
    assert "## Resolution History" in content
    assert "Resolved in favor of original" in content

    # CONTESTED.md should now be empty
    contested_md = (chronicles_dir / "CONTESTED.md").read_text()
    assert "contested_count: 0" in contested_md
