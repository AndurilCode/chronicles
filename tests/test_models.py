"""Tests for core data models."""
from chronicles.models import Message, Transcript, CleanedTranscript, TranscriptMetadata, ExtractionResult, Signal, SignalsResult


def test_message_defaults():
    msg = Message(role="user", content="hello", timestamp="2026-04-09T10:00:00Z")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.tool_name == ""
    assert msg.tool_input == {}


def test_message_tool_call():
    msg = Message(
        role="tool_call",
        content="",
        timestamp="2026-04-09T10:00:00Z",
        tool_name="Read",
        tool_input={"file_path": "/src/main.py"},
    )
    assert msg.tool_name == "Read"
    assert msg.tool_input["file_path"] == "/src/main.py"


def test_transcript_fields():
    t = Transcript(
        session_id="abc123",
        source="claude-code",
        project="my-project",
        repository="my-repo",
        branch="feat/test",
        cwd="/home/user/repo",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="claude-opus-4-6",
        messages=[],
    )
    assert t.source == "claude-code"
    assert t.date == "2026-04-09"
    assert t.messages == []


def test_transcript_date_from_timestamp():
    t = Transcript(
        session_id="x", source="", project="", repository="",
        branch="", cwd="", timestamp_start="2026-12-25T08:00:00Z",
        timestamp_end="", model="", messages=[],
    )
    assert t.date == "2026-12-25"


def test_transcript_date_empty():
    t = Transcript(
        session_id="x", source="", project="", repository="",
        branch="", cwd="", timestamp_start="",
        timestamp_end="", model="", messages=[],
    )
    assert t.date == ""


def test_cleaned_transcript():
    meta = TranscriptMetadata(
        session_id="abc", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z", model="opus",
    )
    ct = CleanedTranscript(metadata=meta, chunks=[[]])
    assert ct.metadata.session_id == "abc"
    assert len(ct.chunks) == 1


def test_extraction_result_fields():
    result = ExtractionResult(
        branch="feat/test",
        status="complete",
        tags=["test"],
        duration="10min",
        files_changed=["src/main.py"],
        objective="Test something",
        outcome="It worked",
        decisions=[],
        problems=[],
        discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[],
    )
    assert result.status == "complete"
    assert result.slug == "feat-test"


def test_extraction_result_slug_strips_prefix():
    result = ExtractionResult(
        branch="feat/oauth-connections", status="complete", tags=[],
        duration="", files_changed=[], objective="", outcome="",
        decisions=[], problems=[], discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[],
    )
    assert result.slug == "feat-oauth-connections"


def test_signal_dataclass():
    s = Signal(
        pattern="Agent used Bash grep instead of Grep tool",
        type="mistake",
        rule="Use the Grep tool instead of Bash with grep",
        context=["tool:Bash", "tool:Grep"],
        severity="high",
    )
    assert s.type == "mistake"
    assert s.severity == "high"


def test_signals_result_dataclass():
    r = SignalsResult(
        signals=[
            Signal(
                pattern="Searched src/ three times before finding module in lib/",
                type="mistake",
                rule="Check lib/ for utility modules",
                context=["area:navigation"],
                severity="low",
            ),
        ],
        demotions=["Use find instead of Glob for deep searches"],
    )
    assert len(r.signals) == 1
    assert len(r.demotions) == 1
