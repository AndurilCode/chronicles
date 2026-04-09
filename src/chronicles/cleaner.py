"""Transcript cleaner — filters tool results and chunks by turns."""
from __future__ import annotations
from chronicles.models import (
    Message, Transcript, CleanedTranscript, TranscriptMetadata,
)

STRIP_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash", "ls", "cat"})
KEEP_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})

def clean_transcript(transcript: Transcript) -> CleanedTranscript:
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
    filtered = _filter_tool_results(transcript.messages)
    chunks = _chunk_by_turns(filtered)
    return CleanedTranscript(metadata=metadata, chunks=chunks)

def _filter_tool_results(messages: list[Message]) -> list[Message]:
    result: list[Message] = []
    for msg in messages:
        if msg.role == "tool_result" and msg.tool_name in STRIP_TOOLS:
            result.append(Message(
                role=msg.role, content="", timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
        else:
            result.append(msg)
    return result

def _chunk_by_turns(messages: list[Message]) -> list[list[Message]]:
    if not messages:
        return [[]]
    return [messages]
