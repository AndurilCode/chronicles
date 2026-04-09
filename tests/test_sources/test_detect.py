"""Tests for source auto-detection."""
import json
from pathlib import Path

from chronicles.sources import detect_source, ALL_SOURCES
from chronicles.sources.base import BaseSource


def test_all_sources_registered():
    assert len(ALL_SOURCES) == 3
    keys = [s.key for s in ALL_SOURCES]
    assert "claude-code" in keys
    assert "copilot-cli" in keys
    assert "copilot-vscode" in keys


def test_detect_claude_code(tmp_path):
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps({"type": "human", "message": {"content": [{"type": "text", "text": "hello"}]}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n"
    )
    source = detect_source(session)
    assert source.key == "claude-code"


def test_detect_copilot_cli(tmp_path):
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps({"type": "session.start", "timestamp": "2026-04-09T10:00:00Z"}) + "\n"
        + json.dumps({"type": "turn.start", "request": {"message": "hello"}}) + "\n"
    )
    source = detect_source(session)
    assert source.key == "copilot-cli"


def test_detect_copilot_vscode(tmp_path):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({
        "version": 2,
        "sessions": [{"requests": [{"message": {"text": "hello"}}]}],
    }))
    source = detect_source(session)
    assert source.key == "copilot-vscode"


def test_detect_unknown_raises(tmp_path):
    session = tmp_path / "unknown.txt"
    session.write_text("just some text\n")
    import pytest
    with pytest.raises(ValueError, match="Could not detect source"):
        detect_source(session)
