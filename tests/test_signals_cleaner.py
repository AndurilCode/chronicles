"""Tests for signals cleaner — preserves tool interactions, strips content."""
from chronicles.signals_cleaner import clean_transcript_for_signals
from chronicles.models import Message, Transcript


def _make_transcript(messages: list[Message]) -> Transcript:
    return Transcript(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus", messages=messages,
    )


def test_preserves_tool_call_parameters():
    messages = [
        Message(role="user", content="find the config", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "config", "path": "src/"}),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "Grep"
    assert tool_calls[0].tool_input == {"pattern": "config", "path": "src/"}


def test_preserves_tool_errors():
    messages = [
        Message(role="user", content="run tests", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "pytest"}),
        Message(role="tool_result", content="FAILED: 3 errors\nAssertionError: ...",
                timestamp="T2", tool_name="Bash"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert len(tool_results) == 1
    assert "FAILED" in tool_results[0].content


def test_strips_read_file_content():
    messages = [
        Message(role="user", content="read file", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Read",
                tool_input={"file_path": "/src/main.py"}),
        Message(role="tool_result",
                content="1\timport os\n2\timport sys\n3\t\n4\tdef main():\n5\t    pass\n",
                timestamp="T2", tool_name="Read"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0].content == "(file content stripped)"


def test_strips_grep_match_content():
    messages = [
        Message(role="user", content="search", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "def main"}),
        Message(role="tool_result",
                content="src/main.py:4:def main():\nsrc/cli.py:10:def main():",
                timestamp="T2", tool_name="Grep"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert tool_results[0].content == "(match content stripped)"


def test_truncates_large_bash_output():
    long_output = "\n".join([f"line {i}" for i in range(200)])
    messages = [
        Message(role="user", content="run", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "find . -name '*.py'"}),
        Message(role="tool_result", content=long_output, timestamp="T2", tool_name="Bash"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    lines = tool_results[0].content.strip().split("\n")
    assert len(lines) <= 12
    assert any("truncated" in line.lower() for line in lines)


def test_keeps_short_bash_output():
    messages = [
        Message(role="user", content="run", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "echo hello"}),
        Message(role="tool_result", content="hello", timestamp="T2", tool_name="Bash"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert tool_results[0].content == "hello"


def test_keeps_user_corrections():
    messages = [
        Message(role="user", content="no, not that file — check src/utils.py instead",
                timestamp="T0"),
        Message(role="assistant", content="ok", timestamp="T1"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    user_msgs = [m for chunk in result.chunks for m in chunk if m.role == "user"]
    assert len(user_msgs) == 1
    assert "not that file" in user_msgs[0].content


def test_strips_long_requirement_messages():
    long_req = "I want you to build a feature that does X. " * 50
    messages = [
        Message(role="user", content=long_req, timestamp="T0"),
        Message(role="assistant", content="ok", timestamp="T1"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    user_msgs = [m for chunk in result.chunks for m in chunk if m.role == "user"]
    assert len(user_msgs) == 1
    assert len(user_msgs[0].content) <= 100


def test_preserves_assistant_reasoning():
    messages = [
        Message(role="user", content="fix it", timestamp="T0"),
        Message(role="assistant",
                content="Let me search for the config file. I'll try src/ first.",
                timestamp="T1"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    asst_msgs = [m for chunk in result.chunks for m in chunk if m.role == "assistant"]
    assert "search for the config" in asst_msgs[0].content


def test_skips_plumbing_tools():
    messages = [
        Message(role="user", content="do something", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="TaskCreate",
                tool_input={"subject": "test"}),
        Message(role="tool_result", content="created", timestamp="T2", tool_name="TaskCreate"),
        Message(role="assistant", content="Done.", timestamp="T3"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    all_msgs = [m for chunk in result.chunks for m in chunk]
    tool_names = [m.tool_name for m in all_msgs if m.tool_name]
    assert len(tool_names) == 0


def test_chunks_on_user_messages():
    messages = [
        Message(role="user", content="find the bug", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "error"}),
        Message(role="tool_result", content="(match content stripped)", timestamp="T2",
                tool_name="Grep"),
        Message(role="user", content="now fix it", timestamp="T3"),
        Message(role="tool_call", content="", timestamp="T4", tool_name="Edit",
                tool_input={"file_path": "a.py", "old_string": "x", "new_string": "y"}),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    assert len(result.chunks) == 2


def test_chunks_on_tool_category_shift():
    """A shift from search tools to edit tools starts a new chunk."""
    messages = [
        Message(role="user", content="fix the config", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "config"}),
        Message(role="tool_result", content="", timestamp="T2", tool_name="Grep"),
        Message(role="tool_call", content="", timestamp="T3", tool_name="Glob",
                tool_input={"pattern": "*.yaml"}),
        Message(role="tool_result", content="", timestamp="T4", tool_name="Glob"),
        Message(role="assistant", content="Found it. Let me edit.", timestamp="T5"),
        Message(role="tool_call", content="", timestamp="T6", tool_name="Edit",
                tool_input={"file_path": "config.yaml", "old_string": "a", "new_string": "b"}),
        Message(role="tool_result", content="edited", timestamp="T7", tool_name="Edit"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    assert len(result.chunks) >= 2


def test_metadata_preserved():
    messages = [Message(role="user", content="hello", timestamp="T1")]
    result = clean_transcript_for_signals(_make_transcript(messages))
    assert result.metadata.session_id == "test"
    assert result.metadata.source == "claude-code"
