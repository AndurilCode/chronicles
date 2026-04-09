"""Tests for signals extractor — LLM-powered agentic pattern detection."""
import json
from unittest.mock import patch, MagicMock

from chronicles.config import LLMConfig
from chronicles.models import (
    CleanedTranscript, TranscriptMetadata, Message, Signal, SignalsResult,
)
from chronicles.signals_extractor import SignalsExtractor


def _make_cleaned(chunks: list[list[Message]]) -> CleanedTranscript:
    return CleanedTranscript(
        metadata=TranscriptMetadata(
            session_id="test-123", source="claude-code", project="proj",
            repository="repo", branch="main", cwd="/tmp",
            timestamp_start="2026-04-09T10:00:00Z",
            timestamp_end="2026-04-09T10:30:00Z", model="opus",
        ),
        chunks=chunks,
    )


def _make_config() -> LLMConfig:
    return LLMConfig(provider="claude-code", model="claude-haiku-4-5-20251001")


def test_build_prompt_includes_transcript():
    chunks = [[
        Message(role="user", content="find the config", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "config", "path": "src/"}),
    ]]
    ext = SignalsExtractor(_make_config())
    prompt = ext._build_prompt(_make_cleaned(chunks))
    assert "[TOOL_CALL: Grep]" in prompt
    assert "config" in prompt


def test_build_prompt_includes_existing_signals():
    ext = SignalsExtractor(_make_config())
    chunks = [[Message(role="user", content="hello", timestamp="T0")]]
    existing = "- Use Grep tool instead of Bash grep [tool:Bash,Grep]"
    prompt = ext._build_prompt(_make_cleaned(chunks), existing_signals=existing)
    assert "CURRENT SIGNALS" in prompt
    assert "Use Grep tool" in prompt


def test_parse_valid_response():
    ext = SignalsExtractor(_make_config())
    raw = json.dumps({
        "signals": [
            {
                "pattern": "Agent used Bash grep instead of Grep tool",
                "type": "mistake",
                "rule": "Use the Grep tool instead of Bash with grep",
                "context": ["tool:Bash", "tool:Grep"],
                "severity": "high",
            }
        ],
        "demotions": [],
    })
    result = ext._parse_response(raw)
    assert isinstance(result, SignalsResult)
    assert len(result.signals) == 1
    assert result.signals[0].type == "mistake"
    assert result.signals[0].severity == "high"


def test_parse_response_with_markdown_fences():
    ext = SignalsExtractor(_make_config())
    raw = '```json\n' + json.dumps({
        "signals": [],
        "demotions": ["old rule to remove"],
    }) + '\n```'
    result = ext._parse_response(raw)
    assert len(result.demotions) == 1


def test_parse_response_normalizes_type():
    ext = SignalsExtractor(_make_config())
    raw = json.dumps({
        "signals": [
            {
                "pattern": "p", "type": "Mistake", "rule": "r",
                "context": [], "severity": "HIGH",
            }
        ],
        "demotions": [],
    })
    result = ext._parse_response(raw)
    assert result.signals[0].type == "mistake"
    assert result.signals[0].severity == "high"


def test_parse_response_empty_signals():
    ext = SignalsExtractor(_make_config())
    raw = json.dumps({"signals": [], "demotions": []})
    result = ext._parse_response(raw)
    assert len(result.signals) == 0


def test_parse_response_repairs_trailing_comma():
    ext = SignalsExtractor(_make_config())
    raw = '{"signals": [{"pattern": "p", "type": "mistake", "rule": "r", "context": [], "severity": "low",}], "demotions": [],}'
    result = ext._parse_response(raw)
    assert len(result.signals) == 1


def test_extract_calls_claude_cli():
    ext = SignalsExtractor(_make_config())
    chunks = [[Message(role="user", content="test", timestamp="T0")]]
    response = json.dumps({"signals": [], "demotions": []})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=response, stderr=""
        )
        result = ext.extract(_make_cleaned(chunks))

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert isinstance(result, SignalsResult)


def test_extract_raises_on_cli_failure():
    ext = SignalsExtractor(_make_config())
    chunks = [[Message(role="user", content="test", timestamp="T0")]]

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="CLI error"
        )
        try:
            ext.extract(_make_cleaned(chunks))
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "CLI error" in str(e)
