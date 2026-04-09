"""Extractor registry and factory."""
from __future__ import annotations

from chronicles.config import LLMConfig
from chronicles.extractors.base import BaseExtractor
from chronicles.extractors.claude_code import ClaudeCodeExtractor
from chronicles.extractors.copilot_cli import CopilotCLIExtractor

_EXTRACTORS: dict[str, type[BaseExtractor]] = {
    "copilot-cli": CopilotCLIExtractor,
    "claude-code": ClaudeCodeExtractor,
}


def get_extractor(config: LLMConfig) -> BaseExtractor:
    """Return the appropriate extractor instance for the given config."""
    cls = _EXTRACTORS.get(config.provider)
    if cls is None:
        available = ", ".join(_EXTRACTORS)
        raise ValueError(
            f"Unknown LLM provider '{config.provider}'. "
            f"Available providers: {available}"
        )
    return cls(config)
