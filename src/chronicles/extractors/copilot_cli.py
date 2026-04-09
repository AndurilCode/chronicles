"""Copilot CLI extractor — delegates extraction to GitHub Copilot CLI."""
from __future__ import annotations

import json
import subprocess

from chronicles.config import LLMConfig
from chronicles.extractors.base import BaseExtractor
from chronicles.models import CleanedTranscript, ExtractionResult

_SYSTEM_PROMPT = """\
You are a software engineering assistant. Analyze the following conversation \
transcript between a developer and an AI coding assistant. Extract structured \
information and return it as valid JSON matching this schema exactly:

{
  "branch": "<git branch name>",
  "status": "<complete|partial|failed|exploratory>",
  "tags": ["<tag>", ...],
  "duration": "<human readable duration>",
  "files_changed": ["<path>", ...],
  "objective": "<one sentence summary of the goal>",
  "outcome": "<one sentence summary of what was achieved>",
  "decisions": [{"decision": "<text>", "rationale": "<text>"}, ...],
  "problems": [{"problem": "<text>", "resolution": "<text>"}, ...],
  "discovered": [{"item": "<text>", "context": "<text>"}, ...],
  "continuity": {
    "unfinished": ["<item>", ...],
    "open_questions": ["<question>", ...],
    "next": ["<action>", ...]
  },
  "wiki_instructions": [{"title": "<text>", "content": "<text>"}, ...]
}

Return only the JSON object — no markdown fences, no prose.
"""


class CopilotCLIExtractor(BaseExtractor):
    """Uses the GitHub Copilot CLI (`copilot`) to extract transcript data."""

    def _format_message(self, role: str, content: str) -> str:
        label = role.upper()
        return f"[{label}]: {content}"

    def _build_prompt(self, transcript: CleanedTranscript) -> str:
        lines: list[str] = [_SYSTEM_PROMPT, "", "TRANSCRIPT:", ""]
        for chunk in transcript.chunks:
            for msg in chunk:
                lines.append(self._format_message(msg.role, msg.content))
            lines.append("")
        return "\n".join(lines)

    def _parse_response(self, raw: str) -> ExtractionResult:
        data = json.loads(raw)
        return ExtractionResult(
            branch=data["branch"],
            status=data["status"],
            tags=data["tags"],
            duration=data["duration"],
            files_changed=data["files_changed"],
            objective=data["objective"],
            outcome=data["outcome"],
            decisions=data["decisions"],
            problems=data["problems"],
            discovered=data["discovered"],
            continuity=data["continuity"],
            wiki_instructions=data["wiki_instructions"],
        )

    def extract(self, transcript: CleanedTranscript) -> ExtractionResult:
        prompt = self._build_prompt(transcript)
        cmd = ["copilot", "-p", prompt, "--model", self.config.model]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"copilot CLI failed (exit {result.returncode}): {result.stderr}"
            )
        return self._parse_response(result.stdout)
