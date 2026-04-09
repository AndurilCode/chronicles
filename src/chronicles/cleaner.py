"""Transcript cleaner — filters tool noise and chunks by turns."""
from __future__ import annotations

import logging

from chronicles.models import (
    Message, Transcript, CleanedTranscript, TranscriptMetadata,
)

log = logging.getLogger("chronicles")

# Tool results to strip (high-volume, low-signal output)
STRIP_RESULT_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash", "ls", "cat"})

# Tool calls whose full input should be replaced with a brief summary
SUMMARIZE_INPUT_TOOLS = frozenset({
    "Read", "Grep", "Glob", "Bash", "ls", "cat",
    "Write", "Edit", "NotebookEdit",
})

# Internal plumbing tools — skip entirely (not knowledge-bearing)
SKIP_TOOLS = frozenset({
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    "TaskStop", "TaskOutput", "ToolSearch",
    "Skill", "Agent", "SendMessage",
})


def clean_transcript(transcript: Transcript) -> CleanedTranscript:
    """Filter tool noise and chunk by turns."""
    metadata = TranscriptMetadata(
        session_id=transcript.session_id,
        source=transcript.source,
        project=transcript.project,
        repository=transcript.repository,
        branch=transcript.branch,
        cwd=transcript.cwd,
        timestamp_start=transcript.timestamp_start,
        timestamp_end=transcript.timestamp_end,
        model=transcript.model,
    )
    filtered = _filter_messages(transcript.messages)
    chunks = _chunk_by_turns(filtered)
    return CleanedTranscript(metadata=metadata, chunks=chunks)


def _filter_messages(messages: list[Message]) -> list[Message]:
    """Filter tool calls and results based on signal value."""
    result: list[Message] = []
    for msg in messages:
        # Skip internal plumbing tools entirely
        if msg.tool_name in SKIP_TOOLS:
            continue

        # Strip tool result content for high-volume tools
        if msg.role == "tool_result" and msg.tool_name in STRIP_RESULT_TOOLS:
            result.append(Message(
                role=msg.role, content="", timestamp=msg.timestamp,
                tool_name=msg.tool_name,
            ))
            continue

        # Summarize tool call inputs for tools with large inputs
        if msg.role == "tool_call" and msg.tool_name in SUMMARIZE_INPUT_TOOLS:
            summary = _summarize_tool_input(msg.tool_name, msg.tool_input)
            result.append(Message(
                role=msg.role, content=summary, timestamp=msg.timestamp,
                tool_name=msg.tool_name, tool_input={},
            ))
            continue

        result.append(msg)
    return result


def _summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create a brief summary of a tool call's input."""
    if tool_name in ("Read", "Write", "NotebookEdit"):
        return tool_input.get("file_path", tool_input.get("path", ""))
    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")[:60]
        new = tool_input.get("new_string", "")[:60]
        return f"{path}: '{old}' -> '{new}'"
    if tool_name == "Bash":
        return tool_input.get("command", "")[:120]
    if tool_name == "Grep":
        return f"pattern={tool_input.get('pattern', '')}"
    if tool_name == "Glob":
        return f"pattern={tool_input.get('pattern', '')}"
    return ""


def _chunk_by_turns(messages: list[Message]) -> list[list[Message]]:
    """Split messages into turn-based chunks.

    A turn starts with a user message and includes all subsequent
    assistant/tool messages until the next user message.
    """
    if not messages:
        return [[]]

    chunks: list[list[Message]] = []
    current: list[Message] = []

    for msg in messages:
        if msg.role == "user" and current:
            chunks.append(current)
            current = []
        current.append(msg)

    if current:
        chunks.append(current)

    return chunks if chunks else [[]]
