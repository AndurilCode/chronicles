"""Tests for the chronicles signals CLI command."""
import json
from unittest.mock import patch, MagicMock

from chronicles.cli import main
from chronicles.models import SignalsResult


def test_signals_command_runs_pipeline(chronicles_dir, tmp_path):
    """End-to-end: signals command parses, cleans, extracts, writes."""
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "human", "text": "find the config"}) + "\n"
        + json.dumps({"type": "assistant", "text": "Let me search."}) + "\n"
    )

    mock_result = SignalsResult(signals=[], demotions=[])

    with patch("chronicles.cli.SignalsExtractor") as MockExtractor:
        instance = MockExtractor.return_value
        instance.extract.return_value = mock_result

        with patch("chronicles.cli.detect_source") as mock_detect:
            from chronicles.models import Transcript, Message
            mock_source = MagicMock()
            mock_source.key = "claude-code"
            mock_source.parse_session.return_value = Transcript(
                session_id="test", source="claude-code", project="proj",
                repository="repo", branch="main", cwd="/tmp",
                timestamp_start="2026-04-09T10:00:00Z",
                timestamp_end="2026-04-09T10:30:00Z",
                model="opus",
                messages=[
                    Message(role="user", content="find the config", timestamp="T0"),
                    Message(role="assistant", content="Let me search.", timestamp="T1"),
                ],
            )
            mock_detect.return_value = mock_source

            main(["signals", str(transcript_path),
                  "--chronicles-dir", str(chronicles_dir)])

    signals_path = chronicles_dir / "SIGNALS.md"
    assert signals_path.exists()


def test_signals_command_no_paths_exits(chronicles_dir):
    """signals with no paths and no --since should fail."""
    try:
        main(["signals", "--chronicles-dir", str(chronicles_dir)])
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 1
