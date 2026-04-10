"""Core data models for the chronicles pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message in a transcript."""
    role: str              # "user" | "assistant" | "tool_call" | "tool_result"
    content: str
    timestamp: str         # ISO 8601
    tool_name: str = ""    # for tool_call / tool_result (canonical name)
    tool_input: dict = field(default_factory=dict)


@dataclass
class Transcript:
    """Parsed transcript from any source adapter."""
    session_id: str
    source: str
    project: str
    repository: str
    branch: str
    cwd: str
    timestamp_start: str
    timestamp_end: str
    model: str
    messages: list[Message]

    @property
    def date(self) -> str:
        if self.timestamp_start:
            return self.timestamp_start[:10]
        return ""


@dataclass
class TranscriptMetadata:
    """Transcript identity without messages — used in CleanedTranscript."""
    session_id: str
    source: str
    project: str
    repository: str
    branch: str
    cwd: str
    timestamp_start: str
    timestamp_end: str
    model: str


@dataclass
class CleanedTranscript:
    """Transcript after cleaning: filtered tool results, chunked by turns."""
    metadata: TranscriptMetadata
    chunks: list[list[Message]]


@dataclass
class ExtractionResult:
    """Structured output from the LLM extractor."""
    branch: str
    status: str            # complete | partial | failed | exploratory
    tags: list[str]
    duration: str
    files_changed: list[str]
    objective: str
    outcome: str
    decisions: list[dict[str, str]]
    problems: list[dict[str, Any]]
    discovered: list[dict[str, str]]
    continuity: dict[str, list[str]]
    wiki_instructions: list[dict[str, Any]]

    @property
    def slug(self) -> str:
        return self.branch.replace("/", "-").replace("\\", "-")


@dataclass
class Signal:
    """A single agentic operational signal."""
    pattern: str        # what happened
    type: str           # "mistake" | "efficient" | "steer"
    rule: str           # imperative instruction for future agents
    context: list[str]  # tags like "tool:Grep", "area:navigation"
    severity: str       # "high" or "low"


@dataclass
class SignalsResult:
    """Output from the signals extractor."""
    signals: list[Signal]
    demotions: list[str]   # existing rules to remove (contradicted)
