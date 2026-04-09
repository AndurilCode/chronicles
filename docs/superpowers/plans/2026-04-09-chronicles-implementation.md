# Chronicles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that extracts structured knowledge from agent session transcripts into a codebase-local Obsidian wiki.

**Architecture:** Two-command CLI (`chronicles ingest` and `chronicles lint`). Ingest parses platform-specific transcripts through source adapters, cleans them, sends to a pluggable LLM extractor, and writes records + wiki articles via Jinja2 templates. Lint validates the wiki, manages confidence lifecycle, merges duplicates, and regenerates GOLD.md.

**Tech Stack:** Python 3.11+, Jinja2, PyYAML, argparse, concurrent.futures

---

## File Structure

```
chronicles/
├── pyproject.toml                    # Package config, CLI entry point
├── src/chronicles/
│   ├── __init__.py
│   ├── __main__.py                   # python -m chronicles
│   ├── cli.py                        # argparse: ingest + lint subcommands
│   ├── config.py                     # config.yaml loader + defaults
│   ├── models.py                     # Message, Transcript, CleanedTranscript, Record dataclasses
│   ├── sources/
│   │   ├── __init__.py               # ALL_SOURCES list, detect_source()
│   │   ├── base.py                   # BaseSource ABC
│   │   ├── claude_code.py            # Claude Code JSONL parser
│   │   ├── copilot_cli.py            # Copilot CLI JSONL parser
│   │   └── copilot_vscode.py         # Copilot VS Code JSON parser
│   ├── cleaner.py                    # Tool result filtering + turn-based chunking
│   ├── extractors/
│   │   ├── __init__.py               # get_extractor(config) factory
│   │   ├── base.py                   # BaseExtractor ABC
│   │   ├── copilot_cli.py            # copilot -p subprocess wrapper
│   │   └── claude_code.py            # claude --print subprocess wrapper
│   ├── writer.py                     # Write records, CHRONICLES.md entries, wiki pages
│   ├── linter.py                     # Structural validation, links, dedup, confidence, GOLD.md
│   └── templates.py                  # Jinja2 template loader + renderer
├── templates/                        # Default Jinja2 templates (6 files)
│   ├── record.md.j2
│   ├── wiki_article.md.j2
│   ├── wiki_query.md.j2
│   ├── wiki_category.md.j2
│   ├── chronicles_entry.md.j2
│   └── gold.md.j2
└── tests/
    ├── conftest.py                   # Shared fixtures, tmp chronicles dir
    ├── test_models.py
    ├── test_config.py
    ├── test_cleaner.py
    ├── test_templates.py
    ├── test_writer.py
    ├── test_linter.py
    ├── test_sources/
    │   ├── test_detect.py
    │   ├── test_claude_code.py
    │   ├── test_copilot_cli.py
    │   └── test_copilot_vscode.py
    ├── test_extractors/
    │   ├── test_copilot_cli.py
    │   └── test_claude_code.py
    └── fixtures/
        ├── claude_code_session.jsonl
        ├── copilot_cli_session.jsonl
        └── copilot_vscode_session.json
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/chronicles/__init__.py`
- Create: `src/chronicles/__main__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "chronicles"
version = "0.1.0"
description = "Automatic knowledge extraction from agent session transcripts"
requires-python = ">=3.11"
dependencies = [
    "jinja2>=3.1",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-tmp-files>=0.0.2",
]

[project.scripts]
chronicles = "chronicles.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init and entry point**

`src/chronicles/__init__.py`:
```python
"""Chronicles — automatic knowledge extraction from agent session transcripts."""
```

`src/chronicles/__main__.py`:
```python
"""Allow running as `python -m chronicles`."""
from chronicles.cli import main

main()
```

- [ ] **Step 3: Create test conftest with shared fixtures**

`tests/conftest.py`:
```python
"""Shared test fixtures."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def chronicles_dir(tmp_path):
    """Create a temporary chronicles directory structure."""
    dirs = [
        "records",
        "archives",
        "wiki/articles",
        "wiki/categories",
        "wiki/queries",
        "templates",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)

    # Write minimal config.yaml
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n"
        "  provider: copilot-cli\n"
        "  model: gpt-5-mini\n"
        "  max_concurrent: 1\n"
        "sources:\n"
        "  - claude-code\n"
        "  - copilot-cli\n"
        "  - copilot-vscode\n"
        "confidence:\n"
        "  promotion_threshold: 3\n"
        "archive:\n"
        "  after_days: 90\n"
    )

    # Write empty index files
    (tmp_path / "CHRONICLES.md").write_text(
        "---\ntype: chronicles-index\nlast_updated: 2026-01-01\nrecord_count: 0\n---\n\n# Chronicles\n"
    )
    (tmp_path / "GOLD.md").write_text(
        "---\ntype: gold-index\nlast_updated: 2026-01-01\npromoted_count: 0\n---\n\n# Gold Notes\n"
    )

    return tmp_path
```

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p src/chronicles/sources src/chronicles/extractors tests/test_sources tests/test_extractors tests/fixtures
touch src/chronicles/sources/__init__.py src/chronicles/extractors/__init__.py
touch tests/test_sources/__init__.py tests/test_extractors/__init__.py
```

- [ ] **Step 5: Install in dev mode and verify**

Run: `pip install -e ".[dev]"`
Expected: installs successfully

Run: `pytest --collect-only`
Expected: no errors (no tests collected yet is fine)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: scaffold chronicles project structure"
```

---

### Task 2: Data Models

**Files:**
- Create: `src/chronicles/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for data models**

`tests/test_models.py`:
```python
"""Tests for core data models."""
from chronicles.models import Message, Transcript, CleanedTranscript, TranscriptMetadata, ExtractionResult


def test_message_defaults():
    msg = Message(role="user", content="hello", timestamp="2026-04-09T10:00:00Z")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.tool_name == ""
    assert msg.tool_input == {}


def test_message_tool_call():
    msg = Message(
        role="tool_call",
        content="",
        timestamp="2026-04-09T10:00:00Z",
        tool_name="Read",
        tool_input={"file_path": "/src/main.py"},
    )
    assert msg.tool_name == "Read"
    assert msg.tool_input["file_path"] == "/src/main.py"


def test_transcript_fields():
    t = Transcript(
        session_id="abc123",
        source="claude-code",
        project="my-project",
        repository="my-repo",
        branch="feat/test",
        cwd="/home/user/repo",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="claude-opus-4-6",
        messages=[],
    )
    assert t.source == "claude-code"
    assert t.date == "2026-04-09"
    assert t.messages == []


def test_transcript_date_from_timestamp():
    t = Transcript(
        session_id="x", source="", project="", repository="",
        branch="", cwd="", timestamp_start="2026-12-25T08:00:00Z",
        timestamp_end="", model="", messages=[],
    )
    assert t.date == "2026-12-25"


def test_transcript_date_empty():
    t = Transcript(
        session_id="x", source="", project="", repository="",
        branch="", cwd="", timestamp_start="",
        timestamp_end="", model="", messages=[],
    )
    assert t.date == ""


def test_cleaned_transcript():
    meta = TranscriptMetadata(
        session_id="abc", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z", model="opus",
    )
    ct = CleanedTranscript(metadata=meta, chunks=[[]])
    assert ct.metadata.session_id == "abc"
    assert len(ct.chunks) == 1


def test_extraction_result_fields():
    result = ExtractionResult(
        branch="feat/test",
        status="complete",
        tags=["test"],
        duration="10min",
        files_changed=["src/main.py"],
        objective="Test something",
        outcome="It worked",
        decisions=[],
        problems=[],
        discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[],
    )
    assert result.status == "complete"
    assert result.slug == "feat-test"


def test_extraction_result_slug_strips_prefix():
    result = ExtractionResult(
        branch="feat/oauth-connections", status="complete", tags=[],
        duration="", files_changed=[], objective="", outcome="",
        decisions=[], problems=[], discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[],
    )
    assert result.slug == "feat-oauth-connections"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement data models**

`src/chronicles/models.py`:
```python
"""Core data models for the chronicles pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message in a transcript."""
    role: str              # "user" | "assistant" | "tool_call" | "tool_result"
    content: str
    timestamp: str         # ISO 8601
    tool_name: str = ""    # for tool_call / tool_result (canonical name)
    tool_input: dict = field(default_factory=dict)


@dataclass
class Transcript:
    """Parsed transcript from any source adapter."""
    session_id: str
    source: str
    project: str
    repository: str
    branch: str
    cwd: str
    timestamp_start: str
    timestamp_end: str
    model: str
    messages: list[Message]

    @property
    def date(self) -> str:
        if self.timestamp_start:
            return self.timestamp_start[:10]
        return ""


@dataclass
class TranscriptMetadata:
    """Transcript identity without messages — used in CleanedTranscript."""
    session_id: str
    source: str
    project: str
    repository: str
    branch: str
    cwd: str
    timestamp_start: str
    timestamp_end: str
    model: str


@dataclass
class CleanedTranscript:
    """Transcript after cleaning: filtered tool results, chunked by turns."""
    metadata: TranscriptMetadata
    chunks: list[list[Message]]


@dataclass
class ExtractionResult:
    """Structured output from the LLM extractor."""
    branch: str
    status: str            # complete | partial | failed | exploratory
    tags: list[str]
    duration: str
    files_changed: list[str]
    objective: str
    outcome: str
    decisions: list[dict[str, str]]
    problems: list[dict[str, Any]]
    discovered: list[dict[str, str]]
    continuity: dict[str, list[str]]
    wiki_instructions: list[dict[str, Any]]

    @property
    def slug(self) -> str:
        return self.branch.replace("/", "-")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/models.py tests/test_models.py
git commit -m "feat: add core data models (Message, Transcript, ExtractionResult)"
```

---

### Task 3: Config Loader

**Files:**
- Create: `src/chronicles/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

`tests/test_config.py`:
```python
"""Tests for config loading."""
from pathlib import Path

from chronicles.config import load_config, ChroniclesConfig


def test_load_config_from_file(chronicles_dir):
    config = load_config(chronicles_dir)
    assert config.llm.provider == "copilot-cli"
    assert config.llm.model == "gpt-5-mini"
    assert config.llm.max_concurrent == 1
    assert "claude-code" in config.sources
    assert config.confidence.promotion_threshold == 3
    assert config.archive.after_days == 90


def test_load_config_defaults(tmp_path):
    """Missing config.yaml uses defaults."""
    config = load_config(tmp_path)
    assert config.llm.provider == "copilot-cli"
    assert config.llm.model == "gpt-5-mini"
    assert config.llm.max_concurrent == 3
    assert config.confidence.promotion_threshold == 3
    assert config.archive.after_days == 90


def test_load_config_partial_override(tmp_path):
    """Partial config merges with defaults."""
    (tmp_path / "config.yaml").write_text(
        "llm:\n  provider: claude-code\n  model: claude-opus-4-6\n"
    )
    config = load_config(tmp_path)
    assert config.llm.provider == "claude-code"
    assert config.llm.model == "claude-opus-4-6"
    assert config.llm.max_concurrent == 3  # default
    assert config.confidence.promotion_threshold == 3  # default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement config loader**

`src/chronicles/config.py`:
```python
"""Config loader — reads chronicles/config.yaml with defaults."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    provider: str = "copilot-cli"
    model: str = "gpt-5-mini"
    max_concurrent: int = 3


@dataclass
class ConfidenceConfig:
    promotion_threshold: int = 3


@dataclass
class ArchiveConfig:
    after_days: int = 90


@dataclass
class ChroniclesConfig:
    llm: LLMConfig
    sources: list[str]
    confidence: ConfidenceConfig
    archive: ArchiveConfig
    chronicles_dir: Path


