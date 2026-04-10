"""Signals extractor — LLM-powered detection of agentic operational patterns."""
from __future__ import annotations

import json
import re
import subprocess

from chronicles.config import LLMConfig
from chronicles.models import CleanedTranscript, Signal, SignalsResult

_AGENT_PROMPT = """\
You are analyzing an AI coding agent's TOOL USAGE BEHAVIOR. You look at the \
sequence of tool calls and their results to find operational mistakes and \
patterns that future agents should know about.

You ONLY care about what the agent DID with tools — not what it discussed, \
designed, or built. Ignore all conversation content about architecture, design \
decisions, or implementation details. Focus exclusively on the tool call/result \
sequence.

Return ONLY valid JSON (no markdown fences, no explanation):
{
  "signals": [
    {
      "pattern": "string — the tool sequence that reveals the mistake or pattern",
      "type": "mistake | efficient",
      "rule": "string — short imperative rule (under 100 chars)",
      "context": ["string — tags"],
      "severity": "high | low"
    }
  ],
  "demotions": ["string — verbatim rule text from CURRENT SIGNALS contradicted by this session"]
}

WHAT TO LOOK FOR in the tool call sequence:

1. WRONG COMMAND: Agent ran a command that failed, then tried a different one that worked.
   Example: `pytest` failed → `uv run python -m pytest` worked.
   Signal: "Run tests with `uv run python -m pytest`, not bare `pytest`"

2. WRONG TOOL: Agent used Bash for something a dedicated tool does better.
   Example: Bash(`grep -r foo .`) → then Grep(pattern="foo")

3. WRONG PATH: Agent searched a non-existent directory, then found it elsewhere.
   Example: Read("src/utils.py") → ERROR → Read("src/chronicles/utils.py") → OK

4. HALLUCINATED PATH/COMMAND: Agent tried to read/run something that doesn't exist.

5. WASTED RETRIES: 3+ attempts with variations before succeeding.

6. EFFICIENT SHORTCUT: Agent navigated directly to the right location.

DO NOT EMIT:
- Anything about what was discussed, designed, or decided in conversation
- Anything about code architecture or implementation patterns
- Generic agent advice that applies to ANY codebase

HARD FILTER: Every rule MUST reference a concrete path, command, or structure \
FROM THIS REPO. If you could paste the rule into a different project and it \
would still make sense, it is too generic — reject it.

DEMOTIONS: If any CURRENT SIGNAL is contradicted by tool behavior in this session, \
include its EXACT rule text in "demotions".

Aim for 0-3 signals. Zero is the CORRECT answer for most sessions.
"""

_STEERS_PROMPT = """\
You are extracting HUMAN RULES from a coding session transcript. Look ONLY at \
[USER] messages for moments where the user CORRECTS the agent or gives an \
EXPLICIT DIRECTIVE about how to work.

Return ONLY valid JSON (no markdown fences, no explanation):
{
  "signals": [
    {
      "pattern": "string — what the user said",
      "type": "steer",
      "rule": "string — the rule the user established (under 100 chars)",
      "context": ["string — tags"],
      "severity": "high"
    }
  ],
  "demotions": []
}

WHAT IS A STEER:
- User corrects agent behavior: "no, not that — use X instead"
- User sets a rule: "always use X for Y", "never do X", "stop doing X"
- User rejects an approach and redirects to a specific alternative
- User gives an explicit preference for how work should be done

WHAT IS NOT A STEER:
- User asking questions or giving requirements ("add feature X", "build Y")
- User providing context or explaining the codebase
- User approving or confirming ("ok", "looks good", "yes")
- User asking for status or progress
- Generic conversation that doesn't establish a rule

Aim for 0-3 steers per session. Zero is correct for most sessions.
"""

_VALID_TYPE = {"mistake", "efficient", "steer"}
_VALID_SEVERITY = {"high", "low"}


def _summarize_params(tool_name: str, tool_input: dict) -> str:
    """Show only the key parameter — enough to detect wrong paths/commands."""
    if not tool_input:
        return ""
    if tool_name == "Read":
        return tool_input.get("file_path", "")
    if tool_name == "Write":
        return tool_input.get("file_path", "")
    if tool_name == "Edit":
        return tool_input.get("file_path", "")
    if tool_name == "Grep":
        p = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return f'pattern="{p}" path={path}' if path else f'pattern="{p}"'
    if tool_name == "Glob":
        return f'pattern="{tool_input.get("pattern", "")}"'
    if tool_name == "Bash":
        return tool_input.get("command", "")[:120]
    return ""


def _summarize_result(tool_name: str, content: str) -> str:
    """Classify result as OK, EMPTY, ERROR — strip content details."""
    if not content:
        return "EMPTY"
    c = content.strip().lower()
    if "error" in c or "fail" in c or "not found" in c or "does not exist" in c:
        return f"ERROR: {content.split(chr(10))[0][:150]}"
    if content in ("(file content stripped)", "(match content stripped)"):
        return "OK"
    if tool_name == "Bash":
        lines = content.strip().split("\n")
        if len(lines) <= 3:
            return content.strip()[:150]
        return f"OK ({len(lines)} lines)"
    return "OK"


class SignalsExtractor:
    """Uses the Claude CLI (`claude --print`) to extract agentic signals."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def _build_prompt(
        self,
        system: str,
        transcript: CleanedTranscript,
        existing_signals: str | None = None,
    ) -> str:
        lines: list[str] = [system]

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
                formatted = self._format_message(msg)
                if formatted:
                    lines.append(formatted)
            lines.append("")
        lines.append("--- END TRANSCRIPT ---")
        lines.append("Return ONLY JSON.")
        return "\n".join(lines)

    @staticmethod
    def _format_message(msg) -> str:
        if msg.role == "user":
            return f"[USER] {msg.content}"
        elif msg.role == "assistant":
            return f"[AGENT] {msg.content}" if msg.content else ""
        elif msg.role == "tool_call":
            params = _summarize_params(msg.tool_name, msg.tool_input)
            return f"[CALL: {msg.tool_name}] {params}".rstrip()
        elif msg.role == "tool_result":
            outcome = _summarize_result(msg.tool_name, msg.content)
            return f"[RESULT: {msg.tool_name}] {outcome}"
        return ""

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

    def _call_llm(self, prompt: str) -> str:
        cmd = ["claude", "--print", "--model", self.config.model, prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr}"
            )
        return result.stdout

    def extract(
        self,
        transcript: CleanedTranscript,
        existing_signals: str | None = None,
    ) -> SignalsResult:
        from concurrent.futures import ThreadPoolExecutor
        import logging
        _log = logging.getLogger("chronicles")

        agent_prompt = self._build_prompt(_AGENT_PROMPT, transcript, existing_signals)
        steers_prompt = self._build_prompt(_STEERS_PROMPT, transcript)

        with ThreadPoolExecutor(max_workers=2) as pool:
            agent_future = pool.submit(self._call_llm, agent_prompt)
            steers_future = pool.submit(self._call_llm, steers_prompt)

        agent_result = self._parse_response(agent_future.result())

        try:
            steers_result = self._parse_response(steers_future.result())
        except RuntimeError:
            _log.warning("Steers extraction failed, continuing with agent signals only")
            steers_result = SignalsResult(signals=[], demotions=[])

        return SignalsResult(
            signals=agent_result.signals + steers_result.signals,
            demotions=agent_result.demotions + steers_result.demotions,
        )
