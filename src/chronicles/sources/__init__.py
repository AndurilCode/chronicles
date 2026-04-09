"""Source adapter registry and auto-detection."""
from __future__ import annotations
from pathlib import Path

from chronicles.sources.base import BaseSource
from chronicles.sources.claude_code import ClaudeCodeSource
from chronicles.sources.copilot_cli import CopilotCLISource
from chronicles.sources.copilot_vscode import CopilotVSCodeSource

ALL_SOURCES: list[BaseSource] = [
    ClaudeCodeSource(),
    CopilotCLISource(),
    CopilotVSCodeSource(),
]


def detect_source(session_path: Path) -> BaseSource:
    for source in ALL_SOURCES:
        if source.sniff(session_path):
            return source
    raise ValueError(f"Could not detect source for {session_path}")


def get_source(key: str) -> BaseSource:
    for source in ALL_SOURCES:
        if source.key == key:
            return source
    raise ValueError(f"Unknown source: {key}")
