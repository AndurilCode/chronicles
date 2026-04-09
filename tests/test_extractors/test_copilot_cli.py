"""Tests for Copilot CLI extractor."""
import json
from unittest.mock import patch, MagicMock
from chronicles.config import LLMConfig
from chronicles.extractors.copilot_cli import CopilotCLIExtractor
from chronicles.models import Message, CleanedTranscript, TranscriptMetadata, ExtractionResult

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

def test_builds_prompt():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    transcript = _make_cleaned_transcript()
    prompt = extractor._build_prompt(transcript)
    assert "Fix the bug" in prompt
    assert "Fixed it." in prompt

def test_parses_llm_json_response():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    raw_json = json.dumps({
        "branch": "fix/bug", "status": "complete", "tags": ["bugfix"],
        "duration": "5min", "files_changed": ["src/auth.py"],
        "objective": "Fix the bug", "outcome": "Bug fixed",
        "decisions": [], "problems": [], "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [],
    })
    result = extractor._parse_response(raw_json)
    assert isinstance(result, ExtractionResult)
    assert result.branch == "fix/bug"
    assert result.status == "complete"

@patch("subprocess.run")
def test_extract_calls_copilot(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "branch": "fix/bug", "status": "complete", "tags": [],
            "duration": "5min", "files_changed": [],
            "objective": "Fix", "outcome": "Fixed",
            "decisions": [], "problems": [], "discovered": [],
            "continuity": {"unfinished": [], "open_questions": [], "next": []},
            "wiki_instructions": [],
        }),
    )
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    result = extractor.extract(_make_cleaned_transcript())
    assert result.branch == "fix/bug"
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "copilot" in cmd[0]
    assert "--model" in cmd
