"""Signals cleaner — preserves tool interactions, strips content."""
from __future__ import annotations

import logging

from chronicles.models import (
    Message, Transcript, CleanedTranscript, TranscriptMetadata,
)

log = logging.getLogger("chronicles")

SKIP_TOOLS = frozenset({
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    "TaskStop", "TaskOutput", "ToolSearch",
    "Skill", "Agent", "SendMessage",
})

STRIP_CONTENT_TOOLS = frozenset({"Read", "Glob"})
STRIP_MATCH_TOOLS = frozenset({"Grep"})

_BASH_MAX_LINES = 20
_USER_MAX_LEN = 300  # keep enough for corrections/steers
_ASSISTANT_MAX_LEN = 100

_SEARCH_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash"})
_EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def clean_transcript_for_signals(transcript: Transcript) -> CleanedTranscript:
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
    chunks = _chunk_by_operations(filtered)
    return CleanedTranscript(metadata=metadata, chunks=chunks)


def _filter_messages(messages: list[Message]) -> list[Message]:
    result: list[Message] = []
    for msg in messages:
        if msg.tool_name in SKIP_TOOLS:
            continue
        if msg.role == "tool_result" and msg.tool_name in STRIP_CONTENT_TOOLS:
            result.append(Message(
                role=msg.role, content="(file content stripped)",
                timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
            continue
        if msg.role == "tool_result" and msg.tool_name in STRIP_MATCH_TOOLS:
            result.append(Message(
                role=msg.role, content="(match content stripped)",
                timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
            continue
        if msg.role == "tool_result" and msg.tool_name == "Bash":
            result.append(Message(
                role=msg.role, content=_truncate_bash(msg.content),
                timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
            continue
        if msg.role == "user" and len(msg.content) > _USER_MAX_LEN:
            result.append(Message(
                role=msg.role, content=msg.content[:_USER_MAX_LEN],
                timestamp=msg.timestamp,
            ))
            continue
        # Strip assistant messages to brief context — we only care about tool sequences
        if msg.role == "assistant" and len(msg.content) > _ASSISTANT_MAX_LEN:
            result.append(Message(
                role=msg.role, content=msg.content[:_ASSISTANT_MAX_LEN],
                timestamp=msg.timestamp,
            ))
            continue
        result.append(msg)
    return result


def _truncate_bash(content: str) -> str:
    lines = content.split("\n")
    if len(lines) <= _BASH_MAX_LINES:
        return content
    head = lines[:5]
    tail = lines[-5:]
    return "\n".join(head + [f"... ({len(lines) - 10} lines truncated) ..."] + tail)


def _tool_category(tool_name: str) -> str:
    if tool_name in _EDIT_TOOLS:
        return "edit"
    if tool_name in _SEARCH_TOOLS:
        return "search"
    return "other"


def _chunk_by_operations(messages: list[Message]) -> list[list[Message]]:
    if not messages:
        return [[]]
    chunks: list[list[Message]] = []
    current: list[Message] = []
    prev_category: str = ""

    for msg in messages:
        if msg.role == "user" and current:
            chunks.append(current)
            current = []
            prev_category = ""
        if msg.role == "tool_call" and msg.tool_name:
            cat = _tool_category(msg.tool_name)
            if prev_category and cat != prev_category and current:
                chunks.append(current)
                current = []
            prev_category = cat
        current.append(msg)

    if current:
        chunks.append(current)
    return chunks if chunks else [[]]
