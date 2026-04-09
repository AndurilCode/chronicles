"""Copilot CLI extractor — delegates extraction to GitHub Copilot CLI."""
from __future__ import annotations

import json
import subprocess

from chronicles.extractors.base import BaseExtractor
from chronicles.models import CleanedTranscript, ExtractionResult

_SYSTEM_PROMPT = """\
You are a knowledge extraction engine. You read agent session transcripts \
and extract structured knowledge for a codebase wiki.

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
        "body": "Detailed description. 3-5 sentences minimum. Explain WHAT the convention/decision/pattern is, WHY it exists, and HOW to apply it. Include code examples or file paths when relevant. This should be useful as standalone reference documentation.",
        "evidence": ["Specific evidence from the session — quote decisions, reference file paths, describe what was tried"],
        "implications": ["Concrete, actionable implications — what should developers do or avoid based on this knowledge"]
      },
      "relationships": [
        {
          "type": "contradicts | supersedes | depends-on | generalizes | related-to",
          "target": "existing-article-slug"
        }
      ]
    }
  ]
}

RULES for wiki_instructions:
- Create an article for EVERY significant convention, decision, pattern, trap, or workaround discovered in the session
- Be thorough: a session with 5 decisions should produce 5+ articles
- The "path" MUST be "wiki/articles/kebab-case-slug.md" or "wiki/queries/question-slug.md"
- "body" must be detailed (3-5 sentences minimum) — these are wiki reference pages, not summaries
- "evidence" should cite specific session details (file paths, error messages, what was tried)
- "implications" should be actionable (what to do, what to avoid, when this applies)
- For questions asked by the user and answered, use path "wiki/queries/question-slug.md"
- Use "confidence": "medium" when the user explicitly stated the knowledge; "low" when inferred by the agent
- If EXISTING WIKI ARTICLES are listed below, REUSE their tags when relevant instead of inventing new ones
- If a discovery overlaps with an existing article, use "action": "update" with the EXISTING article path instead of creating a duplicate
- Reference existing articles by their slug in your evidence or implications when relevant
- If a new article supersedes, contradicts, or depends on an EXISTING article, add a "relationships" array to the wiki_instruction
- Valid relationship types: contradicts, supersedes, depends-on, generalizes, related-to
- "target" must be the slug (filename without .md) of an existing article listed above
- Only add relationships when the connection is clear from the session evidence
"""


class CopilotCLIExtractor(BaseExtractor):
    """Uses the GitHub Copilot CLI (`copilot`) to extract transcript data."""

    def _build_prompt(
        self,
        transcript: CleanedTranscript,
        wiki_context: list[dict] | None = None,
    ) -> str:
        lines: list[str] = [_SYSTEM_PROMPT]

        # Inject existing wiki context so the LLM can reuse tags and reference articles
        if wiki_context:
            lines.append("")
            lines.append("--- EXISTING WIKI ARTICLES ---")
            for article in wiki_context:
                tags = ", ".join(article.get("tags", []))
                lines.append(
                    f"- {article['title']} (type={article.get('type', '?')}, "
                    f"tags=[{tags}], path={article.get('path', '?')})"
                )
            lines.append("--- END EXISTING WIKI ---")

        # Surface contested articles for resolution
        if wiki_context:
            contested = [a for a in wiki_context if a.get("confidence") == "contested"]
            if contested:
                lines.append("")
                lines.append("--- CONTESTED ARTICLES ---")
                lines.append(
                    "The following articles are CONTESTED — if this session provides evidence "
                    'for either side, include a wiki_instruction with action: "resolve" and the article path.'
                )
                for article in contested:
                    lines.append(f"- {article['title']} (path={article.get('path', '?')})")
                lines.append("--- END CONTESTED ---")

        lines.append("")
        lines.append("--- TRANSCRIPT ---")
        lines.append("")
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
            detail = msg.content or json.dumps(msg.tool_input) if msg.tool_input else ""
            return f"[TOOL_CALL: {msg.tool_name}] {detail}".rstrip()
        elif msg.role == "tool_result":
            if msg.content:
                return f"[TOOL_RESULT: {msg.tool_name}] {msg.content}"
            return f"[TOOL_RESULT: {msg.tool_name}] (stripped)"
        return f"[{msg.role.upper()}] {msg.content}"

    def _parse_response(self, raw: str) -> ExtractionResult:
        text = raw.strip()
        if not text:
            raise RuntimeError("LLM returned empty response")
        # Strip markdown fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        text = text.strip()
        # Find JSON object in response (LLM may prepend/append text)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise RuntimeError(f"No JSON object found in LLM response: {text[:200]}")
        text = text[start:end]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try basic repairs: trailing commas, unescaped newlines in strings
            repaired = self._repair_json(text)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse LLM JSON: {e}\nResponse: {text[:500]}") from e
        _REQUIRED_KEYS = [
            "branch", "status", "tags", "duration", "files_changed",
            "objective", "outcome", "decisions", "problems", "discovered",
            "continuity", "wiki_instructions",
        ]
        missing = [k for k in _REQUIRED_KEYS if k not in data]
        if missing:
            raise RuntimeError(
                f"LLM response missing required fields: {', '.join(missing)}"
            )
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

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt basic JSON repairs for common LLM output issues."""
        import re
        # Remove trailing commas before ] or }
        text = re.sub(r",\s*([}\]])", r"\1", text)
        return text

    def extract(
        self,
        transcript: CleanedTranscript,
        wiki_context: list[dict] | None = None,
    ) -> ExtractionResult:
        prompt = self._build_prompt(transcript, wiki_context)
        cmd = ["copilot", "-p", prompt, "--model", self.config.model]
        import logging
        _log = logging.getLogger("chronicles")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"copilot CLI failed (exit {result.returncode}): {result.stderr}"
            )
        if result.stderr:
            _log.debug("copilot stderr: %s", result.stderr[:500])
        _log.debug("copilot stdout length: %d chars", len(result.stdout))
        return self._parse_response(result.stdout)
