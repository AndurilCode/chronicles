# Agentic Signals Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a parallel pipeline that extracts agentic operational patterns from session transcripts and injects them as natural language rules into future sessions via SIGNALS.md.

**Architecture:** A signals pipeline (cleaner, extractor, writer) runs independently from the wiki pipeline, sharing only source parsers and config. New CLI command `chronicles signals` and two hook scripts handle ingestion and injection.

**Tech Stack:** Python, dataclasses, subprocess (LLM CLI), argparse, pytest

**Spec:** `docs/superpowers/specs/2026-04-10-agentic-signals-design.md`

---

### Task 1: Add SignalResult model

**Files:**
- Modify: `src/chronicles/models.py:60-78`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py — append to existing file

from chronicles.models import Signal, SignalsResult


def test_signal_dataclass():
    s = Signal(
        pattern="Agent used Bash grep instead of Grep tool",
        type="mistake",
        rule="Use the Grep tool instead of Bash with grep or rg",
        context=["tool:Bash", "tool:Grep"],
        severity="high",
    )
    assert s.type == "mistake"
    assert s.severity == "high"


def test_signals_result_dataclass():
    r = SignalsResult(
        signals=[
            Signal(
                pattern="Searched src/ three times before finding module in lib/",
                type="mistake",
                rule="Check lib/ for utility modules",
                context=["area:navigation"],
                severity="low",
            ),
        ],
        demotions=["Use find instead of Glob for deep searches"],
    )
    assert len(r.signals) == 1
    assert len(r.demotions) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_models.py::test_signal_dataclass tests/test_models.py::test_signals_result_dataclass -v`
Expected: FAIL with `ImportError: cannot import name 'Signal'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/chronicles/models.py` after the `ExtractionResult` class:

```python
@dataclass
class Signal:
    """A single agentic operational signal."""
    pattern: str        # what happened
    type: str           # "mistake" or "efficient"
    rule: str           # imperative instruction for future agents
    context: list[str]  # tags like "tool:Grep", "area:navigation"
    severity: str       # "high" or "low"


@dataclass
class SignalsResult:
    """Output from the signals extractor."""
    signals: list[Signal]
    demotions: list[str]   # existing rules to remove (contradicted)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_models.py::test_signal_dataclass tests/test_models.py::test_signals_result_dataclass -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/models.py tests/test_models.py
git commit -m "feat(signals): add Signal and SignalsResult data models"
```

---

### Task 2: Implement signals cleaner

**Files:**
- Create: `src/chronicles/signals_cleaner.py`
- Create: `tests/test_signals_cleaner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signals_cleaner.py
"""Tests for signals cleaner — preserves tool interactions, strips content."""
from chronicles.signals_cleaner import clean_transcript_for_signals
from chronicles.models import Message, Transcript


def _make_transcript(messages: list[Message]) -> Transcript:
    return Transcript(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus", messages=messages,
    )


# ── Preserves tool calls with parameters ──


def test_preserves_tool_call_parameters():
    messages = [
        Message(role="user", content="find the config", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "config", "path": "src/"}),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "Grep"
    assert tool_calls[0].tool_input == {"pattern": "config", "path": "src/"}


