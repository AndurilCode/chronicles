"""Claude Code extractor — delegates extraction to the `claude` CLI."""
from __future__ import annotations

import subprocess

from chronicles.config import LLMConfig
from chronicles.extractors.base import BaseExtractor
from chronicles.extractors.copilot_cli import CopilotCLIExtractor
from chronicles.models import CleanedTranscript, ExtractionResult


class ClaudeCodeExtractor(BaseExtractor):
    """Uses the Claude Code CLI (`claude --print`) to extract transcript data."""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        # Reuse prompt-building and response-parsing from CopilotCLIExtractor
        self._helper = CopilotCLIExtractor(config)

    def extract(
        self,
        transcript: CleanedTranscript,
        wiki_context: list[dict] | None = None,
    ) -> ExtractionResult:
        prompt = self._helper._build_prompt(transcript, wiki_context)
        cmd = ["claude", "--print", "--model", self.config.model, prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr}"
            )
        return self._helper._parse_response(result.stdout)
