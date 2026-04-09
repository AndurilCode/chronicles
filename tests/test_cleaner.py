"""Tests for transcript cleaner."""
from chronicles.cleaner import clean_transcript
from chronicles.models import Message, Transcript


def _make_transcript(messages: list[Message]) -> Transcript:
    return Transcript(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus", messages=messages,
    )


# ── Tool result filtering ──


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
        Message(role="user", content="edit file", timestamp="T0"),
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
        Message(role="user", content="write file", timestamp="T0"),
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
        Message(role="user", content="search", timestamp="T0"),
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


# ── Tool call input summarization ──


def test_summarizes_read_tool_call_input():
    messages = [
        Message(role="user", content="read", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Read",
                tool_input={"file_path": "/src/main.py"}),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "Read"
    assert tool_calls[0].content == "/src/main.py"
    assert tool_calls[0].tool_input == {}  # full input stripped


def test_summarizes_edit_tool_call_input():
    messages = [
        Message(role="user", content="edit", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Edit",
                tool_input={"file_path": "a.py", "old_string": "old code here", "new_string": "new code here"}),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert "a.py" in tool_calls[0].content
    assert "old code" in tool_calls[0].content
    assert "new code" in tool_calls[0].content


def test_summarizes_bash_tool_call_input():
    messages = [
        Message(role="user", content="run", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "python3 -m pytest -v --tb=short"}),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert "pytest" in tool_calls[0].content


# ── Plumbing tool skipping ──


def test_skips_plumbing_tools():
    messages = [
        Message(role="user", content="do something", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="TaskCreate",
                tool_input={"subject": "test"}),
        Message(role="tool_call", content="", timestamp="T2", tool_name="TaskUpdate",
                tool_input={"taskId": "1", "status": "completed"}),
        Message(role="tool_call", content="", timestamp="T3", tool_name="ToolSearch",
                tool_input={"query": "select:Read"}),
        Message(role="tool_call", content="", timestamp="T4", tool_name="Agent",
                tool_input={"prompt": "do stuff"}),
        Message(role="assistant", content="Done.", timestamp="T5"),
    ]
    result = clean_transcript(_make_transcript(messages))
    all_msgs = [m for chunk in result.chunks for m in chunk]
    tool_names = [m.tool_name for m in all_msgs if m.role == "tool_call"]
    assert len(tool_names) == 0  # all plumbing tools skipped


# ── Turn-based chunking ──


def test_single_turn_single_chunk():
    messages = [
        Message(role="user", content="hello", timestamp="T1"),
        Message(role="assistant", content="hi", timestamp="T2"),
    ]
    result = clean_transcript(_make_transcript(messages))
    assert len(result.chunks) == 1
    assert len(result.chunks[0]) == 2


def test_multiple_turns_multiple_chunks():
    messages = [
        Message(role="user", content="first question", timestamp="T1"),
        Message(role="assistant", content="first answer", timestamp="T2"),
        Message(role="user", content="second question", timestamp="T3"),
        Message(role="assistant", content="second answer", timestamp="T4"),
        Message(role="user", content="third question", timestamp="T5"),
        Message(role="assistant", content="third answer", timestamp="T6"),
    ]
    result = clean_transcript(_make_transcript(messages))
    assert len(result.chunks) == 3
    assert result.chunks[0][0].content == "first question"
    assert result.chunks[1][0].content == "second question"
    assert result.chunks[2][0].content == "third question"


def test_turn_includes_tool_calls():
    """Tool calls between user messages belong to the preceding turn."""
    messages = [
        Message(role="user", content="fix the bug", timestamp="T1"),
        Message(role="assistant", content="Let me look.", timestamp="T2"),
        Message(role="tool_call", content="", timestamp="T3", tool_name="Read",
                tool_input={"file_path": "bug.py"}),
        Message(role="assistant", content="Found it.", timestamp="T4"),
        Message(role="user", content="great", timestamp="T5"),
        Message(role="assistant", content="Done.", timestamp="T6"),
    ]
    result = clean_transcript(_make_transcript(messages))
    assert len(result.chunks) == 2
    # First chunk: user + assistant + tool_call + assistant
    assert len(result.chunks[0]) == 4
    # Second chunk: user + assistant
    assert len(result.chunks[1]) == 2


def test_empty_messages_returns_empty_chunk():
    result = clean_transcript(_make_transcript([]))
    assert len(result.chunks) == 1
    assert result.chunks[0] == []


def test_metadata_preserved():
    messages = [Message(role="user", content="hello", timestamp="T1")]
    result = clean_transcript(_make_transcript(messages))
    assert result.metadata.session_id == "test"
    assert result.metadata.source == "claude-code"
    assert result.metadata.project == "proj"
