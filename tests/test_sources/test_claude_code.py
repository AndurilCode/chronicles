"""Tests for Claude Code source adapter."""
from pathlib import Path
from chronicles.sources.claude_code import ClaudeCodeSource

FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_parse_session():
    source = ClaudeCodeSource()
    transcript = source.parse_session(FIXTURES / "claude_code_session.jsonl")
    assert transcript.source == "claude-code"
    assert transcript.model == "claude-opus-4-6"
    assert transcript.cwd == "/home/user/project"
    assert transcript.timestamp_start == "2026-04-09T10:00:00.000Z"
    assert transcript.timestamp_end == "2026-04-09T10:00:15.000Z"
    assert len(transcript.messages) > 0

def test_parse_session_message_roles():
    source = ClaudeCodeSource()
    transcript = source.parse_session(FIXTURES / "claude_code_session.jsonl")
    roles = [m.role for m in transcript.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_call" in roles
    assert "tool_result" in roles

def test_parse_session_tool_names():
    source = ClaudeCodeSource()
    transcript = source.parse_session(FIXTURES / "claude_code_session.jsonl")
    tool_calls = [m for m in transcript.messages if m.role == "tool_call"]
    tool_names = [m.tool_name for m in tool_calls]
    assert "Read" in tool_names
    assert "Edit" in tool_names

def test_parse_session_skips_sidechains(tmp_path):
    import json
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps({"type": "human", "isSidechain": False, "cwd": "/tmp",
                     "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]},
                     "timestamp": "2026-04-09T10:00:00Z"}) + "\n"
        + json.dumps({"type": "assistant", "isSidechain": True,
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "sidechain"}],
                                 "model": "claude-opus-4-6"},
                     "timestamp": "2026-04-09T10:00:05Z"}) + "\n"
    )
    source = ClaudeCodeSource()
    transcript = source.parse_session(session)
    contents = [m.content for m in transcript.messages]
    assert "sidechain" not in contents
