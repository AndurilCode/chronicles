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
