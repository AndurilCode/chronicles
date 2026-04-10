"""LLM extractor — builds the extraction prompt and parses the response.

Provider-agnostic: delegates the actual LLM call to ``call_llm()``.
"""
from __future__ import annotations

import json

from chronicles.config import LLMConfig
from chronicles.llm_utils import call_llm, parse_llm_json, normalize_enum
from chronicles.models import CleanedTranscript, ExtractionResult

_SYSTEM_PROMPT = """\
You are a knowledge extraction engine. You read agent session transcripts \
and extract structured knowledge for a codebase wiki.

Return ONLY valid JSON matching this schema (no markdown fences, no explanation):
{
  "branch": "string — branch name or short description of work",
  "status": "complete | partial | failed | exploratory",
  "tags": ["string"],
  "duration": "string — estimated duration like 30min or 2h",
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
        "body": "First sentence: WHAT is this convention/decision/pattern. Second sentence: WHY it exists or why this choice was made. Third sentence: HOW to apply it or what developers should do. Optional 4th-5th sentences: caveats, edge cases, or code examples.",
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

EXAMPLE OUTPUT (for a session that implemented OAuth token refresh):
{
  "branch": "feat/oauth-refresh",
  "status": "complete",
  "tags": ["oauth", "auth", "tokens"],
  "duration": "45min",
  "files_changed": ["src/auth/refresh.py", "tests/test_refresh.py"],
  "objective": "Implement OAuth token refresh for API connections",
  "outcome": "Working refresh flow with 3 new tests, discovered scope delimiter issue",
  "decisions": [
    {"description": "Refresh tokens before expiry instead of on 401", "rationale": "Avoids retry complexity, trades ~5% unnecessary refreshes"}
  ],
  "problems": [
    {"description": "token_endpoint returns 403 when scope includes offline_access", "root_cause": "Provider expects space-delimited scopes, we sent comma-delimited", "dead_end": false}
  ],
  "discovered": [
    {"type": "convention", "description": "All connection configs use _connection suffix pattern"},
    {"type": "trap", "description": "Scope parameter must be space-delimited, not comma-delimited"}
  ],
  "continuity": {
    "unfinished": ["Error UX when refresh fails"],
    "open_questions": ["Should expired tokens auto-disconnect?"],
    "next": ["Add backoff to rate-limit retry"]
  },
  "wiki_instructions": [
    {
      "action": "create",
      "path": "wiki/articles/scope-delimiter-trap.md",
      "data": {
        "title": "OAuth Scope Delimiter Trap",
        "type": "trap",
        "confidence": "medium",
        "tags": ["oauth", "auth"],
        "body": "OAuth scope parameters must be space-delimited, not comma-delimited. Several providers silently accept comma-delimited scopes but return 403 when certain scopes (like offline_access) are included. This was discovered when the token endpoint rejected refresh requests with comma-separated scope strings.",
        "evidence": ["token_endpoint returned 403 with scope=openid,offline_access", "Fixed by changing to scope=openid offline_access in src/auth/refresh.py"],
        "implications": ["Always use space-delimited OAuth scopes", "Test scope strings with offline_access included"]
      }
    }
  ]
}

WHEN TO CREATE AN ARTICLE — create one when:
- A decision was explicitly made between alternatives (type: decision)
- A naming convention, coding pattern, or project rule was stated or discovered (type: convention)
- A reusable architectural or implementation pattern emerged (type: pattern)
- A non-obvious gotcha, pitfall, or footgun was encountered (type: trap)
- A temporary fix or hack was applied (type: workaround)
- Do NOT create articles for routine operations (running tests, reading files, installing packages)

RULES:
- "path" MUST be "wiki/articles/kebab-case-slug.md" or "wiki/queries/question-slug.md"
- "body": sentence 1 = WHAT, sentence 2 = WHY, sentence 3 = HOW. Minimum 3 sentences.
- "evidence": cite specific file paths, error messages, or decisions from the session
- "implications": what should developers do or avoid
- "confidence": use "medium" when the user explicitly stated it; "low" when inferred
- "type" MUST be exactly one of: convention, decision, pattern, trap, workaround, concept
- "status" MUST be exactly one of: complete, partial, failed, exploratory
- Tags should include 1-2 broad domain tags (e.g. architecture, extraction, parsing, pipeline, wiki, testing) plus 1-2 specific tags. Broad tags help articles cluster into categories; specific tags distinguish them.
- If EXISTING WIKI ARTICLES are listed below, REUSE their tags and use "action": "update" for overlapping topics
- If a new article supersedes or depends on an EXISTING article, add "relationships" with the existing slug as target
- Valid relationship types: contradicts, supersedes, depends-on, generalizes, related-to
- "target" in relationships must be the slug of an existing article listed above — do NOT invent slugs for articles that don't exist
"""