def load_config(chronicles_dir: Path) -> ChroniclesConfig:
    """Load config.yaml from chronicles_dir, falling back to defaults."""
    config_path = chronicles_dir / "config.yaml"

    raw: dict = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}

    llm_raw = raw.get("llm", {})
    llm = LLMConfig(
        provider=llm_raw.get("provider", "copilot-cli"),
        model=llm_raw.get("model", "gpt-5-mini"),
        max_concurrent=llm_raw.get("max_concurrent", 3),
    )

    sources = raw.get("sources", ["claude-code", "copilot-cli", "copilot-vscode"])

    conf_raw = raw.get("confidence", {})
    confidence = ConfidenceConfig(
        promotion_threshold=conf_raw.get("promotion_threshold", 3),
    )

    arch_raw = raw.get("archive", {})
    archive = ArchiveConfig(
        after_days=arch_raw.get("after_days", 90),
    )

    return ChroniclesConfig(
        llm=llm,
        sources=sources,
        confidence=confidence,
        archive=archive,
        chronicles_dir=chronicles_dir,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/config.py tests/test_config.py
git commit -m "feat: add config.yaml loader with defaults"
```

---

### Task 4: Template Renderer + Default Templates

**Files:**
- Create: `src/chronicles/templates.py`
- Create: `templates/record.md.j2`
- Create: `templates/wiki_article.md.j2`
- Create: `templates/wiki_query.md.j2`
- Create: `templates/wiki_category.md.j2`
- Create: `templates/chronicles_entry.md.j2`
- Create: `templates/gold.md.j2`
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write failing tests**

`tests/test_templates.py`:
```python
"""Tests for template rendering."""
from pathlib import Path

from chronicles.templates import TemplateRenderer


def test_render_record(tmp_path):
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "branch": "feat/oauth",
        "status": "complete",
        "tags": ["oauth", "auth"],
        "source": "claude-code",
        "duration": "30min",
        "files_changed": ["src/auth.py"],
        "objective": "Add OAuth",
        "outcome": "OAuth works",
        "decisions": [
            {"description": "Use refresh tokens", "rationale": "more secure"}
        ],
        "problems": [
            {"description": "403 on scope", "root_cause": "wrong delimiter", "dead_end": False}
        ],
        "discovered": [
            {"type": "convention", "description": "Use _connection suffix"}
        ],
        "continuity": {
            "unfinished": ["Error UX"],
            "open_questions": ["Auto-disconnect?"],
            "next": ["Add backoff"],
        },
    }
    result = renderer.render("record", data)
    assert "date: 2026-04-09" in result
    assert "feat/oauth" in result
    assert "Add OAuth" in result
    assert "Use refresh tokens" in result
    assert "[convention]" in result
    assert "Error UX" in result


def test_render_wiki_article():
    renderer = TemplateRenderer()
    data = {
        "type": "convention",
        "confidence": "low",
        "sources": ["2026-04-09_feat-oauth"],
        "first_seen": "2026-04-09",
        "last_confirmed": "2026-04-09",
        "tags": ["naming"],
        "title": "Connection Suffix Pattern",
        "body": "All configs use _connection suffix.",
        "evidence": ["Found in oauth session"],
        "implications": ["Must follow pattern"],
    }
    result = renderer.render("wiki_article", data)
    assert "type: convention" in result
    assert "confidence: low" in result
    assert "Connection Suffix Pattern" in result
    assert "[[2026-04-09_feat-oauth]]" in result


def test_render_chronicles_entry():
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "slug": "feat-oauth",
        "branch": "feat/oauth",
        "status_icon": "✅",
        "status_label": "Complete",
        "objective": "Add OAuth",
        "outcome": "OAuth works",
        "tags_as_hashtags": "#oauth #auth",
    }
    result = renderer.render("chronicles_entry", data)
    assert "[[2026-04-09_feat-oauth|feat/oauth]]" in result
    assert "✅" in result
    assert "#oauth #auth" in result


def test_render_gold():
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "count": 2,
        "groups": [
            ("Conventions", [
                {"title": "Suffix Pattern", "summary": "use _connection suffix"},
            ]),
            ("Workarounds", [
                {"title": "Retry Backoff", "summary": "hardcoded 60s"},
            ]),
        ],
    }
    result = renderer.render("gold", data)
    assert "promoted_count: 2" in result
    assert "## Conventions" in result
    assert "[[Suffix Pattern]]" in result
    assert "## Workarounds" in result


def test_render_wiki_query():
    renderer = TemplateRenderer()
    data = {
        "asked_by": "human",
        "date": "2026-04-09",
        "answered_from": ["Article A", "Article B"],
        "tags": ["onboarding"],
        "question": "How do I add a connection?",
        "answer": "Follow the suffix pattern.",
    }
    result = renderer.render("wiki_query", data)
    assert "type: query" in result
    assert "[[Article A]]" in result
    assert "How do I add a connection?" in result


def test_render_wiki_category():
    renderer = TemplateRenderer()
    data = {
        "tags": ["mcp"],
        "title": "MCP Conventions",
        "articles": ["Suffix Pattern", "Token Storage"],
        "open_questions": ["Auto-disconnect?"],
    }
    result = renderer.render("wiki_category", data)
    assert "type: category" in result
    assert "[[Suffix Pattern]]" in result
    assert "## Open Questions" in result


def test_custom_template_dir(tmp_path):
    """User-provided template dir overrides defaults."""
    custom = tmp_path / "templates"
    custom.mkdir()
    (custom / "record.md.j2").write_text("CUSTOM: {{ branch }}")
    renderer = TemplateRenderer(template_dir=custom)
    result = renderer.render("record", {"branch": "main"})
    assert result == "CUSTOM: main"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_templates.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Create default templates**

`templates/record.md.j2`:
```
---
date: {{ date }}
branch: {{ branch }}
status: {{ status }}
tags: {{ tags }}
agent: {{ source }}
duration: {{ duration }}
files_changed:
{% for f in files_changed %}  - {{ f }}
{% endfor %}---

# {{ branch }}

> **Objective**: {{ objective }}
> **Outcome**: {{ outcome }}

## Decisions
{% for d in decisions %}- {{ d.description }} -- {{ d.rationale }}
{% endfor %}
## Problems
{% for p in problems %}{% if p.dead_end %}- Dead end: {{ p.description }}, {{ p.root_cause }}
{% else %}- `{{ p.description }}`
  -> root cause: {{ p.root_cause }}
{% endif %}{% endfor %}
## Discovered
{% for d in discovered %}- [{{ d.type }}] {{ d.description }}
{% endfor %}
## Continuity
{% for u in continuity.unfinished %}- **Unfinished**: {{ u }}
{% endfor %}{% for q in continuity.open_questions %}- **Open question**: {{ q }}
{% endfor %}{% for n in continuity.next %}- **Next**: {{ n }}
{% endfor %}
```

`templates/wiki_article.md.j2`:
```
---
type: {{ type }}
confidence: {{ confidence }}
sources:
{% for s in sources %}  - "[[{{ s }}]]"
{% endfor %}first_seen: {{ first_seen }}
last_confirmed: {{ last_confirmed }}
tags: {{ tags }}
---

# {{ title }}

{{ body }}

## Evidence
{% for e in evidence %}- {{ e }}
{% endfor %}
## Implications
{% for i in implications %}- {{ i }}
{% endfor %}
```

`templates/wiki_query.md.j2`:
```
---
type: query
asked_by: {{ asked_by }}
date: {{ date }}
answered_from:
{% for a in answered_from %}  - "[[{{ a }}]]"
{% endfor %}tags: {{ tags }}
---

# {{ question }}

{{ answer }}
```

`templates/wiki_category.md.j2`:
```
---
type: category
tags: {{ tags }}
---

# {{ title }}

{% for a in articles %}- [[{{ a }}]]
{% endfor %}
{% if open_questions %}## Open Questions
{% for q in open_questions %}- [[{{ q }}]]
{% endfor %}{% endif %}
```

`templates/chronicles_entry.md.j2`:
```
## [[{{ date }}_{{ slug }}|{{ branch }}]] | {{ status_icon }} {{ status_label }}
> **Objective**: {{ objective }}
> **Outcome**: {{ outcome }}
> **Tags**: {{ tags_as_hashtags }}
```

`templates/gold.md.j2`:
```
---
type: gold-index
last_updated: {{ date }}
promoted_count: {{ count }}
---

# Gold Notes

> High-confidence, validated knowledge for this repository. Read before acting.

{% for group_name, articles in groups %}## {{ group_name }}
{% for a in articles %}- [[{{ a.title }}]] -- {{ a.summary }}
{% endfor %}
{% endfor %}
```

- [ ] **Step 4: Implement template renderer**

`src/chronicles/templates.py`:
```python
"""Jinja2 template loader and renderer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

# Default templates ship with the package
_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


class TemplateRenderer:
    """Renders chronicles artifacts from Jinja2 templates."""

    def __init__(self, template_dir: Path | None = None):
        self._dir = template_dir or _DEFAULT_TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._dir)),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=False,
        )

    def render(self, template_name: str, data: dict[str, Any]) -> str:
        """Render a template by name (without .md.j2 extension)."""
        tpl = self._env.get_template(f"{template_name}.md.j2")
        return tpl.render(**data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_templates.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/templates.py templates/ tests/test_templates.py
git commit -m "feat: add Jinja2 template renderer and 6 default templates"
```

---

### Task 5: Source Adapter Base + Auto-Detection

**Files:**
- Create: `src/chronicles/sources/base.py`
- Create: `src/chronicles/sources/__init__.py`
- Create: `tests/test_sources/test_detect.py`

- [ ] **Step 1: Write failing tests**

`tests/test_sources/test_detect.py`:
```python
"""Tests for source auto-detection."""
import json
from pathlib import Path

from chronicles.sources import detect_source, ALL_SOURCES
from chronicles.sources.base import BaseSource


def test_all_sources_registered():
    assert len(ALL_SOURCES) == 3
    keys = [s.key for s in ALL_SOURCES]
    assert "claude-code" in keys
    assert "copilot-cli" in keys
    assert "copilot-vscode" in keys


def test_detect_claude_code(tmp_path):
    """Claude Code JSONL has type: human/assistant with message.content."""
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps({"type": "human", "message": {"content": [{"type": "text", "text": "hello"}]}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n"
    )
    source = detect_source(session)
    assert source.key == "claude-code"


def test_detect_copilot_cli(tmp_path):
    """Copilot CLI JSONL has type: userPromptSubmitted / turn.start."""
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps({"type": "session.start", "timestamp": "2026-04-09T10:00:00Z"}) + "\n"
        + json.dumps({"type": "turn.start", "request": {"message": "hello"}}) + "\n"
    )
    source = detect_source(session)
    assert source.key == "copilot-cli"


def test_detect_copilot_vscode(tmp_path):
    """VS Code Copilot Chat JSON has sessions with requests array."""
    session = tmp_path / "session.json"
    session.write_text(json.dumps({
        "version": 2,
        "sessions": [{"requests": [{"message": {"text": "hello"}}]}],
    }))
    source = detect_source(session)
    assert source.key == "copilot-vscode"


def test_detect_unknown_raises(tmp_path):
    """Unknown format raises ValueError."""
    session = tmp_path / "unknown.txt"
    session.write_text("just some text\n")
    import pytest
    with pytest.raises(ValueError, match="Could not detect source"):
        detect_source(session)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sources/test_detect.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement BaseSource and detection**

`src/chronicles/sources/base.py`:
```python
"""Base source adapter interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Transcript


class BaseSource(ABC):
    """Interface every source parser must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name, e.g. 'Claude Code'."""

    @property
    @abstractmethod
    def key(self) -> str:
        """Machine key, e.g. 'claude-code'."""

    @abstractmethod
    def available(self) -> bool:
        """Return True if this source's data directory exists."""

    @abstractmethod
    def parse_session(self, session_path: Path) -> Transcript:
        """Parse a single session file into a Transcript."""

    @abstractmethod
    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        """Find session files, optionally filtered by date."""

    @abstractmethod
    def sniff(self, session_path: Path) -> bool:
        """Return True if the file looks like it came from this source."""
```

`src/chronicles/sources/__init__.py`:
```python
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
    """Auto-detect the source of a transcript file."""
    for source in ALL_SOURCES:
        if source.sniff(session_path):
            return source
    raise ValueError(f"Could not detect source for {session_path}")


def get_source(key: str) -> BaseSource:
    """Get a source adapter by key."""
    for source in ALL_SOURCES:
        if source.key == key:
            return source
    raise ValueError(f"Unknown source: {key}")
