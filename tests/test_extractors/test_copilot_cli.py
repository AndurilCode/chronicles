"""Tests for Copilot CLI extractor."""
import json
from unittest.mock import patch, MagicMock
from chronicles.config import LLMConfig
from chronicles.extractor import Extractor
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
    extractor = Extractor(config)
    transcript = _make_cleaned_transcript()
    prompt = extractor._build_prompt(transcript)
    assert "Fix the bug" in prompt
    assert "Fixed it." in prompt

def test_parses_llm_json_response():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
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

@patch("chronicles.llm_utils._call_cli")
def test_extract_calls_copilot(mock_cli):
    mock_cli.return_value = json.dumps({
        "branch": "fix/bug", "status": "complete", "tags": [],
        "duration": "5min", "files_changed": [],
        "objective": "Fix", "outcome": "Fixed",
        "decisions": [], "problems": [], "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [],
    })
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    result = extractor.extract(_make_cleaned_transcript())
    assert result.branch == "fix/bug"
    mock_cli.assert_called_once()
    cmd = mock_cli.call_args[0][0]
    assert "copilot" in cmd[0]
    assert "--model" in cmd

def test_prompt_includes_few_shot_example():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    transcript = _make_cleaned_transcript()
    prompt = extractor._build_prompt(transcript)
    assert "EXAMPLE OUTPUT" in prompt
    assert "scope-delimiter-trap" in prompt


def test_normalizes_status_enum():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    raw_json = json.dumps({
        "branch": "fix/bug", "status": "Completed", "tags": ["bugfix"],
        "duration": "5min", "files_changed": ["src/auth.py"],
        "objective": "Fix", "outcome": "Fixed",
        "decisions": [], "problems": [], "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [],
    })
    result = extractor._parse_response(raw_json)
    assert result.status == "complete"


def test_normalizes_article_type_and_confidence():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    raw_json = json.dumps({
        "branch": "fix/bug", "status": "complete", "tags": [],
        "duration": "5min", "files_changed": [],
        "objective": "Fix", "outcome": "Fixed",
        "decisions": [], "problems": [], "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [{
            "action": "create",
            "path": "wiki/articles/test.md",
            "data": {
                "title": "Test", "type": "Convention", "confidence": "High",
                "tags": ["test"], "body": "Test.", "evidence": ["e"], "implications": ["i"],
            },
        }],
    })
    result = extractor._parse_response(raw_json)
    instr = result.wiki_instructions[0]
    assert instr["data"]["type"] == "convention"
    assert instr["data"]["confidence"] == "low"  # "High" not in valid set, falls to "low"


def test_ensures_list_fields():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    raw_json = json.dumps({
        "branch": "fix/bug", "status": "complete", "tags": "single-tag",
        "duration": "5min", "files_changed": "single-file.py",
        "objective": "Fix", "outcome": "Fixed",
        "decisions": [], "problems": [], "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [],
    })
    result = extractor._parse_response(raw_json)
    assert result.tags == ["single-tag"]
    assert result.files_changed == ["single-file.py"]


def test_prompt_includes_contested_context():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    transcript = _make_cleaned_transcript()
    wiki_context = [
        {"title": "Refresh Strategy", "type": "decision", "tags": ["auth"],
         "path": "wiki/articles/refresh-strategy.md", "confidence": "contested"},
    ]
    prompt = extractor._build_prompt(transcript, wiki_context)
    assert "CONTESTED" in prompt
    assert "Refresh Strategy" in prompt
    assert '"resolve"' in prompt

def test_prompt_includes_relationship_schema():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = Extractor(config)
    transcript = _make_cleaned_transcript()
    prompt = extractor._build_prompt(transcript)
    assert '"relationships"' in prompt
    assert "supersedes" in prompt
    assert "contradicts" in prompt
    assert "depends-on" in prompt