def test_preserves_tool_errors():
    messages = [
        Message(role="user", content="run tests", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "pytest"}),
        Message(role="tool_result", content="FAILED: 3 errors\nAssertionError: ...",
                timestamp="T2", tool_name="Bash"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert len(tool_results) == 1
    assert "FAILED" in tool_results[0].content


# ── Strips file content from Read results ──


def test_strips_read_file_content():
    messages = [
        Message(role="user", content="read file", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Read",
                tool_input={"file_path": "/src/main.py"}),
        Message(role="tool_result",
                content="1\timport os\n2\timport sys\n3\t\n4\tdef main():\n5\t    pass\n",
                timestamp="T2", tool_name="Read"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0].content == "(file content stripped)"


def test_strips_grep_match_content():
    messages = [
        Message(role="user", content="search", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "def main"}),
        Message(role="tool_result",
                content="src/main.py:4:def main():\nsrc/cli.py:10:def main():",
                timestamp="T2", tool_name="Grep"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert tool_results[0].content == "(match content stripped)"


# ── Truncates large bash output ──


def test_truncates_large_bash_output():
    long_output = "\n".join([f"line {i}" for i in range(200)])
    messages = [
        Message(role="user", content="run", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "find . -name '*.py'"}),
        Message(role="tool_result", content=long_output, timestamp="T2", tool_name="Bash"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    lines = tool_results[0].content.strip().split("\n")
    # Should have first 5, truncation marker, last 5
    assert len(lines) <= 12
    assert any("truncated" in line.lower() for line in lines)


def test_keeps_short_bash_output():
    messages = [
        Message(role="user", content="run", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Bash",
                tool_input={"command": "echo hello"}),
        Message(role="tool_result", content="hello", timestamp="T2", tool_name="Bash"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert tool_results[0].content == "hello"


# ── Keeps user corrections, strips requirements ──


def test_keeps_user_corrections():
    messages = [
        Message(role="user", content="no, not that file — check src/utils.py instead",
                timestamp="T0"),
        Message(role="assistant", content="ok", timestamp="T1"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    user_msgs = [m for chunk in result.chunks for m in chunk if m.role == "user"]
    assert len(user_msgs) == 1
    assert "not that file" in user_msgs[0].content


def test_strips_long_requirement_messages():
    long_req = "I want you to build a feature that does X. " * 50
    messages = [
        Message(role="user", content=long_req, timestamp="T0"),
        Message(role="assistant", content="ok", timestamp="T1"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    user_msgs = [m for chunk in result.chunks for m in chunk if m.role == "user"]
    assert len(user_msgs) == 1
    assert len(user_msgs[0].content) <= 200


# ── Preserves assistant reasoning ──


def test_preserves_assistant_reasoning():
    messages = [
        Message(role="user", content="fix it", timestamp="T0"),
        Message(role="assistant",
                content="Let me search for the config file. I'll try src/ first.",
                timestamp="T1"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    asst_msgs = [m for chunk in result.chunks for m in chunk if m.role == "assistant"]
    assert "search for the config" in asst_msgs[0].content


# ── Skips plumbing tools ──


def test_skips_plumbing_tools():
    messages = [
        Message(role="user", content="do something", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="TaskCreate",
                tool_input={"subject": "test"}),
        Message(role="tool_result", content="created", timestamp="T2", tool_name="TaskCreate"),
        Message(role="assistant", content="Done.", timestamp="T3"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    all_msgs = [m for chunk in result.chunks for m in chunk]
    tool_names = [m.tool_name for m in all_msgs if m.tool_name]
    assert len(tool_names) == 0


# ── Chunking by operational sequence ──


def test_chunks_on_user_messages():
    messages = [
        Message(role="user", content="find the bug", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "error"}),
        Message(role="tool_result", content="(match content stripped)", timestamp="T2",
                tool_name="Grep"),
        Message(role="user", content="now fix it", timestamp="T3"),
        Message(role="tool_call", content="", timestamp="T4", tool_name="Edit",
                tool_input={"file_path": "a.py", "old_string": "x", "new_string": "y"}),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    assert len(result.chunks) == 2


def test_chunks_on_tool_category_shift():
    """A shift from search tools to edit tools starts a new chunk."""
    messages = [
        Message(role="user", content="fix the config", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "config"}),
        Message(role="tool_result", content="", timestamp="T2", tool_name="Grep"),
        Message(role="tool_call", content="", timestamp="T3", tool_name="Glob",
                tool_input={"pattern": "*.yaml"}),
        Message(role="tool_result", content="", timestamp="T4", tool_name="Glob"),
        Message(role="assistant", content="Found it. Let me edit.", timestamp="T5"),
        Message(role="tool_call", content="", timestamp="T6", tool_name="Edit",
                tool_input={"file_path": "config.yaml", "old_string": "a", "new_string": "b"}),
        Message(role="tool_result", content="edited", timestamp="T7", tool_name="Edit"),
    ]
    result = clean_transcript_for_signals(_make_transcript(messages))
    # Should split into search chunk and edit chunk
    assert len(result.chunks) >= 2


def test_metadata_preserved():
    messages = [Message(role="user", content="hello", timestamp="T1")]
    result = clean_transcript_for_signals(_make_transcript(messages))
    assert result.metadata.session_id == "test"
    assert result.metadata.source == "claude-code"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_cleaner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicles.signals_cleaner'`

- [ ] **Step 3: Implement signals cleaner**

```python
# src/chronicles/signals_cleaner.py
"""Signals cleaner — preserves tool interactions, strips content."""
from __future__ import annotations

import logging

from chronicles.models import (
    Message, Transcript, CleanedTranscript, TranscriptMetadata,
)

log = logging.getLogger("chronicles")

# Internal plumbing — skip entirely
SKIP_TOOLS = frozenset({
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    "TaskStop", "TaskOutput", "ToolSearch",
    "Skill", "Agent", "SendMessage",
})

# Tools whose results contain file/match content (strip result, keep call)
STRIP_CONTENT_TOOLS = frozenset({"Read", "Glob"})

# Tools whose results contain match content (strip result, keep call)
STRIP_MATCH_TOOLS = frozenset({"Grep"})

# Maximum lines for bash output before truncation
_BASH_MAX_LINES = 20

# Maximum length for user messages (longer = likely requirements, not corrections)
_USER_MAX_LEN = 200

# Tool categories for chunk boundary detection
_SEARCH_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash"})
_EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
_EXEC_TOOLS = frozenset({"Bash"})


def clean_transcript_for_signals(transcript: Transcript) -> CleanedTranscript:
    """Clean transcript for agentic signal extraction.

    Preserves tool calls with parameters and errors.
    Strips file content and large outputs.
    Chunks by operational sequence.
    """
    metadata = TranscriptMetadata(
        session_id=transcript.session_id,
        source=transcript.source,
        project=transcript.project,
        repository=transcript.repository,
        branch=transcript.branch,
        cwd=transcript.cwd,
        timestamp_start=transcript.timestamp_start,
        timestamp_end=transcript.timestamp_end,
        model=transcript.model,
    )
    filtered = _filter_messages(transcript.messages)
    chunks = _chunk_by_operations(filtered)
    return CleanedTranscript(metadata=metadata, chunks=chunks)


def _filter_messages(messages: list[Message]) -> list[Message]:
    """Filter messages: preserve tool interactions, strip content."""
    result: list[Message] = []
    for msg in messages:
        # Skip plumbing tools entirely
        if msg.tool_name in SKIP_TOOLS:
            continue

        # Strip file content from Read results
        if msg.role == "tool_result" and msg.tool_name in STRIP_CONTENT_TOOLS:
            result.append(Message(
                role=msg.role, content="(file content stripped)",
                timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
            continue

        # Strip match content from Grep results
        if msg.role == "tool_result" and msg.tool_name in STRIP_MATCH_TOOLS:
            result.append(Message(
                role=msg.role, content="(match content stripped)",
                timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
            continue

        # Truncate large Bash output
        if msg.role == "tool_result" and msg.tool_name == "Bash":
            result.append(Message(
                role=msg.role, content=_truncate_bash(msg.content),
                timestamp=msg.timestamp, tool_name=msg.tool_name,
            ))
            continue

        # Truncate long user messages (likely requirements, not corrections)
        if msg.role == "user" and len(msg.content) > _USER_MAX_LEN:
            result.append(Message(
                role=msg.role, content=msg.content[:_USER_MAX_LEN],
                timestamp=msg.timestamp,
            ))
            continue

        # Keep everything else as-is (tool_calls with full parameters, assistant reasoning)
        result.append(msg)
    return result


def _truncate_bash(content: str) -> str:
    """Truncate bash output, keeping first and last lines."""
    lines = content.split("\n")
    if len(lines) <= _BASH_MAX_LINES:
        return content
    head = lines[:5]
    tail = lines[-5:]
    return "\n".join(head + [f"... ({len(lines) - 10} lines truncated) ..."] + tail)


def _tool_category(tool_name: str) -> str:
    """Classify a tool into a category for chunk boundary detection."""
    if tool_name in _EDIT_TOOLS:
        return "edit"
    if tool_name in _SEARCH_TOOLS:
        return "search"
    return "other"


def _chunk_by_operations(messages: list[Message]) -> list[list[Message]]:
    """Split messages into operational chunks.

    A new chunk starts when:
    - A user message appears (and current chunk is non-empty)
    - Tool category shifts (search → edit, edit → search)
    """
    if not messages:
        return [[]]

    chunks: list[list[Message]] = []
    current: list[Message] = []
    prev_category: str = ""

    for msg in messages:
        # User message starts a new chunk
        if msg.role == "user" and current:
            chunks.append(current)
            current = []
            prev_category = ""

        # Tool category shift starts a new chunk
        if msg.role == "tool_call" and msg.tool_name:
            cat = _tool_category(msg.tool_name)
            if prev_category and cat != prev_category and current:
                chunks.append(current)
                current = []
            prev_category = cat

        current.append(msg)

    if current:
        chunks.append(current)

    return chunks if chunks else [[]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_cleaner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/signals_cleaner.py tests/test_signals_cleaner.py
git commit -m "feat(signals): add signals cleaner with tool-preserving strategy"
```

---

### Task 3: Implement signals extractor

**Files:**
- Create: `src/chronicles/signals_extractor.py`
- Create: `tests/test_signals_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signals_extractor.py
"""Tests for signals extractor — LLM-powered agentic pattern detection."""
import json
from unittest.mock import patch, MagicMock

from chronicles.config import LLMConfig
from chronicles.models import (
    CleanedTranscript, TranscriptMetadata, Message, Signal, SignalsResult,
)
from chronicles.signals_extractor import SignalsExtractor


def _make_cleaned(chunks: list[list[Message]]) -> CleanedTranscript:
    return CleanedTranscript(
        metadata=TranscriptMetadata(
            session_id="test-123", source="claude-code", project="proj",
            repository="repo", branch="main", cwd="/tmp",
            timestamp_start="2026-04-09T10:00:00Z",
            timestamp_end="2026-04-09T10:30:00Z", model="opus",
        ),
        chunks=chunks,
    )


def _make_config() -> LLMConfig:
    return LLMConfig(provider="claude-code", model="claude-haiku-4-5-20251001")


# ── Prompt building ──


def test_build_prompt_includes_transcript():
    chunks = [[
        Message(role="user", content="find the config", timestamp="T0"),
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "config", "path": "src/"}),
    ]]
    ext = SignalsExtractor(_make_config())
    prompt = ext._build_prompt(_make_cleaned(chunks))
    assert "[TOOL_CALL: Grep]" in prompt
    assert "config" in prompt


def test_build_prompt_includes_existing_signals():
    ext = SignalsExtractor(_make_config())
    chunks = [[Message(role="user", content="hello", timestamp="T0")]]
    existing = "- Use Grep tool instead of Bash grep [tool:Bash,Grep]"
    prompt = ext._build_prompt(_make_cleaned(chunks), existing_signals=existing)
    assert "CURRENT SIGNALS" in prompt
    assert "Use Grep tool" in prompt


# ── Response parsing ──


def test_parse_valid_response():
    ext = SignalsExtractor(_make_config())
    raw = json.dumps({
        "signals": [
            {
                "pattern": "Agent used Bash grep instead of Grep tool",
                "type": "mistake",
                "rule": "Use the Grep tool instead of Bash with grep",
                "context": ["tool:Bash", "tool:Grep"],
                "severity": "high",
            }
        ],
        "demotions": [],
    })
    result = ext._parse_response(raw)
    assert isinstance(result, SignalsResult)
    assert len(result.signals) == 1
    assert result.signals[0].type == "mistake"
    assert result.signals[0].severity == "high"


def test_parse_response_with_markdown_fences():
    ext = SignalsExtractor(_make_config())
    raw = '```json\n' + json.dumps({
        "signals": [],
        "demotions": ["old rule to remove"],
    }) + '\n```'
    result = ext._parse_response(raw)
    assert len(result.demotions) == 1


def test_parse_response_normalizes_type():
    ext = SignalsExtractor(_make_config())
    raw = json.dumps({
        "signals": [
            {
                "pattern": "p", "type": "Mistake", "rule": "r",
                "context": [], "severity": "HIGH",
            }
        ],
        "demotions": [],
    })
    result = ext._parse_response(raw)
    assert result.signals[0].type == "mistake"
    assert result.signals[0].severity == "high"


def test_parse_response_empty_signals():
    ext = SignalsExtractor(_make_config())
    raw = json.dumps({"signals": [], "demotions": []})
    result = ext._parse_response(raw)
    assert len(result.signals) == 0


def test_parse_response_repairs_trailing_comma():
    ext = SignalsExtractor(_make_config())
    raw = '{"signals": [{"pattern": "p", "type": "mistake", "rule": "r", "context": [], "severity": "low",}], "demotions": [],}'
    result = ext._parse_response(raw)
    assert len(result.signals) == 1


# ── End-to-end extract with mocked CLI ──


def test_extract_calls_claude_cli():
    ext = SignalsExtractor(_make_config())
    chunks = [[Message(role="user", content="test", timestamp="T0")]]
    response = json.dumps({"signals": [], "demotions": []})

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=response, stderr=""
        )
        result = ext.extract(_make_cleaned(chunks))

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert isinstance(result, SignalsResult)


def test_extract_raises_on_cli_failure():
    ext = SignalsExtractor(_make_config())
    chunks = [[Message(role="user", content="test", timestamp="T0")]]

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="CLI error"
        )
        try:
            ext.extract(_make_cleaned(chunks))
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "CLI error" in str(e)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicles.signals_extractor'`

- [ ] **Step 3: Implement signals extractor**

```python
# src/chronicles/signals_extractor.py
"""Signals extractor — LLM-powered agentic pattern detection."""
from __future__ import annotations

import json
import logging
import re
import subprocess

from chronicles.config import LLMConfig
from chronicles.models import CleanedTranscript, Signal, SignalsResult

log = logging.getLogger("chronicles")

_SYSTEM_PROMPT = """\
You are an agentic operations analyst. You read agent session transcripts \
and detect operational patterns — both mistakes and efficient strategies.

Focus on HOW the agent used tools, NOT what knowledge it extracted. \
Look for:

MISTAKES (anti-patterns):
- Wrong tool for the task (e.g., Bash with grep/rg when Grep tool is available)
- Failed searches that could have been avoided (searching wrong directories)
- Circular exploration (trying the same search multiple ways before finding it)
- Unnecessary retries or repeated failed approaches
- Overly broad operations (reading entire files when a specific range was needed)

EFFICIENT PATTERNS (worth repeating):
- Direct navigation to the right file/location without unnecessary searching
- Effective tool combinations for common tasks
- Good recovery strategies after initial failures

Return ONLY valid JSON matching this schema (no markdown fences, no explanation):
{
  "signals": [
    {
      "pattern": "string — what the agent did (descriptive)",
      "type": "mistake | efficient",
      "rule": "string — imperative instruction for future agents",
      "context": ["string — tags like tool:Grep, area:navigation, file:src/config.py"],
      "severity": "high | low"
    }
  ],
  "demotions": ["string — exact text of existing rules that this session contradicts"]
}

RULES:
- "type" MUST be exactly one of: mistake, efficient
- "severity" MUST be exactly one of: high, low
- "rule" must be a natural language imperative (e.g., "Use Grep instead of Bash grep")
- "context" tags use the format "category:value" (tool:X, area:X, file:X)
- "demotions" lists the exact rule text from CURRENT SIGNALS that should be removed
- Only report patterns that would help future agents — skip trivial or one-off issues
- "high" severity = wasted significant effort; "low" = minor inefficiency
- Prefer specific, actionable rules over vague advice
- If no signals are found, return {"signals": [], "demotions": []}
"""


class SignalsExtractor:
    """Extracts agentic operational patterns from cleaned transcripts."""

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
            lines.append(
                "If this session shows that any CURRENT SIGNAL is wrong, "
                "include its exact rule text in \"demotions\"."
            )

        lines.append("")
        lines.append("--- TRANSCRIPT ---")
        lines.append("")
        for chunk in transcript.chunks:
            for msg in chunk:
                lines.append(self._format_message(msg))
            lines.append("")
        lines.append("--- END TRANSCRIPT ---")
        lines.append("Analyze the agent's operational behavior above. Return ONLY JSON.")
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
            return f"[TOOL_RESULT: {msg.tool_name}] (empty)"
        return f"[{msg.role.upper()}] {msg.content}"

    _VALID_TYPE = {"mistake", "efficient"}
    _VALID_SEVERITY = {"high", "low"}

    def _parse_response(self, raw: str) -> SignalsResult:
        text = raw.strip()
        if not text:
            raise RuntimeError("LLM returned empty response")

        # Strip markdown fences
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        text = text.strip()

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise RuntimeError(f"No JSON object found in response: {text[:200]}")
        text = text[start:end]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            repaired = re.sub(r",\s*([}\]])", r"\1", text)
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse JSON: {e}\n{text[:500]}") from e

        raw_signals = data.get("signals", [])
        if not isinstance(raw_signals, list):
            raw_signals = []

        signals = []
        for s in raw_signals:
            if not isinstance(s, dict):
                continue
            sig_type = str(s.get("type", "mistake")).strip().lower()
            if sig_type not in self._VALID_TYPE:
                sig_type = "mistake"
            severity = str(s.get("severity", "low")).strip().lower()
            if severity not in self._VALID_SEVERITY:
                severity = "low"
            context = s.get("context", [])
            if not isinstance(context, list):
                context = [str(context)] if context else []

            signals.append(Signal(
                pattern=str(s.get("pattern", "")),
                type=sig_type,
                rule=str(s.get("rule", "")),
                context=[str(c) for c in context],
                severity=severity,
            ))

        demotions = data.get("demotions", [])
        if not isinstance(demotions, list):
            demotions = []
        demotions = [str(d) for d in demotions]

        return SignalsResult(signals=signals, demotions=demotions)

    def extract(
        self,
        transcript: CleanedTranscript,
        existing_signals: str | None = None,
    ) -> SignalsResult:
        """Run extraction via Claude CLI."""
        prompt = self._build_prompt(transcript, existing_signals)
        cmd = ["claude", "--print", "--model", self.config.model, prompt]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (exit {result.returncode}): {result.stderr}"
            )
        return self._parse_response(result.stdout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_extractor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/signals_extractor.py tests/test_signals_extractor.py
git commit -m "feat(signals): add signals extractor with LLM-powered pattern detection"
```

---

### Task 4: Implement signals writer

**Files:**
- Create: `src/chronicles/signals_writer.py`
- Create: `tests/test_signals_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signals_writer.py
"""Tests for signals writer — maintains SIGNALS.md."""
from pathlib import Path

from chronicles.models import Signal, SignalsResult
from chronicles.signals_writer import update_signals_file, load_active_signals


# ── Writing new signals ──


def test_creates_signals_file_if_missing(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    result = SignalsResult(
        signals=[
            Signal(
                pattern="Agent used Bash grep",
                type="mistake",
                rule="Use the Grep tool instead of Bash with grep",
                context=["tool:Bash", "tool:Grep"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="abc123")
    assert signals_path.exists()
    content = signals_path.read_text()
    assert "## Active" in content
    assert "Use the Grep tool instead of Bash with grep" in content
    assert "[tool:Bash,Grep]" in content


def test_appends_to_existing_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Existing rule here [tool:Read] [area:nav]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[
            Signal(
                pattern="new pattern",
                type="efficient",
                rule="New rule for agents",
                context=["area:testing"],
                severity="low",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="def456")
    content = signals_path.read_text()
    assert "Existing rule here" in content
    assert "New rule for agents" in content


def test_high_severity_at_top(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Low severity rule [area:nav]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[
            Signal(
                pattern="critical mistake",
                type="mistake",
                rule="High severity rule",
                context=["tool:Bash"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="ghi789")
    content = signals_path.read_text()
    active_section = content.split("## Active")[1].split("## Demoted")[0]
    lines = [l for l in active_section.strip().split("\n") if l.startswith("- ")]
    assert "High severity rule" in lines[0]


# ── Demotions ──


def test_demotes_contradicted_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Check lib/ for utility modules [area:navigation]\n"
        "- Use Grep instead of Bash grep [tool:Bash,Grep]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[],
        demotions=["Check lib/ for utility modules"],
    )
    update_signals_file(signals_path, result, session_id="xyz999")
    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    assert "Check lib/" not in active
    demoted = content.split("## Demoted")[1]
    assert "Check lib/" in demoted
    assert "xyz999" in demoted


# ── Deduplication ──


def test_does_not_add_duplicate_rules(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Use the Grep tool instead of Bash with grep [tool:Bash,Grep]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[
            Signal(
                pattern="same mistake again",
                type="mistake",
                rule="Use the Grep tool instead of Bash with grep",
                context=["tool:Bash", "tool:Grep"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="dup123")
    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    count = active.count("Use the Grep tool instead of Bash with grep")
    assert count == 1


# ── Cap enforcement ──


def test_caps_at_max_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    existing = "# Signals\n\n## Active\n\n"
    for i in range(50):
        existing += f"- Existing rule {i} [area:test]\n"
    existing += "\n## Demoted\n"
    signals_path.write_text(existing)

    result = SignalsResult(
        signals=[
            Signal(
                pattern="new important signal",
                type="mistake",
                rule="Brand new rule",
                context=["tool:X"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="cap123", max_active=50)
    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    lines = [l for l in active.strip().split("\n") if l.startswith("- ")]
    assert len(lines) <= 50
    assert any("Brand new rule" in l for l in lines)


# ── Loading active signals ──


def test_load_active_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Rule one [tool:X]\n"
        "- Rule two [area:Y]\n\n"
        "## Demoted\n\n"
        "- ~~Old rule~~ (contradicted: session abc)\n"
    )
    active = load_active_signals(signals_path)
    assert "Rule one" in active
    assert "Rule two" in active
    assert "Old rule" not in active


def test_load_active_signals_missing_file(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    active = load_active_signals(signals_path)
    assert active == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicles.signals_writer'`

- [ ] **Step 3: Implement signals writer**

```python
# src/chronicles/signals_writer.py
"""Signals writer — maintains SIGNALS.md with active rules and demotions."""
from __future__ import annotations

import logging
from pathlib import Path

from chronicles.models import SignalsResult

log = logging.getLogger("chronicles")

_TEMPLATE = """\
# Signals

## Active

{active}

## Demoted

{demoted}
"""


def load_active_signals(signals_path: Path) -> str:
    """Load the Active section from SIGNALS.md. Returns empty string if missing."""
    if not signals_path.exists():
        return ""
    content = signals_path.read_text()
    if "## Active" not in content:
        return ""
    active_section = content.split("## Active")[1]
    if "## Demoted" in active_section:
        active_section = active_section.split("## Demoted")[0]
    return active_section.strip()


def update_signals_file(
    signals_path: Path,
    result: SignalsResult,
    session_id: str,
    max_active: int = 50,
) -> None:
    """Update SIGNALS.md with new signals and demotions."""
    # Parse existing content
    active_lines: list[str] = []
    demoted_lines: list[str] = []

    if signals_path.exists():
        content = signals_path.read_text()
        active_lines = _parse_section(content, "## Active")
        demoted_lines = _parse_section(content, "## Demoted")

    # Apply demotions: move matching active rules to demoted
    for demotion_rule in result.demotions:
        remaining = []
        for line in active_lines:
            if demotion_rule in line:
                demoted_lines.append(
                    f"- ~~{_strip_bullet(line)}~~ "
                    f"(contradicted: session {session_id})"
                )
            else:
                remaining.append(line)
        active_lines = remaining

    # Collect existing rule texts for dedup
    existing_rules = {_extract_rule_text(line) for line in active_lines}

    # Add new signals (deduplicated)
    new_high: list[str] = []
    new_low: list[str] = []
    for signal in result.signals:
        if signal.rule in existing_rules:
            continue
        tags = ",".join(signal.context)
        formatted = f"- {signal.rule} [{tags}]"
        if signal.severity == "high":
            new_high.append(formatted)
        else:
            new_low.append(formatted)

    # High severity at top, then existing, then new low severity
    active_lines = new_high + active_lines + new_low

    # Enforce cap: drop oldest low-severity (from the end) first
    while len(active_lines) > max_active:
        active_lines.pop()

    # Write output
    active_text = "\n".join(active_lines) if active_lines else ""
    demoted_text = "\n".join(demoted_lines) if demoted_lines else ""

    signals_path.write_text(_TEMPLATE.format(
        active=active_text,
        demoted=demoted_text,
    ))


def _parse_section(content: str, header: str) -> list[str]:
    """Extract bullet lines from a markdown section."""
    if header not in content:
        return []
    section = content.split(header)[1]
    # Stop at next ## header
    for next_header in ["## "]:
        parts = section.split(next_header, 1)
        if len(parts) > 1:
            section = parts[0]
            break
    return [line for line in section.strip().split("\n") if line.startswith("- ")]


def _strip_bullet(line: str) -> str:
    """Remove leading '- ' from a bullet line."""
    return line[2:] if line.startswith("- ") else line


def _extract_rule_text(line: str) -> str:
    """Extract the rule text from a formatted signal line."""
    text = _strip_bullet(line)
    # Remove trailing [tags]
    while text.rstrip().endswith("]"):
        bracket_start = text.rfind("[")
        if bracket_start == -1:
            break
        text = text[:bracket_start].rstrip()
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_writer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/signals_writer.py tests/test_signals_writer.py
git commit -m "feat(signals): add signals writer for SIGNALS.md management"
```

---

### Task 5: Add config support for signals

**Files:**
- Modify: `src/chronicles/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_config.py

def test_signals_config_defaults(chronicles_dir):
    from chronicles.config import load_config
    config = load_config(chronicles_dir)
    assert config.signals.max_active == 50
    assert config.signals.demoted_retention_days == 90


def test_signals_config_custom(tmp_path):
    from chronicles.config import load_config
    for d in ["records", "archives", "wiki/articles", "wiki/categories", "wiki/queries"]:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "config.yaml").write_text(
        "llm:\n"
        "  provider: claude-code\n"
        "  model: haiku\n"
        "signals:\n"
        "  max_active: 30\n"
        "  demoted_retention_days: 60\n"
    )
    config = load_config(tmp_path)
    assert config.signals.max_active == 30
    assert config.signals.demoted_retention_days == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_config.py::test_signals_config_defaults tests/test_config.py::test_signals_config_custom -v`
Expected: FAIL with `AttributeError: 'ChroniclesConfig' object has no attribute 'signals'`

- [ ] **Step 3: Add SignalsConfig to config.py**

Add the `SignalsConfig` dataclass after `GapsConfig`:

```python
@dataclass
class SignalsConfig:
    max_active: int = 50
    demoted_retention_days: int = 90
```

Add `signals: SignalsConfig` field to `ChroniclesConfig` dataclass.

In `load_config()`, add parsing for the signals section (same pattern as other sections):

```python
    signals_raw = raw.get("signals", {})
    signals = SignalsConfig(
        max_active=signals_raw.get("max_active", 50),
        demoted_retention_days=signals_raw.get("demoted_retention_days", 90),
    )
```

And pass `signals=signals` to the `ChroniclesConfig(...)` constructor.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/config.py tests/test_config.py
git commit -m "feat(signals): add SignalsConfig to config with max_active and demoted_retention_days"
```

---

### Task 6: Add `chronicles signals` CLI command

**Files:**
- Modify: `src/chronicles/cli.py`
- Create: `tests/test_cli_signals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_signals.py
"""Tests for the chronicles signals CLI command."""
import json
from unittest.mock import patch, MagicMock

from chronicles.cli import main
from chronicles.models import Signal, SignalsResult


def test_signals_command_runs_pipeline(chronicles_dir, tmp_path):
    """End-to-end: signals command parses, cleans, extracts, writes."""
    # Create a minimal transcript
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        json.dumps({"type": "human", "text": "find the config"}) + "\n"
        + json.dumps({"type": "assistant", "text": "Let me search."}) + "\n"
    )

    mock_result = SignalsResult(signals=[], demotions=[])

    with patch("chronicles.cli.SignalsExtractor") as MockExtractor:
        instance = MockExtractor.return_value
        instance.extract.return_value = mock_result

        with patch("chronicles.cli.detect_source") as mock_detect:
            from chronicles.models import Transcript, Message
            mock_source = MagicMock()
            mock_source.key = "claude-code"
            mock_source.parse_session.return_value = Transcript(
                session_id="test", source="claude-code", project="proj",
                repository="repo", branch="main", cwd="/tmp",
                timestamp_start="2026-04-09T10:00:00Z",
                timestamp_end="2026-04-09T10:30:00Z",
                model="opus",
                messages=[
                    Message(role="user", content="find the config", timestamp="T0"),
                    Message(role="assistant", content="Let me search.", timestamp="T1"),
                ],
            )
            mock_detect.return_value = mock_source

            main(["signals", str(transcript_path),
                  "--chronicles-dir", str(chronicles_dir)])

    # SIGNALS.md should exist now
    signals_path = chronicles_dir / "SIGNALS.md"
    assert signals_path.exists()


def test_signals_command_no_paths_exits(chronicles_dir):
    """signals with no paths and no --since should fail."""
    try:
        main(["signals", "--chronicles-dir", str(chronicles_dir)])
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_cli_signals.py -v`
Expected: FAIL (command not registered)

- [ ] **Step 3: Add signals subcommand to CLI**

Add to the imports in `src/chronicles/cli.py`:

```python
from chronicles.signals_cleaner import clean_transcript_for_signals
from chronicles.signals_extractor import SignalsExtractor
from chronicles.signals_writer import update_signals_file, load_active_signals
```

Add the subparser after the `enrich` subparser in `main()`:

```python
    signals_p = sub.add_parser("signals", help="Extract agentic operational signals")
    signals_p.add_argument("paths", nargs="*", type=Path, help="Transcript file paths")
    signals_p.add_argument("--source", type=str, default=None, help="Force source type")
    signals_p.add_argument("--since", type=str, default=None, help="Discover sessions since Nd")
    signals_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                          help="Path to chronicles directory")
    signals_p.add_argument("--last", type=int, default=None, metavar="N",
                          help="Only process the N most recent discovered sessions")
```

Add the dispatch in `main()`:

```python
    elif args.command == "signals":
        _run_signals(args)
```

Add the `_run_signals` function:

```python
def _run_signals(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    _ensure_chronicles_dir(chronicles_dir)
    config = load_config(chronicles_dir)

    paths: list[Path] = list(args.paths) if args.paths else []

    if args.since:
        days = int(args.since.rstrip("d"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for source in ALL_SOURCES:
            if source.key in config.sources and source.available():
                paths.extend(source.discover_sessions(since=cutoff))

    if args.last is not None and paths:
        paths = sorted(paths, key=lambda p: p.stat().st_mtime)[-args.last:]

    if not paths:
        print("No transcript files to process.", file=sys.stderr)
        sys.exit(1)

    log.info("Processing %d transcript(s) for signals", len(paths))

    signals_path = chronicles_dir / "SIGNALS.md"
    existing_signals = load_active_signals(signals_path)

    extractor = SignalsExtractor(config.llm)

    for path in paths:
        source_override = args.source
        if source_override:
            source = get_source(source_override)
        else:
            source = detect_source(path)

        log.info("Parsing %s (source: %s)", path.name, source.key)
        transcript = source.parse_session(path)
        cleaned = clean_transcript_for_signals(transcript)
        total_msgs = sum(len(c) for c in cleaned.chunks)
        log.info("Cleaned → %d messages in %d chunk(s)", total_msgs, len(cleaned.chunks))

        log.info("Extracting signals via %s...", config.llm.provider)
        result = extractor.extract(cleaned, existing_signals=existing_signals)

        log.info("Found %d signal(s), %d demotion(s)",
                 len(result.signals), len(result.demotions))

        update_signals_file(
            signals_path, result,
            session_id=cleaned.metadata.session_id,
            max_active=config.signals.max_active,
        )
        log.info("Updated %s", signals_path.relative_to(chronicles_dir))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_cli_signals.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/cli.py tests/test_cli_signals.py
git commit -m "feat(signals): add chronicles signals CLI command"
```

---

### Task 7: Add hook scripts

**Files:**
- Create: `plugin/scripts/signals-ingest.sh`
- Create: `plugin/scripts/signals-context.sh`
- Modify: `plugin/hooks/hooks.json`

- [ ] **Step 1: Create signals-ingest.sh**

```bash
#!/bin/bash
# SessionEnd hook — extract agentic signals from completed session
set -uo pipefail

INPUT=$(cat)

CWD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('cwd', ''))
except Exception:
    print('')
" 2>/dev/null)

TRANSCRIPT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('transcript_path', ''))
except Exception:
    print('')
" 2>/dev/null)

DIR="${CHRONICLES_DIR:-chronicles}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Only run if chronicles directory exists
[ -d "$CHRONICLES_DIR" ] || exit 0

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles signals "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" || true
else
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles signals --since 1d --last 1 --chronicles-dir "$CHRONICLES_DIR" || true
fi
```

- [ ] **Step 2: Create signals-context.sh**

```bash
#!/bin/bash
# SessionStart hook — inject active signals as context
set -euo pipefail

INPUT=$(cat)

CWD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('cwd', ''))
except Exception:
    print('')
" 2>/dev/null)

DIR="${CHRONICLES_DIR:-chronicles}"
CHRONICLES_DIR="${CWD}/${DIR}"

SIGNALS_PATH="${CHRONICLES_DIR}/SIGNALS.md"

# Only inject if SIGNALS.md exists and has active content
if [ ! -f "$SIGNALS_PATH" ]; then
    exit 0
fi

# Extract Active section only
ACTIVE=$(python3 -c "
import sys
content = open('$SIGNALS_PATH').read()
if '## Active' not in content:
    sys.exit(0)
active = content.split('## Active')[1]
if '## Demoted' in active:
    active = active.split('## Demoted')[0]
active = active.strip()
if active:
    print(active)
" 2>/dev/null)

if [ -z "$ACTIVE" ]; then
    exit 0
fi

CONTEXT="Agentic operational signals from past sessions — follow these rules when using tools:
${ACTIVE}"

python3 -c "
import json, os, sys
context = sys.stdin.read()
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
else:
    print(json.dumps({'additionalContext': context}))
" <<< "$CONTEXT"
```

- [ ] **Step 3: Make scripts executable**

```bash
chmod +x plugin/scripts/signals-ingest.sh plugin/scripts/signals-context.sh
```

- [ ] **Step 4: Update hooks.json**

Replace the content of `plugin/hooks/hooks.json` with:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/gold-context.sh\"",
            "timeout": 10
          },
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/signals-context.sh\"",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/ingest.sh\"",
            "timeout": 600
          },
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/signals-ingest.sh\"",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 5: Verify scripts are syntactically valid**

Run: `bash -n plugin/scripts/signals-ingest.sh && bash -n plugin/scripts/signals-context.sh && echo "OK"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add plugin/scripts/signals-ingest.sh plugin/scripts/signals-context.sh plugin/hooks/hooks.json
git commit -m "feat(signals): add hook scripts for signals injection and ingestion"
```

---

### Task 8: Integration test

**Files:**
- Create: `tests/test_signals_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_signals_integration.py
"""Integration test: full signals pipeline from transcript to SIGNALS.md."""
import json
from unittest.mock import patch, MagicMock

from chronicles.models import Message, Transcript, Signal, SignalsResult
from chronicles.signals_cleaner import clean_transcript_for_signals
from chronicles.signals_extractor import SignalsExtractor
from chronicles.signals_writer import update_signals_file, load_active_signals
from chronicles.config import LLMConfig


def test_full_signals_pipeline(tmp_path):
    """Transcript → clean → extract (mocked) → write → verify SIGNALS.md."""
    # 1. Create transcript with a realistic tool-mistake pattern
    transcript = Transcript(
        session_id="integration-test-001",
        source="claude-code",
        project="myproject",
        repository="myrepo",
        branch="feat/add-config",
        cwd="/home/user/myrepo",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus",
        messages=[
            Message(role="user", content="find the config file", timestamp="T0"),
            Message(role="assistant", content="Let me search for it.", timestamp="T1"),
            Message(role="tool_call", content="", timestamp="T2", tool_name="Bash",
                    tool_input={"command": "grep -r 'config' src/"}),
            Message(role="tool_result", content="lots of matches...", timestamp="T3",
                    tool_name="Bash"),
            Message(role="tool_call", content="", timestamp="T4", tool_name="Grep",
                    tool_input={"pattern": "config", "path": "src/"}),
            Message(role="tool_result", content="src/config.py:1:# config module",
                    timestamp="T5", tool_name="Grep"),
            Message(role="assistant", content="Found it at src/config.py", timestamp="T6"),
        ],
    )

    # 2. Clean
    cleaned = clean_transcript_for_signals(transcript)
    assert len(cleaned.chunks) >= 1
    # Verify tool_call parameters are preserved
    tool_calls = [m for chunk in cleaned.chunks for m in chunk if m.role == "tool_call"]
    assert any(m.tool_name == "Bash" and m.tool_input.get("command") for m in tool_calls)

    # 3. Mock extraction (LLM would detect Bash grep → Grep tool mistake)
    mock_result = SignalsResult(
        signals=[
            Signal(
                pattern="Agent used Bash with grep command before using the Grep tool",
                type="mistake",
                rule="Use the Grep tool directly instead of Bash with grep or rg commands",
                context=["tool:Bash", "tool:Grep", "area:search"],
                severity="high",
            ),
        ],
        demotions=[],
    )

    # 4. Write
    signals_path = tmp_path / "SIGNALS.md"
    update_signals_file(signals_path, mock_result, session_id="integration-test-001")

    # 5. Verify
    assert signals_path.exists()
    content = signals_path.read_text()
    assert "Use the Grep tool directly" in content
    assert "[tool:Bash,tool:Grep,area:search]" in content

    # 6. Verify load_active_signals returns the rule for injection
    active = load_active_signals(signals_path)
    assert "Use the Grep tool directly" in active


def test_demotion_lifecycle(tmp_path):
    """Signal is active → contradicted in next session → demoted."""
    signals_path = tmp_path / "SIGNALS.md"

    # Session 1: add a signal
    result1 = SignalsResult(
        signals=[
            Signal(
                pattern="Agent searched lib/ for modules",
                type="efficient",
                rule="Check lib/ first for utility modules",
                context=["area:navigation"],
                severity="low",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result1, session_id="session-001")
    assert "Check lib/ first" in load_active_signals(signals_path)

    # Session 2: contradicts — there is no lib/ directory
    result2 = SignalsResult(
        signals=[],
        demotions=["Check lib/ first for utility modules"],
    )
    update_signals_file(signals_path, result2, session_id="session-002")

    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    assert "Check lib/" not in active

    demoted = content.split("## Demoted")[1]
    assert "Check lib/" in demoted
    assert "session-002" in demoted
```

- [ ] **Step 2: Run integration tests**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest tests/test_signals_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/gpavanello/Repositories/chronicles && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_signals_integration.py
git commit -m "test(signals): add integration tests for full signals pipeline"
```