```

- [ ] **Step 4: Create stub adapters (needed for imports)**

These are minimal stubs — each will be fully implemented in subsequent tasks.

`src/chronicles/sources/claude_code.py`:
```python
"""Claude Code source adapter."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Transcript
from chronicles.sources.base import BaseSource


class ClaudeCodeSource(BaseSource):

    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def key(self) -> str:
        return "claude-code"

    def available(self) -> bool:
        return Path.home().joinpath(".claude", "projects").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with open(session_path) as f:
                first_line = f.readline().strip()
                if not first_line:
                    return False
                data = json.loads(first_line)
                return data.get("type") in ("human", "assistant", "summary")
        except (json.JSONDecodeError, OSError):
            return False

    def parse_session(self, session_path: Path) -> Transcript:
        raise NotImplementedError("Claude Code parser not yet implemented")

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        raise NotImplementedError("Claude Code discovery not yet implemented")
```

`src/chronicles/sources/copilot_cli.py`:
```python
"""Copilot CLI source adapter."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Transcript
from chronicles.sources.base import BaseSource


class CopilotCLISource(BaseSource):

    @property
    def name(self) -> str:
        return "Copilot CLI"

    @property
    def key(self) -> str:
        return "copilot-cli"

    def available(self) -> bool:
        return Path.home().joinpath(".copilot", "session-state").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with open(session_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    event_type = data.get("type", "")
                    if event_type in ("session.start", "turn.start", "turn.end"):
                        return True
                    return False
        except (json.JSONDecodeError, OSError):
            return False

    def parse_session(self, session_path: Path) -> Transcript:
        raise NotImplementedError("Copilot CLI parser not yet implemented")

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        raise NotImplementedError("Copilot CLI discovery not yet implemented")
```

`src/chronicles/sources/copilot_vscode.py`:
```python
"""Copilot VS Code source adapter."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Transcript
from chronicles.sources.base import BaseSource


class CopilotVSCodeSource(BaseSource):

    @property
    def name(self) -> str:
        return "Copilot VS Code"

    @property
    def key(self) -> str:
        return "copilot-vscode"

    def available(self) -> bool:
        return False  # complex discovery, checked per-file

    def sniff(self, session_path: Path) -> bool:
        try:
            with open(session_path) as f:
                data = json.load(f)
                return "sessions" in data and isinstance(data.get("sessions"), list)
        except (json.JSONDecodeError, OSError):
            return False

    def parse_session(self, session_path: Path) -> Transcript:
        raise NotImplementedError("Copilot VS Code parser not yet implemented")

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        raise NotImplementedError("Copilot VS Code discovery not yet implemented")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sources/test_detect.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/sources/ tests/test_sources/
git commit -m "feat: add source adapter base, stubs, and auto-detection"
```

---

### Task 6: Claude Code Source Adapter

**Files:**
- Modify: `src/chronicles/sources/claude_code.py`
- Create: `tests/fixtures/claude_code_session.jsonl`
- Create: `tests/test_sources/test_claude_code.py`

- [ ] **Step 1: Create test fixture**

Check Sift's Claude Code parser for the exact JSONL format:

Run: `head -5 ~/.claude/projects/*/sessions/*/*.jsonl 2>/dev/null | head -20`

Use the output to build a realistic fixture. `tests/fixtures/claude_code_session.jsonl` — a minimal session with: 1 user message, 1 assistant response with a tool call (Read), tool result, another assistant message with Edit, and tool result:

```jsonl
{"parentMessageId":"","isSidechain":false,"userType":"external","cwd":"/home/user/project","type":"human","message":{"role":"user","content":[{"type":"text","text":"Fix the bug in auth.py"}]},"timestamp":"2026-04-09T10:00:00.000Z"}
{"parentMessageId":"msg1","isSidechain":false,"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Let me read the file first."},{"type":"tool_use","id":"tu1","name":"Read","input":{"file_path":"/home/user/project/src/auth.py"}}],"model":"claude-opus-4-6"},"timestamp":"2026-04-09T10:00:05.000Z"}
{"parentMessageId":"tu1","isSidechain":false,"type":"tool_result","tool_use_id":"tu1","content":[{"type":"text","text":"1\tdef login(user, password):\n2\t    return check(user, pasword)\n"}],"timestamp":"2026-04-09T10:00:06.000Z"}
{"parentMessageId":"tr1","isSidechain":false,"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"I see a typo on line 2. Let me fix it."},{"type":"tool_use","id":"tu2","name":"Edit","input":{"file_path":"/home/user/project/src/auth.py","old_string":"pasword","new_string":"password"}}],"model":"claude-opus-4-6"},"timestamp":"2026-04-09T10:00:10.000Z"}
{"parentMessageId":"tu2","isSidechain":false,"type":"tool_result","tool_use_id":"tu2","content":[{"type":"text","text":"File edited successfully."}],"timestamp":"2026-04-09T10:00:11.000Z"}
{"parentMessageId":"tr2","isSidechain":false,"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Fixed the typo: `pasword` → `password` on line 2."}],"model":"claude-opus-4-6"},"timestamp":"2026-04-09T10:00:15.000Z"}
```

- [ ] **Step 2: Write failing tests**

`tests/test_sources/test_claude_code.py`:
```python
"""Tests for Claude Code source adapter."""
from pathlib import Path

from chronicles.models import Message
from chronicles.sources.claude_code import ClaudeCodeSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_session():
    source = ClaudeCodeSource()
    transcript = source.parse_session(FIXTURES / "claude_code_session.jsonl")

    assert transcript.source == "claude-code"
    assert transcript.model == "claude-opus-4-6"
    assert transcript.cwd == "/home/user/project"
    assert transcript.timestamp_start == "2026-04-09T10:00:00.000Z"
    assert transcript.timestamp_end == "2026-04-09T10:00:15.000Z"
    assert len(transcript.messages) > 0


def test_parse_session_message_roles():
    source = ClaudeCodeSource()
    transcript = source.parse_session(FIXTURES / "claude_code_session.jsonl")

    roles = [m.role for m in transcript.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_call" in roles
    assert "tool_result" in roles


def test_parse_session_tool_names():
    source = ClaudeCodeSource()
    transcript = source.parse_session(FIXTURES / "claude_code_session.jsonl")

    tool_calls = [m for m in transcript.messages if m.role == "tool_call"]
    tool_names = [m.tool_name for m in tool_calls]
    assert "Read" in tool_names
    assert "Edit" in tool_names


def test_parse_session_skips_sidechains(tmp_path):
    """Sidechain messages should be excluded."""
    import json
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps({"type": "human", "isSidechain": False, "cwd": "/tmp",
                     "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]},
                     "timestamp": "2026-04-09T10:00:00Z"}) + "\n"
        + json.dumps({"type": "assistant", "isSidechain": True,
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "sidechain"}],
                                 "model": "claude-opus-4-6"},
                     "timestamp": "2026-04-09T10:00:05Z"}) + "\n"
    )
    source = ClaudeCodeSource()
    transcript = source.parse_session(session)
    contents = [m.content for m in transcript.messages]
    assert "sidechain" not in contents
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sources/test_claude_code.py -v`
Expected: FAIL (NotImplementedError)

- [ ] **Step 4: Implement Claude Code parser**

Replace the stub `parse_session` in `src/chronicles/sources/claude_code.py`:

```python
"""Claude Code source adapter."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

# Claude Code tool names are already canonical
TOOL_NAME_MAP: dict[str, str] = {}


class ClaudeCodeSource(BaseSource):

    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def key(self) -> str:
        return "claude-code"

    def available(self) -> bool:
        return Path.home().joinpath(".claude", "projects").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with open(session_path) as f:
                first_line = f.readline().strip()
                if not first_line:
                    return False
                data = json.loads(first_line)
                return data.get("type") in ("human", "assistant", "summary")
        except (json.JSONDecodeError, OSError):
            return False

    def parse_session(self, session_path: Path) -> Transcript:
        messages: list[Message] = []
        model = ""
        cwd = ""
        ts_start = ""
        ts_end = ""

        with open(session_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("isSidechain", False):
                    continue

                event_type = event.get("type", "")
                timestamp = event.get("timestamp", "")

                if not ts_start and timestamp:
                    ts_start = timestamp
                if timestamp:
                    ts_end = timestamp

                if not cwd and event.get("cwd"):
                    cwd = event["cwd"]

                if event_type == "human":
                    msg_data = event.get("message", {})
                    text = self._extract_text(msg_data.get("content", []))
                    if text:
                        messages.append(Message(
                            role="user", content=text, timestamp=timestamp,
                        ))

                elif event_type == "assistant":
                    msg_data = event.get("message", {})
                    if not model and msg_data.get("model"):
                        model = msg_data["model"]

                    content_blocks = msg_data.get("content", [])
                    text_parts = []
                    for block in content_blocks:
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            # Emit text accumulated so far
                            if text_parts:
                                messages.append(Message(
                                    role="assistant",
                                    content="\n".join(text_parts),
                                    timestamp=timestamp,
                                ))
                                text_parts = []
                            # Emit tool call
                            raw_name = block.get("name", "")
                            canonical = TOOL_NAME_MAP.get(raw_name, raw_name)
                            messages.append(Message(
                                role="tool_call",
                                content="",
                                timestamp=timestamp,
                                tool_name=canonical,
                                tool_input=block.get("input", {}),
                            ))
                    if text_parts:
                        messages.append(Message(
                            role="assistant",
                            content="\n".join(text_parts),
                            timestamp=timestamp,
                        ))

                elif event_type == "tool_result":
                    result_content = event.get("content", [])
                    text = self._extract_text(result_content)
                    # Find the tool name from the most recent tool_call
                    tool_name = ""
                    for m in reversed(messages):
                        if m.role == "tool_call":
                            tool_name = m.tool_name
                            break
                    messages.append(Message(
                        role="tool_result",
                        content=text,
                        timestamp=timestamp,
                        tool_name=tool_name,
                    ))

        # Derive project/repo from cwd
        project = Path(cwd).name if cwd else ""

        return Transcript(
            session_id=session_path.stem,
            source=self.key,
            project=project,
            repository=project,
            branch="",  # not available in transcript
            cwd=cwd,
            timestamp_start=ts_start,
            timestamp_end=ts_end,
            model=model,
            messages=messages,
        )

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        base = Path.home() / ".claude" / "projects"
        if not base.exists():
            return []
        sessions = []
        for jsonl in base.rglob("*.jsonl"):
            if since and jsonl.stat().st_mtime < since.timestamp():
                continue
            sessions.append(jsonl)
        return sorted(sessions, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _extract_text(content_blocks: list) -> str:
        parts = []
        for block in content_blocks:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sources/test_claude_code.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/sources/claude_code.py tests/test_sources/test_claude_code.py tests/fixtures/claude_code_session.jsonl
git commit -m "feat: implement Claude Code source adapter"
```

---

### Task 7: Copilot CLI Source Adapter

**Files:**
- Modify: `src/chronicles/sources/copilot_cli.py`
- Create: `tests/fixtures/copilot_cli_session.jsonl`
- Create: `tests/test_sources/test_copilot_cli.py`

- [ ] **Step 1: Study Copilot CLI transcript format**

Run: `head -20 ~/.copilot/session-state/*/transcript.jsonl 2>/dev/null | head -40`

Use Sift's parser for reference:

Run: `cat /Users/gpavanello/Repositories/claude-token-analysis/sift/sources/copilot_cli.py | head -80`

- [ ] **Step 2: Create test fixture**

`tests/fixtures/copilot_cli_session.jsonl` — a minimal Copilot CLI session:

```jsonl
{"type":"session.start","timestamp":"2026-04-09T10:00:00.000Z","cwd":"/home/user/project"}
{"type":"turn.start","timestamp":"2026-04-09T10:00:01.000Z","request":{"type":"user-text","message":"Fix the bug in auth.py"}}
{"type":"tool.call","timestamp":"2026-04-09T10:00:03.000Z","tool":{"name":"readFile","parameters":{"path":"/home/user/project/src/auth.py"}}}
{"type":"tool.result","timestamp":"2026-04-09T10:00:04.000Z","tool":{"name":"readFile"},"result":"def login(user, password):\n    return check(user, pasword)\n"}
{"type":"message","timestamp":"2026-04-09T10:00:06.000Z","role":"assistant","content":"I see a typo. Let me fix it."}
{"type":"tool.call","timestamp":"2026-04-09T10:00:07.000Z","tool":{"name":"editFile","parameters":{"path":"/home/user/project/src/auth.py","oldText":"pasword","newText":"password"}}}
{"type":"tool.result","timestamp":"2026-04-09T10:00:08.000Z","tool":{"name":"editFile"},"result":"File edited."}
{"type":"message","timestamp":"2026-04-09T10:00:10.000Z","role":"assistant","content":"Fixed the typo."}
{"type":"turn.end","timestamp":"2026-04-09T10:00:11.000Z"}
{"type":"session.shutdown","timestamp":"2026-04-09T10:00:15.000Z","reason":"user_exit","modelMetrics":{"outputTokens":150},"codeChanges":{"linesAdded":1,"linesRemoved":1}}
```

- [ ] **Step 3: Write failing tests**

`tests/test_sources/test_copilot_cli.py`:
```python
"""Tests for Copilot CLI source adapter."""
from pathlib import Path

from chronicles.sources.copilot_cli import CopilotCLISource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_session():
    source = CopilotCLISource()
    transcript = source.parse_session(FIXTURES / "copilot_cli_session.jsonl")

    assert transcript.source == "copilot-cli"
    assert transcript.cwd == "/home/user/project"
    assert transcript.timestamp_start == "2026-04-09T10:00:00.000Z"
    assert len(transcript.messages) > 0


def test_parse_session_message_roles():
    source = CopilotCLISource()
    transcript = source.parse_session(FIXTURES / "copilot_cli_session.jsonl")

    roles = [m.role for m in transcript.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_call" in roles
    assert "tool_result" in roles


def test_tool_names_are_canonical():
    """Copilot tool names should be mapped to canonical names."""
    source = CopilotCLISource()
    transcript = source.parse_session(FIXTURES / "copilot_cli_session.jsonl")

    tool_calls = [m for m in transcript.messages if m.role == "tool_call"]
    tool_names = [m.tool_name for m in tool_calls]
    assert "Read" in tool_names  # readFile -> Read
    assert "Edit" in tool_names  # editFile -> Edit
    assert "readFile" not in tool_names  # raw name should not appear
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_sources/test_copilot_cli.py -v`
Expected: FAIL (NotImplementedError)

- [ ] **Step 5: Implement Copilot CLI parser**

Replace the stub in `src/chronicles/sources/copilot_cli.py`:

```python
"""Copilot CLI source adapter."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

TOOL_NAME_MAP = {
    "readFile": "Read",
    "editFile": "Edit",
    "runCommand": "Bash",
    "listFiles": "Glob",
    "searchFiles": "Grep",
    "writeFile": "Write",
}


class CopilotCLISource(BaseSource):

    @property
    def name(self) -> str:
        return "Copilot CLI"

    @property
    def key(self) -> str:
        return "copilot-cli"

    def available(self) -> bool:
        return Path.home().joinpath(".copilot", "session-state").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with open(session_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    event_type = data.get("type", "")
                    if event_type in ("session.start", "turn.start", "turn.end"):
                        return True
                    return False
        except (json.JSONDecodeError, OSError):
            return False

    def parse_session(self, session_path: Path) -> Transcript:
        messages: list[Message] = []
        cwd = ""
        ts_start = ""
        ts_end = ""
        model = ""

        with open(session_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")
                timestamp = event.get("timestamp", "")

                if not ts_start and timestamp:
                    ts_start = timestamp
                if timestamp:
                    ts_end = timestamp

                if event_type == "session.start":
                    cwd = event.get("cwd", "")

                elif event_type == "turn.start":
                    request = event.get("request", {})
                    user_text = request.get("message", "")
                    if user_text:
                        messages.append(Message(
                            role="user", content=user_text, timestamp=timestamp,
                        ))

                elif event_type == "message" and event.get("role") == "assistant":
                    content = event.get("content", "")
                    if content:
                        messages.append(Message(
                            role="assistant", content=content, timestamp=timestamp,
                        ))

                elif event_type == "tool.call":
                    tool = event.get("tool", {})
                    raw_name = tool.get("name", "")
                    canonical = TOOL_NAME_MAP.get(raw_name, raw_name)
                    messages.append(Message(
                        role="tool_call",
                        content="",
                        timestamp=timestamp,
                        tool_name=canonical,
                        tool_input=tool.get("parameters", {}),
                    ))

                elif event_type == "tool.result":
                    tool = event.get("tool", {})
                    raw_name = tool.get("name", "")
                    canonical = TOOL_NAME_MAP.get(raw_name, raw_name)
                    messages.append(Message(
                        role="tool_result",
                        content=event.get("result", ""),
                        timestamp=timestamp,
                        tool_name=canonical,
                    ))

        project = Path(cwd).name if cwd else ""

        return Transcript(
            session_id=session_path.stem,
            source=self.key,
            project=project,
            repository=project,
            branch="",
            cwd=cwd,
            timestamp_start=ts_start,
            timestamp_end=ts_end,
            model=model,
            messages=messages,
        )

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        base = Path.home() / ".copilot" / "session-state"
        if not base.exists():
            return []
        sessions = []
        for jsonl in base.rglob("*.jsonl"):
            if since and jsonl.stat().st_mtime < since.timestamp():
                continue
            sessions.append(jsonl)
        return sorted(sessions, key=lambda p: p.stat().st_mtime)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_sources/test_copilot_cli.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicles/sources/copilot_cli.py tests/test_sources/test_copilot_cli.py tests/fixtures/copilot_cli_session.jsonl
git commit -m "feat: implement Copilot CLI source adapter with tool name mapping"
```

---

### Task 8: Copilot VS Code Source Adapter

**Files:**
- Modify: `src/chronicles/sources/copilot_vscode.py`
- Create: `tests/fixtures/copilot_vscode_session.json`
- Create: `tests/test_sources/test_copilot_vscode.py`

- [ ] **Step 1: Study VS Code Copilot format**

Check Sift's VS Code parser for the JSON structure:

Run: `cat /Users/gpavanello/Repositories/claude-token-analysis/sift/sources/vscode_copilot.py | head -80`

- [ ] **Step 2: Create test fixture**

`tests/fixtures/copilot_vscode_session.json`:
```json
{
  "version": 2,
  "sessions": [
    {
      "sessionId": "vscode-session-001",
      "requests": [
        {
          "message": {"text": "Fix the bug in auth.py"},
          "timestamp": 1744192800000,
          "result": {
            "value": "I see a typo. Let me fix it.\nFixed the typo.",
            "metadata": {
              "toolCallRounds": [
                {
                  "toolCalls": [
                    {"name": "readFile", "input": {"path": "src/auth.py"}},
                    {"name": "editFile", "input": {"path": "src/auth.py", "oldText": "pasword", "newText": "password"}}
                  ]
                }
              ]
            }
          }
        }
      ]
    }
  ]
}
```

- [ ] **Step 3: Write failing tests**

`tests/test_sources/test_copilot_vscode.py`:
```python
"""Tests for Copilot VS Code source adapter."""
from pathlib import Path

from chronicles.sources.copilot_vscode import CopilotVSCodeSource

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_session():
    source = CopilotVSCodeSource()
    transcript = source.parse_session(FIXTURES / "copilot_vscode_session.json")

    assert transcript.source == "copilot-vscode"
    assert transcript.session_id == "vscode-session-001"
    assert len(transcript.messages) > 0


def test_parse_session_message_roles():
    source = CopilotVSCodeSource()
    transcript = source.parse_session(FIXTURES / "copilot_vscode_session.json")

    roles = [m.role for m in transcript.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool_call" in roles


def test_tool_names_are_canonical():
    source = CopilotVSCodeSource()
    transcript = source.parse_session(FIXTURES / "copilot_vscode_session.json")

    tool_calls = [m for m in transcript.messages if m.role == "tool_call"]
    tool_names = [m.tool_name for m in tool_calls]
    assert "Read" in tool_names
    assert "Edit" in tool_names
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_sources/test_copilot_vscode.py -v`
Expected: FAIL (NotImplementedError)

- [ ] **Step 5: Implement VS Code Copilot parser**

Replace the stub in `src/chronicles/sources/copilot_vscode.py`:

```python
"""Copilot VS Code source adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

TOOL_NAME_MAP = {
    "readFile": "Read",
    "editFile": "Edit",
    "runCommand": "Bash",
    "listFiles": "Glob",
    "searchFiles": "Grep",
    "writeFile": "Write",
}


class CopilotVSCodeSource(BaseSource):

    @property
    def name(self) -> str:
        return "Copilot VS Code"

    @property
    def key(self) -> str:
        return "copilot-vscode"

    def available(self) -> bool:
        return False

    def sniff(self, session_path: Path) -> bool:
        try:
            with open(session_path) as f:
                data = json.load(f)
                return "sessions" in data and isinstance(data.get("sessions"), list)
        except (json.JSONDecodeError, OSError):
            return False

    def parse_session(self, session_path: Path) -> Transcript:
        with open(session_path) as f:
            data = json.load(f)

        messages: list[Message] = []
        session_id = ""
        ts_start = ""
        ts_end = ""

        for session in data.get("sessions", []):
            if not session_id:
                session_id = session.get("sessionId", session_path.stem)

            for request in session.get("requests", []):
                # User message
                user_text = request.get("message", {}).get("text", "")
                ts_ms = request.get("timestamp", 0)
                timestamp = self._ms_to_iso(ts_ms) if ts_ms else ""

                if not ts_start and timestamp:
                    ts_start = timestamp
                if timestamp:
                    ts_end = timestamp

                if user_text:
                    messages.append(Message(
                        role="user", content=user_text, timestamp=timestamp,
                    ))

                # Tool calls from result metadata
                result = request.get("result", {})
                metadata = result.get("metadata", {})
                for round_data in metadata.get("toolCallRounds", []):
                    for tc in round_data.get("toolCalls", []):
                        raw_name = tc.get("name", "")
                        canonical = TOOL_NAME_MAP.get(raw_name, raw_name)
                        messages.append(Message(
                            role="tool_call",
                            content="",
                            timestamp=timestamp,
                            tool_name=canonical,
                            tool_input=tc.get("input", {}),
                        ))

                # Assistant response
                assistant_text = result.get("value", "")
                if assistant_text:
                    messages.append(Message(
                        role="assistant", content=assistant_text, timestamp=timestamp,
                    ))

        return Transcript(
            session_id=session_id,
            source=self.key,
            project="",
            repository="",
            branch="",
            cwd="",
            timestamp_start=ts_start,
            timestamp_end=ts_end,
            model="",
            messages=messages,
        )

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        return []

    @staticmethod
    def _ms_to_iso(ms: int) -> str:
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.isoformat()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_sources/test_copilot_vscode.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicles/sources/copilot_vscode.py tests/test_sources/test_copilot_vscode.py tests/fixtures/copilot_vscode_session.json
git commit -m "feat: implement Copilot VS Code source adapter"
```

---

### Task 9: Transcript Cleaner

**Files:**
- Create: `src/chronicles/cleaner.py`
- Create: `tests/test_cleaner.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cleaner.py`:
```python
"""Tests for transcript cleaner."""
from chronicles.cleaner import clean_transcript
from chronicles.models import Message, Transcript, CleanedTranscript


def _make_transcript(messages: list[Message]) -> Transcript:
    return Transcript(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus", messages=messages,
    )


def test_strips_read_tool_results():
    messages = [
        Message(role="user", content="read the file", timestamp="T1"),
        Message(role="tool_call", content="", timestamp="T2", tool_name="Read",
                tool_input={"file_path": "src/main.py"}),
        Message(role="tool_result", content="huge file content here...", timestamp="T3",
                tool_name="Read"),
        Message(role="assistant", content="I see the file.", timestamp="T4"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    # Read result should be stripped (empty content)
    assert all(m.content == "" for m in tool_results if m.tool_name == "Read")


def test_keeps_edit_tool_results():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Edit",
                tool_input={"file_path": "a.py", "old_string": "x", "new_string": "y"}),
        Message(role="tool_result", content="File edited successfully.", timestamp="T2",
                tool_name="Edit"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert any(m.content == "File edited successfully." for m in tool_results)


def test_keeps_write_tool_results():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Write",
                tool_input={"file_path": "a.py", "content": "hello"}),
        Message(role="tool_result", content="File written.", timestamp="T2",
                tool_name="Write"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert any(m.content == "File written." for m in tool_results)


def test_strips_grep_glob_bash_results():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Grep",
                tool_input={"pattern": "foo"}),
        Message(role="tool_result", content="lots of matches...", timestamp="T2",
                tool_name="Grep"),
        Message(role="tool_call", content="", timestamp="T3", tool_name="Glob",
                tool_input={"pattern": "*.py"}),
        Message(role="tool_result", content="file1.py\nfile2.py", timestamp="T4",
                tool_name="Glob"),
        Message(role="tool_call", content="", timestamp="T5", tool_name="Bash",
                tool_input={"command": "ls"}),
        Message(role="tool_result", content="big output...", timestamp="T6",
                tool_name="Bash"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_results = [m for chunk in result.chunks for m in chunk if m.role == "tool_result"]
    assert all(m.content == "" for m in tool_results)


def test_tool_calls_always_preserved():
    messages = [
        Message(role="tool_call", content="", timestamp="T1", tool_name="Read",
                tool_input={"file_path": "a.py"}),
        Message(role="tool_result", content="content", timestamp="T2", tool_name="Read"),
    ]
    result = clean_transcript(_make_transcript(messages))
    tool_calls = [m for chunk in result.chunks for m in chunk if m.role == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "Read"
    assert tool_calls[0].tool_input == {"file_path": "a.py"}


def test_single_chunk_for_small_transcript():
    messages = [
        Message(role="user", content="hello", timestamp="T1"),
        Message(role="assistant", content="hi", timestamp="T2"),
    ]
    result = clean_transcript(_make_transcript(messages))
    assert len(result.chunks) == 1


def test_metadata_preserved():
    messages = [Message(role="user", content="hello", timestamp="T1")]
    result = clean_transcript(_make_transcript(messages))
    assert result.metadata.session_id == "test"
    assert result.metadata.source == "claude-code"
    assert result.metadata.project == "proj"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cleaner.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement cleaner**

`src/chronicles/cleaner.py`:
```python
"""Transcript cleaner — filters tool results and chunks by turns."""
from __future__ import annotations

from chronicles.models import (
    Message, Transcript, CleanedTranscript, TranscriptMetadata,
)

# Tool results to strip (high-volume, low-signal)
STRIP_TOOLS = frozenset({"Read", "Grep", "Glob", "Bash", "ls", "cat"})

# Tool results to keep (high-signal)
KEEP_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def clean_transcript(transcript: Transcript) -> CleanedTranscript:
    """Filter tool results and organize into turn-based chunks."""
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

    filtered = _filter_tool_results(transcript.messages)
    chunks = _chunk_by_turns(filtered)

    return CleanedTranscript(metadata=metadata, chunks=chunks)


def _filter_tool_results(messages: list[Message]) -> list[Message]:
    """Strip results from high-volume tools, keep results from high-signal tools."""
    result: list[Message] = []
    for msg in messages:
        if msg.role == "tool_result" and msg.tool_name in STRIP_TOOLS:
            # Keep the message but empty the content
            result.append(Message(
                role=msg.role,
                content="",
                timestamp=msg.timestamp,
                tool_name=msg.tool_name,
            ))
        else:
            result.append(msg)
    return result


def _chunk_by_turns(messages: list[Message]) -> list[list[Message]]:
    """Group messages into turns. A turn starts with a user message.

    For now, returns a single chunk (no token budget).
    Chunking logic will split at turn boundaries when needed.
    """
    if not messages:
        return [[]]
    return [messages]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cleaner.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/cleaner.py tests/test_cleaner.py
git commit -m "feat: add transcript cleaner with tool result filtering"
```

---

### Task 10: Extractor Base + Copilot CLI Extractor

**Files:**
- Create: `src/chronicles/extractors/base.py`
- Modify: `src/chronicles/extractors/__init__.py`
- Create: `src/chronicles/extractors/copilot_cli.py`
- Create: `src/chronicles/extractors/claude_code.py`
- Create: `tests/test_extractors/test_copilot_cli.py`
- Create: `tests/test_extractors/test_claude_code.py`

- [ ] **Step 1: Write failing tests**

`tests/test_extractors/test_copilot_cli.py`:
```python
"""Tests for Copilot CLI extractor."""
import json
from unittest.mock import patch, MagicMock

from chronicles.config import LLMConfig
from chronicles.extractors.copilot_cli import CopilotCLIExtractor
from chronicles.models import (
    Message, CleanedTranscript, TranscriptMetadata, ExtractionResult,
)


def _make_cleaned_transcript() -> CleanedTranscript:
    meta = TranscriptMetadata(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z", model="opus",
    )
    messages = [
        Message(role="user", content="Fix the bug", timestamp="T1"),
        Message(role="assistant", content="Fixed it.", timestamp="T2"),
    ]
    return CleanedTranscript(metadata=meta, chunks=[messages])


def test_builds_prompt():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    transcript = _make_cleaned_transcript()
    prompt = extractor._build_prompt(transcript)
    assert "Fix the bug" in prompt
    assert "Fixed it." in prompt


def test_parses_llm_json_response():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)

    raw_json = json.dumps({
        "branch": "fix/bug",
        "status": "complete",
        "tags": ["bugfix"],
        "duration": "5min",
        "files_changed": ["src/auth.py"],
        "objective": "Fix the bug",
        "outcome": "Bug fixed",
        "decisions": [],
        "problems": [],
        "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [],
    })

    result = extractor._parse_response(raw_json)
    assert isinstance(result, ExtractionResult)
    assert result.branch == "fix/bug"
    assert result.status == "complete"


@patch("subprocess.run")
def test_extract_calls_copilot(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "branch": "fix/bug", "status": "complete", "tags": [],
            "duration": "5min", "files_changed": [],
            "objective": "Fix", "outcome": "Fixed",
            "decisions": [], "problems": [], "discovered": [],
            "continuity": {"unfinished": [], "open_questions": [], "next": []},
            "wiki_instructions": [],
        }),
    )

    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    result = extractor.extract(_make_cleaned_transcript())

    assert result.branch == "fix/bug"
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "copilot" in cmd[0]
    assert "--model" in cmd
```

`tests/test_extractors/test_claude_code.py`:
```python
"""Tests for Claude Code extractor."""
import json
from unittest.mock import patch, MagicMock

from chronicles.config import LLMConfig
from chronicles.extractors.claude_code import ClaudeCodeExtractor
from chronicles.models import (
    Message, CleanedTranscript, TranscriptMetadata,
)


def _make_cleaned_transcript() -> CleanedTranscript:
    meta = TranscriptMetadata(
        session_id="test", source="claude-code", project="proj",
        repository="repo", branch="main", cwd="/tmp",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z", model="opus",
    )
    messages = [
        Message(role="user", content="Fix the bug", timestamp="T1"),
        Message(role="assistant", content="Fixed it.", timestamp="T2"),
    ]
    return CleanedTranscript(metadata=meta, chunks=[messages])


@patch("subprocess.run")
def test_extract_calls_claude(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "branch": "fix/bug", "status": "complete", "tags": [],
            "duration": "5min", "files_changed": [],
            "objective": "Fix", "outcome": "Fixed",
            "decisions": [], "problems": [], "discovered": [],
            "continuity": {"unfinished": [], "open_questions": [], "next": []},
            "wiki_instructions": [],
        }),
    )

    config = LLMConfig(provider="claude-code", model="claude-opus-4-6")
    extractor = ClaudeCodeExtractor(config)
    result = extractor.extract(_make_cleaned_transcript())

    assert result.branch == "fix/bug"
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "claude" in cmd[0]
    assert "--print" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extractors/ -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement extractor base**

`src/chronicles/extractors/base.py`:
```python
"""Base extractor interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from chronicles.config import LLMConfig
from chronicles.models import CleanedTranscript, ExtractionResult


class BaseExtractor(ABC):
    """Interface for LLM-backed knowledge extractors."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def extract(self, transcript: CleanedTranscript) -> ExtractionResult:
        """Extract structured knowledge from a cleaned transcript."""
```

- [ ] **Step 4: Implement Copilot CLI extractor**

`src/chronicles/extractors/copilot_cli.py`:
```python
"""Copilot CLI extractor — runs copilot -p to extract knowledge."""
from __future__ import annotations

import json
import subprocess
import textwrap

from chronicles.config import LLMConfig
from chronicles.extractors.base import BaseExtractor
from chronicles.models import CleanedTranscript, ExtractionResult, Message

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a knowledge extraction engine. You read agent session transcripts
    and extract structured knowledge.

    Return ONLY valid JSON matching this schema (no markdown fences, no explanation):
    {
      "branch": "string — branch name or short description",
      "status": "complete | partial | failed | exploratory",
      "tags": ["string"],
      "duration": "string — estimated duration",
      "files_changed": ["string — file paths touched"],
      "objective": "string — what the session set out to do",
      "outcome": "string — what was actually achieved",
      "decisions": [{"description": "string", "rationale": "string"}],
      "problems": [{"description": "string", "root_cause": "string", "dead_end": bool}],
      "discovered": [{"type": "convention|missing-context|workaround|pattern|trap", "description": "string"}],
      "continuity": {
        "unfinished": ["string"],
        "open_questions": ["string"],
        "next": ["string"]
      },
      "wiki_instructions": [
        {
          "action": "create | update",
          "path": "wiki/articles/slug.md or wiki/queries/slug.md",
          "data": {
            "title": "string",
            "type": "convention | decision | pattern | trap | workaround | concept",
            "confidence": "low | medium",
            "tags": ["string"],
            "body": "string",
            "evidence": ["string"],
            "implications": ["string"]
          }
        }
      ]
    }
""")


class CopilotCLIExtractor(BaseExtractor):
    """Extract knowledge using copilot -p."""

    def extract(self, transcript: CleanedTranscript) -> ExtractionResult:
        prompt = self._build_prompt(transcript)
        cmd = [
            "copilot", "-p", prompt,
            "--model", self.config.model,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"copilot failed: {result.stderr}")
        return self._parse_response(result.stdout)

    def _build_prompt(self, transcript: CleanedTranscript) -> str:
        lines = [_SYSTEM_PROMPT, "\n--- TRANSCRIPT ---\n"]
        for chunk in transcript.chunks:
            for msg in chunk:
                lines.append(self._format_message(msg))
        lines.append("\n--- END TRANSCRIPT ---\n")
        lines.append("Extract structured knowledge from the transcript above. Return ONLY JSON.")
        return "\n".join(lines)

    def _parse_response(self, raw: str) -> ExtractionResult:
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        text = text.strip()

        data = json.loads(text)
        return ExtractionResult(
            branch=data["branch"],
            status=data["status"],
            tags=data.get("tags", []),
            duration=data.get("duration", ""),
            files_changed=data.get("files_changed", []),
            objective=data["objective"],
            outcome=data["outcome"],
            decisions=data.get("decisions", []),
            problems=data.get("problems", []),
            discovered=data.get("discovered", []),
            continuity=data.get("continuity", {"unfinished": [], "open_questions": [], "next": []}),
            wiki_instructions=data.get("wiki_instructions", []),
        )

    @staticmethod
    def _format_message(msg: Message) -> str:
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
```

- [ ] **Step 5: Implement Claude Code extractor**

`src/chronicles/extractors/claude_code.py`:
```python
"""Claude Code extractor — runs claude --print to extract knowledge."""
from __future__ import annotations

import json
import subprocess

from chronicles.config import LLMConfig
from chronicles.extractors.base import BaseExtractor
from chronicles.extractors.copilot_cli import CopilotCLIExtractor
from chronicles.models import CleanedTranscript, ExtractionResult


class ClaudeCodeExtractor(BaseExtractor):
    """Extract knowledge using claude --print."""

    def extract(self, transcript: CleanedTranscript) -> ExtractionResult:
        # Reuse prompt building and response parsing from CopilotCLIExtractor
        copilot_ext = CopilotCLIExtractor(self.config)
        prompt = copilot_ext._build_prompt(transcript)

        cmd = ["claude", "--print", prompt]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude failed: {result.stderr}")
        return copilot_ext._parse_response(result.stdout)
```

- [ ] **Step 6: Implement extractor factory**

`src/chronicles/extractors/__init__.py`:
```python
"""Extractor registry."""
from __future__ import annotations

from chronicles.config import LLMConfig
from chronicles.extractors.base import BaseExtractor
from chronicles.extractors.copilot_cli import CopilotCLIExtractor
from chronicles.extractors.claude_code import ClaudeCodeExtractor

_EXTRACTORS: dict[str, type[BaseExtractor]] = {
    "copilot-cli": CopilotCLIExtractor,
    "claude-code": ClaudeCodeExtractor,
}


def get_extractor(config: LLMConfig) -> BaseExtractor:
    """Get an extractor instance for the configured provider."""
    cls = _EXTRACTORS.get(config.provider)
    if cls is None:
        raise ValueError(
            f"Unknown extractor provider: {config.provider}. "
            f"Available: {', '.join(_EXTRACTORS)}"
        )
    return cls(config)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_extractors/ -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/chronicles/extractors/ tests/test_extractors/
git commit -m "feat: add pluggable LLM extractors (copilot-cli, claude-code)"
```

---

### Task 11: Writer

**Files:**
- Create: `src/chronicles/writer.py`
- Create: `tests/test_writer.py`

- [ ] **Step 1: Write failing tests**

`tests/test_writer.py`:
```python
"""Tests for the writer — records, CHRONICLES.md, wiki pages."""
from pathlib import Path

from chronicles.models import ExtractionResult
from chronicles.templates import TemplateRenderer
from chronicles.writer import write_record, append_chronicles_entry, write_wiki_pages


def _make_result() -> ExtractionResult:
    return ExtractionResult(
        branch="feat/oauth",
        status="complete",
        tags=["oauth", "auth"],
        duration="30min",
        files_changed=["src/auth.py"],
        objective="Add OAuth",
        outcome="OAuth works",
        decisions=[{"description": "Use refresh tokens", "rationale": "more secure"}],
        problems=[],
        discovered=[{"type": "convention", "description": "Use _conn suffix"}],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[
            {
                "action": "create",
                "path": "wiki/articles/conn-suffix.md",
                "data": {
                    "title": "Connection Suffix",
                    "type": "convention",
                    "confidence": "low",
                    "tags": ["naming"],
                    "body": "Use _conn suffix.",
                    "evidence": ["Found in oauth session"],
                    "implications": ["Must follow"],
                },
            }
        ],
    )


def test_write_record(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    path = write_record(chronicles_dir, result, "claude-code", "2026-04-09", renderer)

    assert path.exists()
    assert path.name == "2026-04-09_feat-oauth.md"
    content = path.read_text()
    assert "feat/oauth" in content
    assert "Add OAuth" in content


def test_append_chronicles_entry(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    append_chronicles_entry(chronicles_dir, result, "2026-04-09", renderer)

    content = (chronicles_dir / "CHRONICLES.md").read_text()
    assert "feat-oauth" in content
    assert "Add OAuth" in content


def test_write_wiki_pages(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    write_wiki_pages(chronicles_dir, result, "2026-04-09", renderer)

    article = chronicles_dir / "wiki" / "articles" / "conn-suffix.md"
    assert article.exists()
    content = article.read_text()
    assert "Connection Suffix" in content
    assert "confidence: low" in content


def test_write_record_updates_frontmatter_count(chronicles_dir):
    renderer = TemplateRenderer()
    result = _make_result()
    append_chronicles_entry(chronicles_dir, result, "2026-04-09", renderer)

    content = (chronicles_dir / "CHRONICLES.md").read_text()
    assert "record_count: 1" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_writer.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement writer**

`src/chronicles/writer.py`:
```python
"""Writer — produces records, CHRONICLES.md entries, and wiki pages."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from chronicles.models import ExtractionResult
from chronicles.templates import TemplateRenderer

STATUS_ICONS = {
    "complete": "✅",
    "partial": "⚠️",
    "failed": "❌",
    "exploratory": "🔍",
}

STATUS_LABELS = {
    "complete": "Complete",
    "partial": "Partial",
    "failed": "Failed",
    "exploratory": "Exploratory",
}


def write_record(
    chronicles_dir: Path,
    result: ExtractionResult,
    source: str,
    date_str: str,
    renderer: TemplateRenderer,
) -> Path:
    """Write a record file to records/."""
    filename = f"{date_str}_{result.slug}.md"
    path = chronicles_dir / "records" / filename

    data = {
        "date": date_str,
        "branch": result.branch,
        "status": result.status,
        "tags": result.tags,
        "source": source,
        "duration": result.duration,
        "files_changed": result.files_changed,
        "objective": result.objective,
        "outcome": result.outcome,
        "decisions": result.decisions,
        "problems": result.problems,
        "discovered": result.discovered,
        "continuity": result.continuity,
    }

    path.write_text(renderer.render("record", data))
    return path


def append_chronicles_entry(
    chronicles_dir: Path,
    result: ExtractionResult,
    date_str: str,
    renderer: TemplateRenderer,
) -> None:
    """Append an entry to CHRONICLES.md and update frontmatter."""
    chronicles_path = chronicles_dir / "CHRONICLES.md"
    content = chronicles_path.read_text()

    # Render entry
    entry_data = {
        "date": date_str,
        "slug": result.slug,
        "branch": result.branch,
        "status_icon": STATUS_ICONS.get(result.status, ""),
        "status_label": STATUS_LABELS.get(result.status, result.status),
        "objective": result.objective,
        "outcome": result.outcome,
        "tags_as_hashtags": " ".join(f"#{t}" for t in result.tags),
    }
    entry = renderer.render("chronicles_entry", entry_data)

    # Update record_count in frontmatter
    count_match = re.search(r"record_count: (\d+)", content)
    if count_match:
        old_count = int(count_match.group(1))
        content = content.replace(
            f"record_count: {old_count}",
            f"record_count: {old_count + 1}",
        )

    # Update last_updated
    content = re.sub(
        r"last_updated: .+",
        f"last_updated: {date_str}",
        content,
        count=1,
    )

    # Append entry after the last line
    content = content.rstrip() + "\n\n" + entry + "\n"
    chronicles_path.write_text(content)


def write_wiki_pages(
    chronicles_dir: Path,
    result: ExtractionResult,
    date_str: str,
    renderer: TemplateRenderer,
) -> None:
    """Create or update wiki pages from wiki_instructions."""
    record_ref = f"{date_str}_{result.slug}"

    for instruction in result.wiki_instructions:
        action = instruction.get("action", "create")
        rel_path = instruction.get("path", "")
        data = instruction.get("data", {})

        if not rel_path:
            continue

        page_path = chronicles_dir / rel_path
        page_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine template from path
        if "/articles/" in rel_path:
            template = "wiki_article"
            data.setdefault("sources", [record_ref])
            data.setdefault("first_seen", date_str)
            data.setdefault("last_confirmed", date_str)
        elif "/queries/" in rel_path:
            template = "wiki_query"
            data.setdefault("date", date_str)
        elif "/categories/" in rel_path:
            template = "wiki_category"
        else:
            continue

        if action == "create" or not page_path.exists():
            page_path.write_text(renderer.render(template, data))
        elif action == "update" and page_path.exists():
            # For updates, re-render with merged data
            # (simple strategy: overwrite — lint handles dedup)
            page_path.write_text(renderer.render(template, data))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_writer.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/writer.py tests/test_writer.py
git commit -m "feat: add writer for records, CHRONICLES.md, and wiki pages"
```

---

### Task 12: Linter

**Files:**
- Create: `src/chronicles/linter.py`
- Create: `tests/test_linter.py`

- [ ] **Step 1: Write failing tests**

`tests/test_linter.py`:
```python
"""Tests for the linter."""
from pathlib import Path

from chronicles.linter import lint, LintReport


def _write_article(chronicles_dir: Path, name: str, confidence: str = "low",
                   article_type: str = "convention", tags: list[str] | None = None,
                   sources: list[str] | None = None) -> Path:
    tags = tags or ["test"]
    sources = sources or ["2026-04-09_test"]
    path = chronicles_dir / "wiki" / "articles" / f"{name}.md"
    path.write_text(
        f"---\ntype: {article_type}\nconfidence: {confidence}\n"
        f"sources:\n"
        + "".join(f'  - "[[{s}]]"\n' for s in sources)
        + f"first_seen: 2026-04-01\nlast_confirmed: 2026-04-09\n"
        f"tags: {tags}\n---\n\n# {name}\n\nSome content.\n"
    )
    return path


def test_lint_valid_structure(chronicles_dir):
    _write_article(chronicles_dir, "test-article")
    report = lint(chronicles_dir)
    assert isinstance(report, LintReport)
    assert len(report.errors) == 0


def test_lint_detects_missing_frontmatter(chronicles_dir):
    path = chronicles_dir / "wiki" / "articles" / "bad.md"
    path.write_text("# No frontmatter\nJust content.\n")
    report = lint(chronicles_dir)
    assert any("frontmatter" in e.lower() for e in report.errors)


def test_lint_detects_broken_wikilinks(chronicles_dir):
    path = chronicles_dir / "wiki" / "articles" / "test.md"
    path.write_text(
        "---\ntype: convention\nconfidence: low\n"
        'sources:\n  - "[[2026-04-09_test]]"\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-09\ntags: [test]\n---\n\n"
        "# Test\n\nSee [[nonexistent-article]].\n"
    )
    report = lint(chronicles_dir)
    assert any("nonexistent-article" in w for w in report.warnings)


def test_lint_promotes_low_to_medium(chronicles_dir):
    """Article with 2+ sources gets promoted from low to medium."""
    _write_article(chronicles_dir, "multi-source",
                   confidence="low",
                   sources=["2026-04-01_session-a", "2026-04-05_session-b"])
    report = lint(chronicles_dir)
    content = (chronicles_dir / "wiki" / "articles" / "multi-source.md").read_text()
    assert "confidence: medium" in content


def test_lint_promotes_medium_to_high(chronicles_dir):
    """Article with N+ sources gets promoted from medium to high."""
    _write_article(chronicles_dir, "well-confirmed",
                   confidence="medium",
                   sources=["s1", "s2", "s3"])  # default threshold is 3
    report = lint(chronicles_dir)
    content = (chronicles_dir / "wiki" / "articles" / "well-confirmed.md").read_text()
    assert "confidence: high" in content


def test_lint_regenerates_gold(chronicles_dir):
    _write_article(chronicles_dir, "gold-article",
                   confidence="high", article_type="convention")
    report = lint(chronicles_dir)
    gold = (chronicles_dir / "GOLD.md").read_text()
    assert "gold-article" in gold


def test_lint_gold_excludes_low_confidence(chronicles_dir):
    _write_article(chronicles_dir, "low-article", confidence="low")
    report = lint(chronicles_dir)
    gold = (chronicles_dir / "GOLD.md").read_text()
    assert "low-article" not in gold
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_linter.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement linter**

`src/chronicles/linter.py`:
```python
"""Linter — validates structure, manages confidence, regenerates GOLD.md."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from chronicles.config import load_config
from chronicles.templates import TemplateRenderer

# Article types → GOLD.md section names
TYPE_TO_SECTION = {
    "convention": "Conventions",
    "decision": "Architecture Decisions",
    "pattern": "Patterns",
    "trap": "Known Traps",
    "workaround": "Workarounds",
    "concept": "Concepts",
}


@dataclass
class LintReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)
    gold_count: int = 0


def lint(chronicles_dir: Path) -> LintReport:
    """Run all lint checks on the chronicles directory."""
    config = load_config(chronicles_dir)
    report = LintReport()

    articles = _load_articles(chronicles_dir, report)
    _check_wikilinks(chronicles_dir, articles, report)
    _manage_confidence(articles, config.confidence.promotion_threshold, report)
    _regenerate_gold(chronicles_dir, articles, report)

    return report


def _load_articles(chronicles_dir: Path, report: LintReport) -> list[dict]:
    """Load all wiki articles with parsed frontmatter."""
    articles_dir = chronicles_dir / "wiki" / "articles"
    if not articles_dir.exists():
        return []

    articles = []
    for path in sorted(articles_dir.glob("*.md")):
        content = path.read_text()
        fm = _parse_frontmatter(content)
        if fm is None:
            report.errors.append(f"Missing or invalid frontmatter: {path.name}")
            continue

        required = ["type", "confidence"]
        for field_name in required:
            if field_name not in fm:
                report.errors.append(f"Missing required field '{field_name}' in {path.name}")

        articles.append({
            "path": path,
            "frontmatter": fm,
            "content": content,
            "name": path.stem,
        })

    return articles


def _parse_frontmatter(content: str) -> dict | None:
    """Extract YAML frontmatter from markdown."""
    match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def _check_wikilinks(chronicles_dir: Path, articles: list[dict], report: LintReport) -> None:
    """Check for broken wikilinks across all wiki files."""
    known_names = {a["name"] for a in articles}
    # Also include records and queries
    records_dir = chronicles_dir / "records"
    if records_dir.exists():
        known_names.update(p.stem for p in records_dir.glob("*.md"))
    queries_dir = chronicles_dir / "wiki" / "queries"
    if queries_dir.exists():
        known_names.update(p.stem for p in queries_dir.glob("*.md"))

    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

    for article in articles:
        for match in wikilink_re.finditer(article["content"]):
            link_target = match.group(1).strip()
            # Normalize to filename form
            slug = link_target.lower().replace(" ", "-")
            if slug not in known_names and link_target not in known_names:
                report.warnings.append(
                    f"Broken wikilink [[{link_target}]] in {article['name']}"
                )


def _manage_confidence(articles: list[dict], threshold: int, report: LintReport) -> None:
    """Promote or contest article confidence levels."""
    for article in articles:
        fm = article["frontmatter"]
        confidence = fm.get("confidence", "low")
        sources = fm.get("sources", [])
        source_count = len(sources)

        new_confidence = confidence

        if confidence == "low" and source_count >= 2:
            new_confidence = "medium"
        elif confidence == "medium" and source_count >= threshold:
            new_confidence = "high"

        if new_confidence != confidence:
            report.promotions.append(
                f"{article['name']}: {confidence} -> {new_confidence}"
            )
            # Update the file
            content = article["content"]
            content = content.replace(
                f"confidence: {confidence}",
                f"confidence: {new_confidence}",
                1,
            )
            article["path"].write_text(content)
            article["frontmatter"]["confidence"] = new_confidence


def _regenerate_gold(chronicles_dir: Path, articles: list[dict], report: LintReport) -> None:
    """Rebuild GOLD.md from all confidence: high articles."""
    renderer = TemplateRenderer()

    high_articles = [
        a for a in articles
        if a["frontmatter"].get("confidence") == "high"
    ]

    # Group by type
    groups_dict: dict[str, list[dict]] = {}
    for article in high_articles:
        article_type = article["frontmatter"].get("type", "concept")
        section = TYPE_TO_SECTION.get(article_type, "Other")
        groups_dict.setdefault(section, [])
        # Extract first line of body as summary
        body_lines = article["content"].split("---", 2)[-1].strip().split("\n")
        summary = ""
        for line in body_lines:
            line = line.strip()
            if line and not line.startswith("#"):
                summary = line
                break
        groups_dict[section].append({
            "title": article["name"],
            "summary": summary,
        })

    # Sort groups by predefined order
    section_order = list(TYPE_TO_SECTION.values()) + ["Other"]
    groups = []
    for section in section_order:
        if section in groups_dict:
            groups.append((section, groups_dict[section]))

    data = {
        "date": _today(),
        "count": len(high_articles),
        "groups": groups,
    }

    gold_path = chronicles_dir / "GOLD.md"
    gold_path.write_text(renderer.render("gold", data))
    report.gold_count = len(high_articles)


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linter.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: add linter with validation, confidence lifecycle, GOLD.md regen"
```

---

### Task 13: CLI Wiring

**Files:**
- Create: `src/chronicles/cli.py`

- [ ] **Step 1: Implement CLI with argparse**

`src/chronicles/cli.py`:
```python
"""CLI entry point — chronicles ingest and chronicles lint."""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chronicles.config import load_config
from chronicles.cleaner import clean_transcript
from chronicles.extractors import get_extractor
from chronicles.linter import lint
from chronicles.sources import detect_source, get_source, ALL_SOURCES
from chronicles.templates import TemplateRenderer
from chronicles.writer import write_record, append_chronicles_entry, write_wiki_pages


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="chronicles",
        description="Automatic knowledge extraction from agent session transcripts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- ingest ---
    ingest_p = sub.add_parser("ingest", help="Parse, clean, extract, and write records")
    ingest_p.add_argument("paths", nargs="*", type=Path, help="Transcript file paths")
    ingest_p.add_argument("--source", type=str, default=None, help="Force source type")
    ingest_p.add_argument("--since", type=str, default=None, help="Discover sessions since Nd (e.g. 7d)")
    ingest_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                          help="Path to chronicles directory")

    # --- lint ---
    lint_p = sub.add_parser("lint", help="Validate wiki, manage confidence, regenerate GOLD.md")
    lint_p.add_argument("--chronicles-dir", type=Path, default=Path("chronicles"),
                        help="Path to chronicles directory")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        _run_ingest(args)
    elif args.command == "lint":
        _run_lint(args)


def _run_ingest(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    config = load_config(chronicles_dir)
    renderer = TemplateRenderer()
    extractor = get_extractor(config.llm)

    # Collect session paths
    paths: list[Path] = list(args.paths) if args.paths else []

    if args.since:
        days = int(args.since.rstrip("d"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for source in ALL_SOURCES:
            if source.key in config.sources and source.available():
                paths.extend(source.discover_sessions(since=cutoff))

    if not paths:
        print("No transcript files to process.", file=sys.stderr)
        sys.exit(1)

    # Phase 1: Parse + clean in parallel
    def parse_and_clean(path: Path):
        if args.source:
            source = get_source(args.source)
        else:
            source = detect_source(path)
        transcript = source.parse_session(path)
        cleaned = clean_transcript(transcript)
        return cleaned

    with ProcessPoolExecutor() as pool:
        cleaned_transcripts = list(pool.map(parse_and_clean, paths))

    # Phase 2: Extract in parallel (I/O bound)
    with ThreadPoolExecutor(max_workers=config.llm.max_concurrent) as pool:
        results = list(pool.map(extractor.extract, cleaned_transcripts))

    # Phase 3: Write sequentially
    for cleaned, result in zip(cleaned_transcripts, results):
        date_str = cleaned.metadata.timestamp_start[:10]
        source_key = cleaned.metadata.source

        write_record(chronicles_dir, result, source_key, date_str, renderer)
        append_chronicles_entry(chronicles_dir, result, date_str, renderer)
        write_wiki_pages(chronicles_dir, result, date_str, renderer)

    print(f"Ingested {len(results)} session(s).")

    # Run lint after ingest
    _run_lint_internal(chronicles_dir)


def _run_lint(args: argparse.Namespace) -> None:
    chronicles_dir = args.chronicles_dir.resolve()
    _run_lint_internal(chronicles_dir)


def _run_lint_internal(chronicles_dir: Path) -> None:
    report = lint(chronicles_dir)

    if report.errors:
        print(f"\nErrors ({len(report.errors)}):")
        for e in report.errors:
            print(f"  - {e}")

    if report.warnings:
        print(f"\nWarnings ({len(report.warnings)}):")
        for w in report.warnings:
            print(f"  - {w}")

    if report.promotions:
        print(f"\nPromotions ({len(report.promotions)}):")
        for p in report.promotions:
            print(f"  - {p}")

    print(f"\nGOLD.md: {report.gold_count} high-confidence articles.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test CLI manually**

Run: `python -m chronicles --help`
Expected: shows usage with `ingest` and `lint` subcommands

Run: `python -m chronicles ingest --help`
Expected: shows ingest options

Run: `python -m chronicles lint --help`
Expected: shows lint options

- [ ] **Step 3: Commit**

```bash
git add src/chronicles/cli.py
git commit -m "feat: add CLI entry point with ingest and lint subcommands"
```

---

### Task 14: Integration Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

`tests/test_integration.py`:
```python
"""Integration test — full pipeline from fixture transcript to wiki output."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from chronicles.cli import main


def test_full_ingest_pipeline(chronicles_dir, tmp_path):
    """End-to-end: parse a Claude Code fixture, mock the extractor, verify output."""
    fixtures = Path(__file__).parent / "fixtures"
    transcript_path = fixtures / "claude_code_session.jsonl"

    mock_response = json.dumps({
        "branch": "fix/typo",
        "status": "complete",
        "tags": ["bugfix"],
        "duration": "5min",
        "files_changed": ["src/auth.py"],
        "objective": "Fix typo in auth.py",
        "outcome": "Fixed pasword -> password",
        "decisions": [],
        "problems": [
            {"description": "Typo in variable", "root_cause": "pasword misspelled", "dead_end": False}
        ],
        "discovered": [
            {"type": "trap", "description": "auth.py has typo-prone variable names"}
        ],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [
            {
                "action": "create",
                "path": "wiki/articles/auth-typo-trap.md",
                "data": {
                    "title": "Auth Typo Trap",
                    "type": "trap",
                    "confidence": "low",
                    "tags": ["auth", "typo"],
                    "body": "auth.py has typo-prone variable names.",
                    "evidence": ["Found in fix/typo session"],
                    "implications": ["Review auth.py variable names carefully"],
                },
            }
        ],
    })

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_response)
        main([
            "ingest", str(transcript_path),
            "--chronicles-dir", str(chronicles_dir),
        ])

    # Verify record was written
    records = list((chronicles_dir / "records").glob("*.md"))
    assert len(records) == 1
    assert "fix-typo" in records[0].name

    # Verify CHRONICLES.md was updated
    chronicles_content = (chronicles_dir / "CHRONICLES.md").read_text()
    assert "fix-typo" in chronicles_content
    assert "Fix typo" in chronicles_content

    # Verify wiki article was created
    article = chronicles_dir / "wiki" / "articles" / "auth-typo-trap.md"
    assert article.exists()
    assert "Auth Typo Trap" in article.read_text()

    # Verify GOLD.md (should not contain low-confidence article)
    gold = (chronicles_dir / "GOLD.md").read_text()
    assert "auth-typo-trap" not in gold


def test_lint_standalone(chronicles_dir):
    """Lint command runs without errors on empty chronicles."""
    main(["lint", "--chronicles-dir", str(chronicles_dir)])
    # Should not raise
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: all PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration test for ingest pipeline"
```

---

### Task 15: Hook Configuration Examples

**Files:**
- Create: `docs/hooks/claude-code.md`
- Create: `docs/hooks/copilot-cli.md`

- [ ] **Step 1: Write Claude Code hook config docs**

`docs/hooks/claude-code.md`:
```markdown
# Claude Code Hook Setup

Add to `.claude/settings.json`:

\`\`\`json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "chronicles ingest $TRANSCRIPT_PATH --chronicles-dir ./chronicles"
          }
        ]
      }
    ]
  }
}
\`\`\`
```

- [ ] **Step 2: Write Copilot CLI hook config docs**

`docs/hooks/copilot-cli.md`:
```markdown
# Copilot CLI Hook Setup

Add to `.copilot/config.yml`:

\`\`\`yaml
hooks:
  sessionEnd:
    - command: |
        chronicles ingest \
          --source copilot-cli \
          --since 1d \
          --chronicles-dir ./chronicles
\`\`\`

Note: Copilot CLI does not provide `transcript_path` in hook context.
The `--since 1d` flag triggers session discovery, finding the most recent
transcript by matching timestamps.
```

- [ ] **Step 3: Commit**

```bash
git add docs/hooks/
git commit -m "docs: add hook configuration examples for Claude Code and Copilot CLI"
```

---

### Task 16: Archive Rotation

**Files:**
- Create: `src/chronicles/archiver.py`
- Create: `tests/test_archiver.py`

- [ ] **Step 1: Write failing tests**

`tests/test_archiver.py`:
```python
"""Tests for archive rotation."""
from datetime import date, timedelta
from pathlib import Path

from chronicles.archiver import rotate_records


def _write_record(chronicles_dir: Path, name: str, days_ago: int) -> Path:
    path = chronicles_dir / "records" / f"{name}.md"
    d = date.today() - timedelta(days=days_ago)
    path.write_text(
        f"---\ndate: {d.isoformat()}\nbranch: test\nstatus: complete\n"
        f"tags: [test]\nagent: claude-code\nduration: 5min\n"
        f"files_changed:\n  - src/a.py\n---\n\n# test\n"
    )
    return path


def test_rotates_old_records(chronicles_dir):
    _write_record(chronicles_dir, "2026-01-01_old-record", days_ago=100)
    _write_record(chronicles_dir, "2026-04-01_new-record", days_ago=5)

    rotate_records(chronicles_dir, after_days=90)

    # Old record moved to archives
    assert not (chronicles_dir / "records" / "2026-01-01_old-record.md").exists()
    archives = list((chronicles_dir / "archives").rglob("*.md"))
    assert len(archives) == 1
    assert "old-record" in archives[0].name

    # New record stays
    assert (chronicles_dir / "records" / "2026-04-01_new-record.md").exists()


def test_archive_uses_quarter_dirs(chronicles_dir):
    _write_record(chronicles_dir, "2026-01-15_q1-record", days_ago=100)

    rotate_records(chronicles_dir, after_days=90)

    # Should be in YYYY-QN directory
    archives = list((chronicles_dir / "archives").rglob("*.md"))
    assert len(archives) == 1
    parent = archives[0].parent.name
    assert parent.startswith("2026-") or parent.startswith("2025-")
    assert "Q" in parent


def test_chronicles_md_gets_archived_suffix(chronicles_dir):
    _write_record(chronicles_dir, "2026-01-01_old-record", days_ago=100)

    # Add an entry to CHRONICLES.md
    chron = chronicles_dir / "CHRONICLES.md"
    content = chron.read_text()
    content += "\n## [[2026-01-01_old-record|test]] | ✅ Complete\n> **Objective**: Test\n"
    chron.write_text(content)

    rotate_records(chronicles_dir, after_days=90)

    updated = chron.read_text()
    assert "(archived)" in updated


def test_no_rotation_when_all_fresh(chronicles_dir):
    _write_record(chronicles_dir, "2026-04-01_fresh", days_ago=5)

    rotate_records(chronicles_dir, after_days=90)

    assert (chronicles_dir / "records" / "2026-04-01_fresh.md").exists()
    archives = list((chronicles_dir / "archives").rglob("*.md"))
    assert len(archives) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_archiver.py -v`
Expected: FAIL with import errors

- [ ] **Step 3: Implement archiver**

`src/chronicles/archiver.py`:
```python
"""Archive rotation — moves old records to archives/YYYY-QN/."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path


def rotate_records(chronicles_dir: Path, after_days: int = 90) -> list[Path]:
    """Move records older than after_days to archives/. Returns moved paths."""
    records_dir = chronicles_dir / "records"
    if not records_dir.exists():
        return []

    cutoff = date.today() - timedelta(days=after_days)
    moved: list[Path] = []

    for record in sorted(records_dir.glob("*.md")):
        record_date = _extract_date(record)
        if record_date is None or record_date >= cutoff:
            continue

        # Determine quarter
        quarter = (record_date.month - 1) // 3 + 1
        archive_dir = chronicles_dir / "archives" / f"{record_date.year}-Q{quarter}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        dest = archive_dir / record.name
        record.rename(dest)
        moved.append(dest)

        # Update CHRONICLES.md entry
        _mark_archived(chronicles_dir, record.stem)

    return moved


def _extract_date(record_path: Path) -> date | None:
    """Extract date from record filename (YYYY-MM-DD_slug.md) or frontmatter."""
    # Try filename first
    match = re.match(r"(\d{4}-\d{2}-\d{2})_", record_path.name)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass

    # Fallback to frontmatter
    content = record_path.read_text()
    fm_match = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", content, re.MULTILINE)
    if fm_match:
        try:
            return date.fromisoformat(fm_match.group(1))
        except ValueError:
            pass

    return None


def _mark_archived(chronicles_dir: Path, record_stem: str) -> None:
    """Add (archived) suffix to the CHRONICLES.md entry for this record."""
    chron_path = chronicles_dir / "CHRONICLES.md"
    if not chron_path.exists():
        return

    content = chron_path.read_text()
    # Match the wikilink pattern [[YYYY-MM-DD_slug|...]]
    pattern = re.compile(
        rf"(\[\[{re.escape(record_stem)}[^\]]*\]\][^\n]*)"
    )
    match = pattern.search(content)
    if match and "(archived)" not in match.group(1):
        content = content.replace(
            match.group(1),
            match.group(1) + " (archived)",
        )
        chron_path.write_text(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_archiver.py -v`
Expected: all PASS

- [ ] **Step 5: Wire into lint command**

In `src/chronicles/linter.py`, add archive rotation at the start of `lint()`:

Add import at top:
```python
from chronicles.archiver import rotate_records
```

Add as first step in `lint()`:
```python
    # Archive old records before validation
    moved = rotate_records(chronicles_dir, config.archive.after_days)
    if moved:
        report.warnings.append(f"Archived {len(moved)} old record(s)")
```

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicles/archiver.py tests/test_archiver.py src/chronicles/linter.py
git commit -m "feat: add archive rotation for old records"
```

---

### Task 17: Linter — Duplicate Detection and Merge

**Files:**
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_linter.py`:
```python
def test_lint_detects_and_merges_duplicates(chronicles_dir):
    """Two articles about the same concept (similar titles) get merged."""
    _write_article(chronicles_dir, "connection-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-01_session-a"])
    _write_article(chronicles_dir, "conn-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-05_session-b"])

    report = lint(chronicles_dir)

    # One should be merged into the other
    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 1

    # Merged article has both sources
    content = articles[0].read_text()
    assert "session-a" in content
    assert "session-b" in content


def test_lint_no_merge_for_different_topics(chronicles_dir):
    """Articles with different types/tags should not be merged."""
    _write_article(chronicles_dir, "auth-pattern", confidence="low",
                   article_type="convention", tags=["auth"])
    _write_article(chronicles_dir, "retry-pattern", confidence="low",
                   article_type="pattern", tags=["retry"])

    report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_linter.py::test_lint_detects_and_merges_duplicates -v`
Expected: FAIL

- [ ] **Step 3: Implement duplicate detection**

Add to `src/chronicles/linter.py`:

```python
from difflib import SequenceMatcher


def _detect_and_merge_duplicates(articles: list[dict], report: LintReport) -> list[dict]:
    """Find articles with similar titles and same type, merge them."""
    if len(articles) < 2:
        return articles

    merged_indices: set[int] = set()

    for i, a in enumerate(articles):
        if i in merged_indices:
            continue
        for j in range(i + 1, len(articles)):
            if j in merged_indices:
                continue

            b = articles[j]

            # Same type required
            if a["frontmatter"].get("type") != b["frontmatter"].get("type"):
                continue

            # Similar title check
            ratio = SequenceMatcher(None, a["name"], b["name"]).ratio()
            if ratio < 0.6:
                continue

            # Overlapping tags
            a_tags = set(a["frontmatter"].get("tags", []))
            b_tags = set(b["frontmatter"].get("tags", []))
            if not a_tags & b_tags:
                continue

            # Merge b into a
            report.warnings.append(f"Merged duplicate: {b['name']} into {a['name']}")
            _merge_article(a, b)
            merged_indices.add(j)

            # Delete the merged file
            b["path"].unlink()

    return [a for i, a in enumerate(articles) if i not in merged_indices]


def _merge_article(target: dict, source: dict) -> None:
    """Merge source article into target, combining sources and updating file."""
    target_fm = target["frontmatter"]
    source_fm = source["frontmatter"]

    # Merge sources lists
    existing_sources = target_fm.get("sources", [])
    new_sources = source_fm.get("sources", [])
    all_sources = list(dict.fromkeys(existing_sources + new_sources))  # dedup, preserve order

    # Merge tags
    existing_tags = set(target_fm.get("tags", []))
    new_tags = set(source_fm.get("tags", []))
    all_tags = sorted(existing_tags | new_tags)

    # Update frontmatter in file
    content = target["content"]
    content = re.sub(
        r"sources:\n(  - .+\n)+",
        "sources:\n" + "".join(f'  - "{s}"\n' if "[[" not in s else f"  - {s}\n" for s in all_sources),
        content,
    )
    content = re.sub(
        r"tags: \[.+\]",
        f"tags: {all_tags}",
        content,
    )

    target["path"].write_text(content)
    target["content"] = content
    target["frontmatter"]["sources"] = all_sources
    target["frontmatter"]["tags"] = all_tags
```

Wire `_detect_and_merge_duplicates` into the `lint()` function, after `_load_articles` and before `_manage_confidence`:

```python
    articles = _detect_and_merge_duplicates(articles, report)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linter.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: add duplicate detection and merge to linter"
```

---

### Task 18: Linter — Contested Confidence and Stale Detection

**Files:**
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_linter.py`:
```python
def test_lint_marks_contested(chronicles_dir):
    """High-confidence article contradicted by a later session gets contested."""
    path = chronicles_dir / "wiki" / "articles" / "old-convention.md"
    path.write_text(
        "---\ntype: convention\nconfidence: high\n"
        'sources:\n  - "[[2026-03-01_session-a]]"\n  - "[[2026-03-10_session-b]]"\n'
        "  - \"[[2026-03-20_session-c]]\"\n"
        "first_seen: 2026-03-01\nlast_confirmed: 2026-03-20\n"
        "tags: [test]\n---\n\n# old-convention\n\nUse snake_case.\n"
    )

    # Create a record that contradicts it
    record = chronicles_dir / "records" / "2026-04-05_refactor.md"
    record.write_text(
        "---\ndate: 2026-04-05\nbranch: refactor\nstatus: complete\ntags: [test]\n"
        "agent: claude-code\nduration: 10min\nfiles_changed:\n  - src/a.py\n---\n\n"
        "# refactor\n\n## Discovered\n"
        "- [convention] Use camelCase, not snake_case — contradicts [[old-convention]]\n"
    )

    report = lint(chronicles_dir)
    content = path.read_text()
    assert "confidence: contested" in content
    assert "previous_confidence: high" in content


def test_lint_flags_stale_articles(chronicles_dir):
    """High-confidence article not referenced in any recent record gets flagged."""
    _write_article(chronicles_dir, "stale-article",
                   confidence="high",
                   sources=["2025-01-01_ancient"])  # very old

    # No records reference it
    report = lint(chronicles_dir)
    assert any("stale" in w.lower() for w in report.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_linter.py::test_lint_marks_contested tests/test_linter.py::test_lint_flags_stale_articles -v`
Expected: FAIL

- [ ] **Step 3: Implement contested and stale detection**

Add to `src/chronicles/linter.py`:

```python
def _detect_contested(chronicles_dir: Path, articles: list[dict], report: LintReport) -> None:
    """Check records for contradictions of high-confidence articles."""
    records_dir = chronicles_dir / "records"
    if not records_dir.exists():
        return

    for record_path in records_dir.glob("*.md"):
        content = record_path.read_text()
        # Look for "contradicts [[article-name]]" patterns
        contradicts_re = re.compile(r"contradicts?\s+\[\[([^\]]+)\]\]", re.IGNORECASE)
        for match in contradicts_re.finditer(content):
            target_name = match.group(1).strip()
            for article in articles:
                if article["name"] == target_name and article["frontmatter"].get("confidence") == "high":
                    # Mark as contested
                    art_content = article["content"]
                    art_content = art_content.replace(
                        f"confidence: high",
                        f"confidence: contested\ncontested_by: \"[[{record_path.stem}]]\"\nprevious_confidence: high",
                        1,
                    )
                    article["path"].write_text(art_content)
                    article["content"] = art_content
                    article["frontmatter"]["confidence"] = "contested"
                    report.warnings.append(
                        f"Contested: {article['name']} (by {record_path.stem})"
                    )


def _detect_stale(chronicles_dir: Path, articles: list[dict], report: LintReport) -> None:
    """Flag high-confidence articles not referenced in any record."""
    records_dir = chronicles_dir / "records"
    if not records_dir.exists():
        return

    # Collect all wikilink references across all records
    all_references: set[str] = set()
    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
    for record_path in records_dir.glob("*.md"):
        content = record_path.read_text()
        for match in wikilink_re.finditer(content):
            all_references.add(match.group(1).strip())

    # Also check sources in article frontmatter
    for article in articles:
        if article["frontmatter"].get("confidence") != "high":
            continue

        sources = article["frontmatter"].get("sources", [])
        # Check if any source record still exists in records/
        has_recent = False
        for source in sources:
            # Extract record stem from "[[YYYY-MM-DD_slug]]"
            source_match = re.search(r"\[\[([^\]]+)\]\]", str(source))
            if source_match:
                stem = source_match.group(1)
                if (records_dir / f"{stem}.md").exists():
                    has_recent = True
                    break

        if not has_recent and article["name"] not in all_references:
            report.warnings.append(
                f"Stale high-confidence article: {article['name']} "
                f"(no active records reference it)"
            )
```

Wire both into `lint()`, after `_manage_confidence` and before `_regenerate_gold`:

```python
    _detect_contested(chronicles_dir, articles, report)
    _detect_stale(chronicles_dir, articles, report)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_linter.py -v`
Expected: all PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: add contested confidence detection and stale article flagging"
```
