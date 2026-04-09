"""Copilot CLI extractor — delegates extraction to GitHub Copilot CLI."""
from __future__ import annotations

import json
import subprocess

from chronicles.extractors.base import BaseExtractor
from chronicles.models import CleanedTranscript, ExtractionResult

_SYSTEM_PROMPT = """\
You are a knowledge extraction engine. You read agent session transcripts \
and extract structured knowledge.

Return ONLY valid JSON matching this schema (no markdown fences, no explanation):
{
  "branch": "string — branch name or short description of work",
  "status": "complete | partial | failed | exploratory",
  "tags": ["string"],
  "duration": "string — estimated duration",
  "files_changed": ["string — file paths touched"],
  "objective": "string — what the session set out to do",
  "outcome": "string — what was actually achieved",
  "decisions": [{"description": "what was decided", "rationale": "why"}],
  "problems": [{"description": "what went wrong", "root_cause": "why it happened", "dead_end": false}],
  "discovered": [{"type": "convention|missing-context|workaround|pattern|trap", "description": "what was found"}],
  "continuity": {
    "unfinished": ["things not completed"],
    "open_questions": ["questions still open"],
    "next": ["suggested next steps"]
  },
  "wiki_instructions": [
    {
      "action": "create",
      "path": "wiki/articles/kebab-case-slug.md",
      "data": {
        "title": "Human Readable Title",
        "type": "convention | decision | pattern | trap | workaround | concept",
        "confidence": "low | medium",
        "tags": ["string"],
        "body": "one paragraph description",
        "evidence": ["how this was discovered"],
        "implications": ["what this means for future work"]
      }
    }
  ]
}

IMPORTANT for wiki_instructions:
- Create an article for each significant convention, decision, pattern, trap, or workaround discovered
- The "path" MUST be a file path like "wiki/articles/my-article-name.md" (kebab-case, .md extension)
- For questions asked by the user, use "wiki/queries/question-slug.md"
- Always include at least one wiki_instruction if any knowledge was discovered
"""


class CopilotCLIExtractor(BaseExtractor):
    """Uses the GitHub Copilot CLI (`copilot`) to extract transcript data."""

    def _build_prompt(self, transcript: CleanedTranscript) -> str:
        lines: list[str] = [_SYSTEM_PROMPT, "", "--- TRANSCRIPT ---", ""]
        for chunk in transcript.chunks:
            for msg in chunk:
                lines.append(self._format_message(msg))
            lines.append("")
        lines.append("--- END TRANSCRIPT ---")
        lines.append("Extract structured knowledge from the transcript above. Return ONLY JSON.")
        return "\n".join(lines)

    @staticmethod
    def _format_message(msg) -> str:
        if msg.role == "user":
            return f"[USER] {msg.content}"
        elif msg.role == "assistant":
            return f"[ASSISTANT] {msg.content}"
        elif msg.role == "tool_call":
            return f"[TOOL_CALL: {msg.tool_name}] {json.dumps(msg.tool_input)}"
        elif msg.role == "tool_result":
            if msg.content:
                return f"[TOOL_RESULT: {msg.tool_name}] {msg.content}"
            return f"[TOOL_RESULT: {msg.tool_name}] (stripped)"
        return f"[{msg.role.upper()}] {msg.content}"

    def _parse_response(self, raw: str) -> ExtractionResult:
        text = raw.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        text = text.strip()
        data = json.loads(text)
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
