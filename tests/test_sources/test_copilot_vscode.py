"""Tests for Copilot VS Code source adapter."""
from pathlib import Path
from chronicles.sources.copilot_vscode import CopilotVSCodeSource

FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_parse_session():
    source = CopilotVSCodeSource()
    transcript = source.parse_session(FIXTURES / "copilot_vscode_session.json")
    assert transcript.source == "copilot-vscode"
    assert transcript.session_id == "vscode-session-001"
    assert len(transcript.messages) > 0

def test_parse_session_message_roles():
    source = CopilotVSCodeSource()
    transcript = source.parse_session(FIXTURES / "copilot_vscode_session.json")
    roles = [m.role for m in transcript.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_call" in roles

def test_tool_names_are_canonical():
    source = CopilotVSCodeSource()
    transcript = source.parse_session(FIXTURES / "copilot_vscode_session.json")
    tool_calls = [m for m in transcript.messages if m.role == "tool_call"]
    tool_names = [m.tool_name for m in tool_calls]
    assert "Read" in tool_names
    assert "Edit" in tool_names
