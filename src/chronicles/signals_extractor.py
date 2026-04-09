"""Signals extractor — LLM-powered detection of agentic operational patterns."""
from __future__ import annotations

import json
import re
import subprocess

from chronicles.config import LLMConfig
from chronicles.models import CleanedTranscript, Signal, SignalsResult

_SYSTEM_PROMPT = """\
You are an agentic operations analyst. You read transcripts of AI coding agent \
sessions and detect operational patterns — both mistakes (inefficient, wrong, \
or costly behaviours) and efficient patterns (clever reuse, correct tool \
selection, good strategies).

Return ONLY valid JSON matching this schema (no markdown fences, no explanation):
{
  "signals": [
    {
      "pattern": "string — what happened, described concisely",
      "type": "mistake | efficient",
      "rule": "string — imperative instruction for future agents, e.g. 'Use the Grep tool instead of Bash grep'",
      "context": ["string — tags like tool:Grep, area:navigation, area:testing"],
      "severity": "high | low"
    }
  ],
  "demotions": ["string — verbatim rule text from CURRENT SIGNALS that is contradicted or obsolete"]
}

WHAT TO DETECT:
- mistakes: using the wrong tool (e.g. Bash grep instead of Grep tool), unnecessary retries,
  reading whole files when targeted reads suffice, ignoring available context, excessive
  clarification loops, destructive operations without confirmation
- efficient: correct tool selection, effective search strategies, good use of existing context,
  parallelising independent operations, targeted edits instead of rewrites

SEVERITY GUIDELINES:
- high: wasted significant tokens/time, caused errors, or is a systematic anti-pattern
- low: minor inefficiency or a marginal improvement opportunity

RULES:
- "type" MUST be exactly one of: mistake, efficient
- "severity" MUST be exactly one of: high, low
- "rule" must be an imperative sentence (starts with a verb)
- "context" tags follow the pattern "tool:ToolName" or "area:domain" (e.g. area:navigation, area:testing, area:git)
- Only emit signals with clear evidence from the transcript
- If no patterns are found, return {"signals": [], "demotions": []}
"""

_VALID_TYPE = {"mistake", "efficient"}
_VALID_SEVERITY = {"high", "low"}


class SignalsExtractor:
    """Uses the Claude CLI (`claude --print`) to extract agentic signals."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def _build_prompt(
        self,
        transcript: CleanedTranscript,
        existing_signals: str | None = None,
    ) -> str:
        lines: list[str] = [_SYSTEM_PROMPT]

        if existing_signals:
            lines.append("")
            lines.append("--- CURRENT SIGNALS ---")
            lines.append(existing_signals)
            lines.append("--- END CURRENT SIGNALS ---")

        lines.append("")
        lines.append("--- TRANSCRIPT ---")
        lines.append("")
        for chunk in transcript.chunks:
            for msg in chunk:
                lines.append(self._format_message(msg))
            lines.append("")
        lines.append("--- END TRANSCRIPT ---")
        lines.append(
            "Analyse the transcript above for agentic operational patterns. Return ONLY JSON."
        )
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

    def _parse_response(self, raw: str) -> SignalsResult:
        text = raw.strip()
        if not text:
            raise RuntimeError("LLM returned empty response")

        # Strip markdown fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        text = text.strip()

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise RuntimeError(f"No JSON object found in LLM response: {text[:200]}")
        text = text[start:end]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            repaired = self._repair_json(text)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Failed to parse LLM JSON: {e}\nResponse: {text[:500]}"
                ) from e

        signals_raw = data.get("signals", [])
        if not isinstance(signals_raw, list):
            signals_raw = []

        demotions_raw = data.get("demotions", [])
        if not isinstance(demotions_raw, list):
            demotions_raw = []

        signals: list[Signal] = []
        for s in signals_raw:
            if not isinstance(s, dict):
                continue
            sig_type = self._normalize_enum(s.get("type", ""), _VALID_TYPE, "mistake")
            severity = self._normalize_enum(s.get("severity", ""), _VALID_SEVERITY, "low")
            context = s.get("context", [])
            if not isinstance(context, list):
                context = []
            signals.append(Signal(
                pattern=str(s.get("pattern", "")),
                type=sig_type,
                rule=str(s.get("rule", "")),
                context=context,
                severity=severity,
            ))

        demotions = [str(d) for d in demotions_raw if d]

        return SignalsResult(signals=signals, demotions=demotions)

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt basic JSON repairs for common LLM output issues."""
        # Remove trailing commas before ] or }
        text = re.sub(r",\s*([}\]])", r"\1", text)
        return text

    @staticmethod
    def _normalize_enum(value: str, valid: set[str], default: str) -> str:
        """Normalize an enum value: lowercase, strip, fuzzy match."""
        if not isinstance(value, str):
            return default
        v = value.strip().lower()
        if v in valid:
            return v
        for candidate in valid:
            if v.startswith(candidate) or candidate.startswith(v):
                return candidate
        return default

    def extract(
        self,
        transcript: CleanedTranscript,
        existing_signals: str | None = None,
    ) -> SignalsResult:
        prompt = self._build_prompt(transcript, existing_signals)
        cmd = ["claude", "--print", "--model", self.config.model, prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr}"
            )
        return self._parse_response(result.stdout)
