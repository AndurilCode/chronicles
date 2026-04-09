"""Tests for transcript cleaner."""
from chronicles.cleaner import clean_transcript
from chronicles.models import Message, Transcript, CleanedTranscript


def _make_transcript(messages: list[Message]) -> Transcript:
    return Transcript(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus", messages=messages,
    )


def test_strips_read_tool_results():
    messages = [
        Message(role="user", content="read the file", timestamp="T1"),
        Message(role="tool_call", content="", timestamp="T2", tool_name="Read",
                tool_input={"file_path": "src/main.py"}),
        Message(role="tool_result", content="huge file content here...", timestamp="T3",
                tool_name="Read"),
        Message(role="assistant", content="I see the file.", timestamp="T4"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert all(m.content == "" for m in tool_results if m.tool_name == "Read")


def test_keeps_edit_tool_results():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Edit",
                tool_input={"file_path": "a.py", "old_string": "x", "new_string": "y"}),
        Message(role="tool_result", content="File edited successfully.", timestamp="T2",
                tool_name="Edit"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert any(m.content == "File edited successfully." for m in tool_results)


def test_keeps_write_tool_results():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Write",
                tool_input={"file_path": "a.py", "content": "hello"}),
        Message(role="tool_result", content="File written.", timestamp="T2",
                tool_name="Write"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert any(m.content == "File written." for m in tool_results)


def test_strips_grep_glob_bash_results():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "foo"}),
        Message(role="tool_result", content="lots of matches...", timestamp="T2",
                tool_name="Grep"),
        Message(role="tool_call", content="", timestamp="T3", tool_name="Glob",
                tool_input={"pattern": "*.py"}),
        Message(role="tool_result", content="file1.py\nfile2.py", timestamp="T4",
                tool_name="Glob"),
        Message(role="tool_call", content="", timestamp="T5", tool_name="Bash",
                tool_input={"command": "ls"}),
        Message(role="tool_result", content="big output...", timestamp="T6",
                tool_name="Bash"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert all(m.content == "" for m in tool_results)


def test_tool_calls_always_preserved():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Read",
                tool_input={"file_path": "a.py"}),
        Message(role="tool_result", content="content", timestamp="T2", tool_name="Read"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "Read"
    assert tool_calls[0].tool_input == {"file_path": "a.py"}


def test_single_chunk_for_small_transcript():
    messages = [
        Message(role="user", content="hello", timestamp="T1"),
        Message(role="assistant", content="hi", timestamp="T2"),
    ]
    result = clean_transcript(_make_transcript(messages))
    assert len(result.chunks) == 1


def test_metadata_preserved():
    messages = [Message(role="user", content="hello", timestamp="T1")]
    result = clean_transcript(_make_transcript(messages))
    assert result.metadata.session_id == "test"
    assert result.metadata.source == "claude-code"
    assert result.metadata.project == "proj"