class Extractor:
    """Builds the extraction prompt, calls the LLM, and parses the JSON response."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

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

    # Valid enum values for normalization
    _VALID_STATUS = {"complete", "partial", "failed", "exploratory"}
    _VALID_ARTICLE_TYPE = {"convention", "decision", "pattern", "trap", "workaround", "concept"}
    _VALID_CONFIDENCE = {"low", "medium"}
    _VALID_DISCOVERED_TYPE = {"convention", "missing-context", "workaround", "pattern", "trap"}

    def _parse_response(self, raw: str) -> ExtractionResult:
        data = parse_llm_json(raw)

        # Validate required keys
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

        # Normalize and validate
        data["status"] = normalize_enum(data["status"], self._VALID_STATUS, "complete")
        data["tags"] = self._ensure_list(data["tags"])
        data["files_changed"] = self._ensure_list(data["files_changed"])
        data["decisions"] = self._ensure_list(data["decisions"])
        data["problems"] = self._ensure_list(data["problems"])
        data["discovered"] = self._ensure_list(data["discovered"])
        data["wiki_instructions"] = self._ensure_list(data["wiki_instructions"])

        # Normalize discovered types
        for d in data["discovered"]:
            if isinstance(d, dict) and "type" in d:
                d["type"] = normalize_enum(d["type"], self._VALID_DISCOVERED_TYPE, "pattern")

        # Normalize wiki_instructions data fields
        for instr in data["wiki_instructions"]:
            if not isinstance(instr, dict):
                continue
            instr_data = instr.get("data", {})
            if isinstance(instr_data, dict):
                if "type" in instr_data:
                    instr_data["type"] = normalize_enum(
                        instr_data["type"], self._VALID_ARTICLE_TYPE, "pattern"
                    )
                if "confidence" in instr_data:
                    instr_data["confidence"] = normalize_enum(
                        instr_data["confidence"], self._VALID_CONFIDENCE, "low"
                    )
                instr_data["tags"] = self._ensure_list(instr_data.get("tags", []))
                instr_data["evidence"] = self._ensure_list(instr_data.get("evidence", []))
                instr_data["implications"] = self._ensure_list(instr_data.get("implications", []))

        # Ensure continuity has expected structure
        cont = data.get("continuity", {})
        if not isinstance(cont, dict):
            cont = {}
        data["continuity"] = {
            "unfinished": self._ensure_list(cont.get("unfinished", [])),
            "open_questions": self._ensure_list(cont.get("open_questions", [])),
            "next": self._ensure_list(cont.get("next", [])),
        }

        return ExtractionResult(
            branch=str(data["branch"]),
            status=data["status"],
            tags=data["tags"],
            duration=str(data["duration"]),
            files_changed=data["files_changed"],
            objective=str(data["objective"]),
            outcome=str(data["outcome"]),
            decisions=data["decisions"],
            problems=data["problems"],
            discovered=data["discovered"],
            continuity=data["continuity"],
            wiki_instructions=data["wiki_instructions"],
        )

    @staticmethod
    def _ensure_list(value) -> list:
        """Ensure a value is a list. Wraps strings/dicts in a list, returns [] for None."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (str, dict)):
            return [value]
        return []

    def extract(
        self,
        transcript: CleanedTranscript,
        wiki_context: list[dict] | None = None,
    ) -> ExtractionResult:
        prompt = self._build_prompt(transcript, wiki_context)
        raw = call_llm(prompt, self.config)
        return self._parse_response(raw)
