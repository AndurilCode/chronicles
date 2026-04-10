"""Tests for extraction with the claude-code provider."""
import json
from unittest.mock import patch, MagicMock
from chronicles.config import LLMConfig
from chronicles.extractor import Extractor
from chronicles.models import Message, CleanedTranscript, TranscriptMetadata

def _make_cleaned_transcript() -> CleanedTranscript:
    meta = TranscriptMetadata(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z", model="opus",
    )
    messages = [
        Message(role="user", content="Fix the bug", timestamp="T1"),
        Message(role="assistant", content="Fixed it.", timestamp="T2"),
    ]
    return CleanedTranscript(metadata=meta, chunks=[messages])

@patch("chronicles.llm_utils._call_cli")
def test_extract_calls_claude(mock_cli):
    mock_cli.return_value = json.dumps({
        "branch": "fix/bug", "status": "complete", "tags": [],
        "duration": "5min", "files_changed": [],
        "objective": "Fix", "outcome": "Fixed",
        "decisions": [], "problems": [], "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [],
    })
    config = LLMConfig(provider="claude-code", model="claude-opus-4-6")
    extractor = Extractor(config)
    result = extractor.extract(_make_cleaned_transcript())
    assert result.branch == "fix/bug"
    mock_cli.assert_called_once()
    cmd = mock_cli.call_args[0][0]
    assert "claude" in cmd[0]
    assert "--print" in cmd
