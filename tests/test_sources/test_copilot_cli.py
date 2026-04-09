"""Tests for Copilot CLI source adapter."""
from pathlib import Path
from chronicles.sources.copilot_cli import CopilotCLISource

FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_parse_session():
    source = CopilotCLISource()
    transcript = source.parse_session(FIXTURES / "copilot_cli_session.jsonl")
    assert transcript.source == "copilot-cli"
    assert transcript.cwd == "/home/user/project"
    assert transcript.timestamp_start == "2026-04-09T10:00:00.000Z"
    assert len(transcript.messages) > 0

def test_parse_session_message_roles():
    source = CopilotCLISource()
    transcript = source.parse_session(FIXTURES / "copilot_cli_session.jsonl")
    roles = [m.role for m in transcript.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_call" in roles
    assert "tool_result" in roles

def test_tool_names_are_canonical():
    source = CopilotCLISource()
    transcript = source.parse_session(FIXTURES / "copilot_cli_session.jsonl")
    tool_calls = [m for m in transcript.messages if m.role == "tool_call"]
    tool_names = [m.tool_name for m in tool_calls]
    assert "Read" in tool_names
    assert "Edit" in tool_names
    assert "readFile" not in tool_names
