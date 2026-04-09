# Phase 1: Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the infrastructure layer for Chronicles' knowledge lifecycle evolution — pluggable similarity engine, relationship types in wiki frontmatter, and config extensions for decay/gaps.

**Architecture:** Three new config dataclasses (`SimilarityConfig`, `DecayConfig`, `GapsConfig`) with defaults so existing configs keep working. A new `similarity/` package with an ABC and an LLM-backed default engine that reuses the existing subprocess CLI pattern. Relationship types stored as optional frontmatter on wiki articles. The extractor prompt extended to emit relationships. The linter gains `_infer_relationships()` to add implicit relationships.

**Tech Stack:** Python 3.11+, PyYAML, Jinja2, subprocess (for LLM calls)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/chronicles/similarity/__init__.py` | `get_similarity_engine()` factory |
| Create | `src/chronicles/similarity/base.py` | `BaseSimilarityEngine` ABC |
| Create | `src/chronicles/similarity/llm.py` | `LLMSimilarityEngine` — subprocess LLM backend |
| Modify | `src/chronicles/config.py` | Add `SimilarityConfig`, `DecayConfig`, `GapsConfig` dataclasses; wire into `ChroniclesConfig` and `load_config()` |
| Modify | `src/chronicles/templates/wiki_article.md.j2` | Add optional `relationships` block in frontmatter |
| Modify | `src/chronicles/writer.py` | Pass `relationships` from wiki_instructions into template context |
| Modify | `src/chronicles/extractors/copilot_cli.py` | Extend prompt schema with optional `relationships` field |
| Modify | `src/chronicles/linter.py` | Add `_infer_relationships()` step; integrate into `lint()` |
| Create | `tests/test_similarity/__init__.py` | Test package |
| Create | `tests/test_similarity/test_base.py` | Tests for ABC contract |
| Create | `tests/test_similarity/test_llm.py` | Tests for LLMSimilarityEngine (mocked subprocess) |
| Modify | `tests/test_config.py` | Tests for new config sections |
| Modify | `tests/test_templates.py` | Test wiki_article rendering with relationships |
| Modify | `tests/test_writer.py` | Test relationships passed through to template |
| Modify | `tests/test_linter.py` | Test `_infer_relationships()` |
| Modify | `tests/test_extractors/test_copilot_cli.py` | Test prompt includes relationship schema |

---

### Task 1: Config Extensions

**Files:**
- Modify: `src/chronicles/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config dataclasses**

Add to `tests/test_config.py`:

```python
def test_load_config_new_sections_defaults(tmp_path):
    """New config sections use defaults when absent."""
    config = load_config(tmp_path)
    assert config.similarity.engine == "llm"
    assert config.similarity.threshold == 0.7
    assert config.decay.high_to_medium_days == 180
    assert config.decay.medium_to_low_days == 270
    assert config.decay.archive_after_days == 365
    assert config.gaps.enabled is True
    assert config.gaps.git_lookback_days == 90


def test_load_config_new_sections_override(tmp_path):
    """New config sections can be overridden."""
    (tmp_path / "config.yaml").write_text(
        "similarity:\n"
        "  engine: tfidf\n"
        "  threshold: 0.8\n"
        "decay:\n"
        "  high_to_medium_days: 90\n"
        "gaps:\n"
        "  enabled: false\n"
    )
    config = load_config(tmp_path)
    assert config.similarity.engine == "tfidf"
    assert config.similarity.threshold == 0.8
    assert config.decay.high_to_medium_days == 90
    assert config.decay.medium_to_low_days == 270  # default
    assert config.gaps.enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'ChroniclesConfig' object has no attribute 'similarity'`

- [ ] **Step 3: Add dataclasses and wire into load_config**

In `src/chronicles/config.py`, add these dataclasses after `EnrichConfig`:

```python
@dataclass
class SimilarityConfig:
    engine: str = "llm"
    threshold: float = 0.7


@dataclass
class DecayConfig:
    high_to_medium_days: int = 180
    medium_to_low_days: int = 270
    archive_after_days: int = 365


@dataclass
class GapsConfig:
    enabled: bool = True
    git_lookback_days: int = 90
```

Add the three new fields to `ChroniclesConfig`:

```python
@dataclass
class ChroniclesConfig:
    llm: LLMConfig
    sources: list[str]
    confidence: ConfidenceConfig
    archive: ArchiveConfig
    enrich: EnrichConfig
    similarity: SimilarityConfig
    decay: DecayConfig
    gaps: GapsConfig
    chronicles_dir: Path
```

Add parsing to `load_config()`, before the `return` statement:

```python
    sim_raw = raw.get("similarity", {})
    similarity = SimilarityConfig(
        engine=sim_raw.get("engine", "llm"),
        threshold=sim_raw.get("threshold", 0.7),
    )

    decay_raw = raw.get("decay", {})
    decay = DecayConfig(
        high_to_medium_days=decay_raw.get("high_to_medium_days", 180),
        medium_to_low_days=decay_raw.get("medium_to_low_days", 270),
        archive_after_days=decay_raw.get("archive_after_days", 365),
    )

    gaps_raw = raw.get("gaps", {})
    gaps = GapsConfig(
        enabled=gaps_raw.get("enabled", True),
        git_lookback_days=gaps_raw.get("git_lookback_days", 90),
    )

    return ChroniclesConfig(
        llm=llm,
        sources=sources,
        confidence=confidence,
        archive=archive,
        enrich=enrich,
        similarity=similarity,
        decay=decay,
        gaps=gaps,
        chronicles_dir=chronicles_dir,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run full suite to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: All 71+ tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/config.py tests/test_config.py
git commit -m "feat: add SimilarityConfig, DecayConfig, GapsConfig to config"
```

---

### Task 2: Similarity Engine — Base + LLM Implementation

**Files:**
- Create: `src/chronicles/similarity/__init__.py`
- Create: `src/chronicles/similarity/base.py`
- Create: `src/chronicles/similarity/llm.py`
- Create: `tests/test_similarity/__init__.py`
- Create: `tests/test_similarity/test_base.py`
- Create: `tests/test_similarity/test_llm.py`

- [ ] **Step 1: Write failing test for the ABC contract**

Create `tests/test_similarity/__init__.py` (empty file).

Create `tests/test_similarity/test_base.py`:

```python
"""Tests for similarity engine base class."""
import pytest
from chronicles.similarity.base import BaseSimilarityEngine


def test_cannot_instantiate_base():
    """ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseSimilarityEngine(config=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_similarity/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chronicles.similarity'`

- [ ] **Step 3: Implement BaseSimilarityEngine**

Create `src/chronicles/similarity/__init__.py`:

```python
"""Similarity engine package."""
from __future__ import annotations

from chronicles.config import SimilarityConfig
from chronicles.similarity.base import BaseSimilarityEngine


def get_similarity_engine(config: SimilarityConfig, llm_config=None) -> BaseSimilarityEngine:
    """Factory: return the configured similarity engine."""
    if config.engine == "llm":
        from chronicles.similarity.llm import LLMSimilarityEngine
        if llm_config is None:
            raise ValueError("LLM similarity engine requires llm_config")
        return LLMSimilarityEngine(config, llm_config)
    raise ValueError(f"Unknown similarity engine: {config.engine}")
```

Create `src/chronicles/similarity/base.py`:

```python
"""Base similarity engine ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod

from chronicles.config import SimilarityConfig


class BaseSimilarityEngine(ABC):
    """Abstract base for all similarity engines."""

    def __init__(self, config: SimilarityConfig) -> None:
        self.config = config

    @abstractmethod
    def score(self, text_a: str, text_b: str) -> float:
        """Return 0.0-1.0 similarity score between two texts."""

    @abstractmethod
    def batch_score(
        self, items: list[str], threshold: float
    ) -> list[tuple[int, int, float]]:
        """Return (i, j, score) tuples for all pairs above threshold."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_similarity/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for LLMSimilarityEngine**

Create `tests/test_similarity/test_llm.py`:

```python
"""Tests for LLM-backed similarity engine."""
from unittest.mock import patch, MagicMock

from chronicles.config import SimilarityConfig, LLMConfig
from chronicles.similarity.llm import LLMSimilarityEngine


def _make_engine():
    sim_config = SimilarityConfig(engine="llm", threshold=0.7)
    llm_config = LLMConfig(provider="claude-code", model="claude-haiku-4-5")
    return LLMSimilarityEngine(sim_config, llm_config)


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_parses_llm_response(mock_run):
    """LLM returns a number 0-10, engine normalizes to 0.0-1.0."""
    mock_run.return_value = MagicMock(returncode=0, stdout="7\n", stderr="")
    engine = _make_engine()
    result = engine.score("OAuth token refresh", "Token refresh mechanism")
    assert result == 0.7
    mock_run.assert_called_once()


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_clamps_to_range(mock_run):
    """Values outside 0-10 are clamped."""
    mock_run.return_value = MagicMock(returncode=0, stdout="12\n", stderr="")
    engine = _make_engine()
    assert engine.score("a", "b") == 1.0

    mock_run.return_value = MagicMock(returncode=0, stdout="-3\n", stderr="")
    assert engine.score("a", "b") == 0.0


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_returns_zero_on_llm_failure(mock_run):
    """LLM failure returns 0.0 instead of raising."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
    engine = _make_engine()
    assert engine.score("a", "b") == 0.0


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_returns_zero_on_non_numeric(mock_run):
    """Non-numeric LLM output returns 0.0."""
    mock_run.return_value = MagicMock(returncode=0, stdout="these are similar\n", stderr="")
    engine = _make_engine()
    assert engine.score("a", "b") == 0.0


@patch("chronicles.similarity.llm.subprocess.run")
def test_batch_score_filters_by_threshold(mock_run):
    """batch_score returns only pairs above threshold."""
    # 3 items = 3 pairs: (0,1), (0,2), (1,2)
    # Return scores: 8, 3, 9 -> normalized: 0.8, 0.3, 0.9
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="8\n", stderr=""),
        MagicMock(returncode=0, stdout="3\n", stderr=""),
        MagicMock(returncode=0, stdout="9\n", stderr=""),
    ]
    engine = _make_engine()
    results = engine.batch_score(["A", "B", "C"], threshold=0.7)
    assert len(results) == 2
    assert (0, 1, 0.8) in results
    assert (1, 2, 0.9) in results


@patch("chronicles.similarity.llm.subprocess.run")
def test_batch_score_empty_list(mock_run):
    """Empty input returns empty results."""
    engine = _make_engine()
    assert engine.batch_score([], threshold=0.5) == []


@patch("chronicles.similarity.llm.subprocess.run")
def test_batch_score_single_item(mock_run):
    """Single item has no pairs to compare."""
    engine = _make_engine()
    assert engine.batch_score(["A"], threshold=0.5) == []


def test_factory_returns_llm_engine():
    """get_similarity_engine returns LLMSimilarityEngine for 'llm'."""
    from chronicles.similarity import get_similarity_engine
    sim_config = SimilarityConfig(engine="llm", threshold=0.7)
    llm_config = LLMConfig(provider="claude-code", model="claude-haiku-4-5")
    engine = get_similarity_engine(sim_config, llm_config=llm_config)
    assert isinstance(engine, LLMSimilarityEngine)


def test_factory_raises_on_unknown():
    """get_similarity_engine raises for unknown engine type."""
    from chronicles.similarity import get_similarity_engine
    import pytest
    sim_config = SimilarityConfig(engine="unknown", threshold=0.7)
    with pytest.raises(ValueError, match="Unknown similarity engine"):
        get_similarity_engine(sim_config)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_similarity/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chronicles.similarity.llm'`

- [ ] **Step 7: Implement LLMSimilarityEngine**

Create `src/chronicles/similarity/llm.py`:

```python
"""LLM-backed similarity engine."""
from __future__ import annotations

import logging
import re
import subprocess

from chronicles.config import LLMConfig, SimilarityConfig
from chronicles.similarity.base import BaseSimilarityEngine

log = logging.getLogger("chronicles")

_SIMILARITY_PROMPT = (
    "Rate the semantic similarity of these two texts on a scale of 0 to 10, "
    "where 0 means completely unrelated and 10 means identical in meaning. "
    "Return ONLY the number, nothing else.\n\n"
    "Text A: {text_a}\n\n"
    "Text B: {text_b}"
)


class LLMSimilarityEngine(BaseSimilarityEngine):
    """Similarity scoring via configured LLM CLI backend."""

    def __init__(self, config: SimilarityConfig, llm_config: LLMConfig) -> None:
        super().__init__(config)
        self.llm_config = llm_config

    def score(self, text_a: str, text_b: str) -> float:
        prompt = _SIMILARITY_PROMPT.format(text_a=text_a, text_b=text_b)
        raw = self._call_llm(prompt)
        return self._parse_score(raw)

    def batch_score(
        self, items: list[str], threshold: float
    ) -> list[tuple[int, int, float]]:
        results: list[tuple[int, int, float]] = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                s = self.score(items[i], items[j])
                if s >= threshold:
                    results.append((i, j, s))
        return results

    def _call_llm(self, prompt: str) -> str:
        provider = self.llm_config.provider
        model = self.llm_config.model

        if provider == "copilot-cli":
            cmd = ["copilot", "-p", prompt, "--model", model]
        elif provider == "claude-code":
            cmd = ["claude", "--print", "--model", model, prompt]
        else:
            log.warning("Unknown LLM provider for similarity: %s", provider)
            return ""

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=60
            )
            if result.returncode != 0:
                log.warning("Similarity LLM call failed: %s", result.stderr[:200])
                return ""
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            log.warning("Similarity LLM call timed out")
            return ""

    @staticmethod
    def _parse_score(raw: str) -> float:
        if not raw:
            return 0.0
        match = re.search(r"(\d+(?:\.\d+)?)", raw)
        if not match:
            return 0.0
        value = float(match.group(1)) / 10.0
        return max(0.0, min(1.0, value))
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_similarity/ -v`
Expected: All 10 tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicles/similarity/ tests/test_similarity/
git commit -m "feat: add pluggable similarity engine with LLM backend"
```

---

### Task 3: Relationship Types in Template + Writer

**Files:**
- Modify: `src/chronicles/templates/wiki_article.md.j2`
- Modify: `src/chronicles/writer.py`
- Modify: `tests/test_templates.py`
- Modify: `tests/test_writer.py`

- [ ] **Step 1: Write failing test for template rendering with relationships**

Add to `tests/test_templates.py`:

```python
def test_render_wiki_article_with_relationships():
    renderer = TemplateRenderer()
    data = {
        "type": "convention",
        "confidence": "medium",
        "sources": ["2026-04-09_feat-oauth"],
        "first_seen": "2026-04-09",
        "last_confirmed": "2026-04-09",
        "tags": ["naming"],
        "title": "New Convention",
        "body": "This replaces the old convention.",
        "evidence": ["Found in session"],
        "implications": ["Follow new pattern"],
        "relationships": [
            {"type": "supersedes", "target": "old-convention", "source": "[[2026-04-09_feat-oauth]]"},
            {"type": "depends-on", "target": "base-pattern"},
        ],
    }
    result = renderer.render("wiki_article", data)
    assert "relationships:" in result
    assert "type: supersedes" in result
    assert "target: old-convention" in result
    assert "type: depends-on" in result
    assert "target: base-pattern" in result
    # source only present on first relationship
    assert "source: [[2026-04-09_feat-oauth]]" in result


def test_render_wiki_article_without_relationships():
    """Relationships block is omitted when empty."""
    renderer = TemplateRenderer()
    data = {
        "type": "convention",
        "confidence": "low",
        "sources": ["2026-04-09_test"],
        "first_seen": "2026-04-09",
        "last_confirmed": "2026-04-09",
        "tags": ["test"],
        "title": "No Relationships",
        "body": "Simple article.",
        "evidence": ["evidence"],
        "implications": ["implication"],
        "relationships": [],
    }
    result = renderer.render("wiki_article", data)
    assert "relationships:" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_templates.py::test_render_wiki_article_with_relationships tests/test_templates.py::test_render_wiki_article_without_relationships -v`
Expected: FAIL — template doesn't have relationships block yet

- [ ] **Step 3: Update wiki_article.md.j2 template**

Replace the contents of `src/chronicles/templates/wiki_article.md.j2` with:

```jinja2
---
type: {{ type }}
confidence: {{ confidence }}
sources:
{% for s in sources %}  - "[[{{ s }}]]"
{% endfor %}first_seen: {{ first_seen }}
last_confirmed: {{ last_confirmed }}
tags: {{ tags }}
{% if relationships %}relationships:
{% for r in relationships %}  - type: {{ r.type }}
    target: {{ r.target }}
{% if r.source %}    source: {{ r.source }}
{% endif %}{% endfor %}{% endif %}---

# {{ title }}

{{ body }}

## Evidence
{% for e in evidence %}- {{ e }}
{% endfor %}
## Implications
{% for i in implications %}- {{ i }}
{% endfor %}
```

- [ ] **Step 4: Run template tests to verify they pass**

Run: `uv run pytest tests/test_templates.py -v`
Expected: All template tests PASS (including existing ones — the `relationships` block is optional)

- [ ] **Step 5: Write failing test for writer passing relationships**

Add to `tests/test_writer.py`:

```python
def test_write_wiki_pages_with_relationships(chronicles_dir):
    """Relationships from wiki_instructions are passed to template."""
    from chronicles.models import ExtractionResult
    from chronicles.templates import TemplateRenderer
    from chronicles.writer import write_wiki_pages

    renderer = TemplateRenderer()
    result = ExtractionResult(
        branch="feat/test",
        status="complete",
        tags=["test"],
        duration="10min",
        files_changed=[],
        objective="Test",
        outcome="Tested",
        decisions=[],
        problems=[],
        discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[{
            "action": "create",
            "path": "wiki/articles/new-pattern.md",
            "data": {
                "title": "New Pattern",
                "type": "pattern",
                "confidence": "medium",
                "tags": ["test"],
                "body": "A new pattern.",
                "evidence": ["evidence"],
                "implications": ["implication"],
            },
            "relationships": [
                {"type": "supersedes", "target": "old-pattern"},
            ],
        }],
    )
    count = write_wiki_pages(chronicles_dir, result, "2026-04-09", renderer)
    assert count == 1
    content = (chronicles_dir / "wiki" / "articles" / "new-pattern.md").read_text()
    assert "relationships:" in content
    assert "type: supersedes" in content
    assert "target: old-pattern" in content
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_writer.py::test_write_wiki_pages_with_relationships -v`
Expected: FAIL — `relationships` not in rendered output

- [ ] **Step 7: Update writer to pass relationships to template**

In `src/chronicles/writer.py`, update `_build_wiki_context()` to include relationships:

```python
def _build_wiki_context(data: dict, date: str, relationships: list | None = None) -> dict:
    """Build a complete context dict for a wiki template, filling in defaults."""
    return {
        "title": data.get("title", ""),
        "type": data.get("type", "article"),
        "confidence": data.get("confidence", "low"),
        "tags": data.get("tags", []),
        "body": data.get("body", ""),
        "evidence": data.get("evidence", []),
        "implications": data.get("implications", []),
        "sources": data.get("sources", []),
        "first_seen": data.get("first_seen", date),
        "last_confirmed": data.get("last_confirmed", date),
        # category fields
        "articles": data.get("articles", []),
        "open_questions": data.get("open_questions", []),
        # query fields
        "asked_by": data.get("asked_by", ""),
        "date": data.get("date", date),
        "answered_from": data.get("answered_from", []),
        "question": data.get("question", data.get("title", "")),
        "answer": data.get("answer", data.get("body", "")),
        # relationship fields
        "relationships": relationships or [],
    }
```

In `write_wiki_pages()`, extract relationships from the instruction and pass to `_build_wiki_context()`:

```python
        # Extract relationships from instruction (not from data)
        relationships = instruction.get("relationships", [])

        # Build template context with defaults for required fields
        context = _build_wiki_context(data, date, relationships=relationships)
```

- [ ] **Step 8: Run all writer and template tests**

Run: `uv run pytest tests/test_writer.py tests/test_templates.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicles/templates/wiki_article.md.j2 src/chronicles/writer.py tests/test_templates.py tests/test_writer.py
git commit -m "feat: add relationship types to wiki article template and writer"
```

---

### Task 4: Extractor Prompt Extension

**Files:**
- Modify: `src/chronicles/extractors/copilot_cli.py`
- Modify: `tests/test_extractors/test_copilot_cli.py`

- [ ] **Step 1: Write failing test for relationships in prompt**

Add to `tests/test_extractors/test_copilot_cli.py`:

```python
def test_prompt_includes_relationship_schema():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    transcript = _make_cleaned_transcript()
    prompt = extractor._build_prompt(transcript)
    assert '"relationships"' in prompt
    assert "supersedes" in prompt
    assert "contradicts" in prompt
    assert "depends-on" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extractors/test_copilot_cli.py::test_prompt_includes_relationship_schema -v`
Expected: FAIL — `"relationships"` not in prompt

- [ ] **Step 3: Extend the system prompt**

In `src/chronicles/extractors/copilot_cli.py`, update `_SYSTEM_PROMPT`. Add `"relationships"` as an optional field inside the `wiki_instructions` schema (after `"data"`):

```python
      "relationships": [
        {
          "type": "contradicts | supersedes | depends-on | generalizes | related-to",
          "target": "existing-article-slug"
        }
      ]
```

Add these rules to the RULES section at the end of the prompt:

```
- If a new article supersedes, contradicts, or depends on an EXISTING article, add a "relationships" array to the wiki_instruction
- Valid relationship types: contradicts, supersedes, depends-on, generalizes, related-to
- "target" must be the slug (filename without .md) of an existing article listed above
- Only add relationships when the connection is clear from the session evidence
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_extractors/ -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/extractors/copilot_cli.py tests/test_extractors/test_copilot_cli.py
git commit -m "feat: extend extractor prompt with relationship types"
```

---

### Task 5: Linter — _infer_relationships()

**Files:**
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing test for relationship inference from contested articles**

Add to `tests/test_linter.py`:

```python
def test_lint_infers_contradicts_relationship(chronicles_dir):
    """When an article is contested, a contradicts relationship is added."""
    articles_dir = chronicles_dir / "wiki" / "articles"

    (articles_dir / "refresh-strategy.md").write_text(
        "---\ntype: decision\nconfidence: high\nsources:\n"
        '  - "[[2026-04-01_initial]]"\ntags: [auth]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Refresh Strategy\n\nRefresh before expiry.\n"
    )

    records_dir = chronicles_dir / "records"
    (records_dir / "2026-04-15_refactor-auth.md").write_text(
        "---\ndate: 2026-04-15\n---\n\n# Refactor Auth\n\n"
        "This contradicts [[refresh-strategy]].\n"
    )

    report = lint(chronicles_dir)

    content = (articles_dir / "refresh-strategy.md").read_text()
    assert "confidence: contested" in content
    assert "relationships:" in content
    assert "type: contradicts" in content
    assert "target: 2026-04-15_refactor-auth" in content
```

- [ ] **Step 2: Write failing test for related-to relationships from tag overlap**

Add to `tests/test_linter.py`:

```python
def test_lint_infers_related_to_from_tags(chronicles_dir):
    """Articles with overlapping tags get related-to relationships."""
    articles_dir = chronicles_dir / "wiki" / "articles"

    (articles_dir / "article-a.md").write_text(
        "---\ntype: convention\nconfidence: medium\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\ntags: [auth, oauth]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Article A\n\nContent A.\n"
    )
    (articles_dir / "article-b.md").write_text(
        "---\ntype: convention\nconfidence: medium\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\ntags: [auth, tokens]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Article B\n\nContent B.\n"
    )

    lint(chronicles_dir)

    content_a = (articles_dir / "article-a.md").read_text()
    assert "relationships:" in content_a
    assert "type: related-to" in content_a
    assert "target: article-b" in content_a
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_linter.py::test_lint_infers_contradicts_relationship tests/test_linter.py::test_lint_infers_related_to_from_tags -v`
Expected: FAIL

- [ ] **Step 4: Implement _infer_relationships()**

Add to `src/chronicles/linter.py`:

```python
VALID_RELATIONSHIP_TYPES = frozenset({
    "contradicts", "supersedes", "depends-on", "generalizes", "related-to",
})


def _parse_relationships(text: str) -> list[dict]:
    """Extract relationships list from article frontmatter text."""
    fm = _parse_frontmatter(text)
    if fm is None:
        return []
    return fm.get("relationships", []) or []


def _write_relationships(article: dict, relationships: list[dict]) -> None:
    """Write or update the relationships block in an article's frontmatter."""
    text = article["text"]
    path: Path = article["path"]

    # Remove existing relationships block if present
    text = re.sub(
        r"relationships:\n(?:  - .+\n(?:    .+\n)*)*",
        "",
        text,
    )

    if not relationships:
        path.write_text(text)
        article["text"] = text
        return

    # Build relationships YAML block
    rel_lines = ["relationships:\n"]
    for r in relationships:
        rel_lines.append(f"  - type: {r['type']}\n")
        rel_lines.append(f"    target: {r['target']}\n")
        if r.get("source"):
            rel_lines.append(f"    source: {r['source']}\n")
    rel_block = "".join(rel_lines)

    # Insert before closing ---
    text = re.sub(r"\n---\n", f"\n{rel_block}---\n", text, count=1)

    path.write_text(text)
    article["text"] = text
    article["frontmatter"]["relationships"] = relationships


def _infer_relationships(
    chronicles_dir: Path,
    articles: list[dict],
    report: LintReport,
) -> None:
    """Infer and write relationships between articles.

    - contradicts: from contested detection results
    - related-to: from tag overlap (replaces ## Related sections)
    """
    # Build tag -> article mapping for related-to inference
    article_tags: dict[str, set[str]] = {}
    for article in articles:
        fm = article["frontmatter"]
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        article_tags[article["path"].stem] = set(tags)

    for article in articles:
        name = article["path"].stem
        existing_rels = _parse_relationships(article["text"])
        new_rels = list(existing_rels)
        existing_targets = {(r["type"], r.get("target")) for r in existing_rels}

        # Add contradicts from contested status
        fm = article["frontmatter"]
        if fm.get("confidence") == "contested":
            contested_by = fm.get("contested_by", "")
            match = re.search(r"\[\[([^\]]+)\]\]", str(contested_by))
            if match:
                target = match.group(1)
                if ("contradicts", target) not in existing_targets:
                    new_rels.append({"type": "contradicts", "target": target})

        # Add related-to from tag overlap
        my_tags = article_tags.get(name, set())
        if my_tags:
            for other_name, other_tags in article_tags.items():
                if other_name == name:
                    continue
                shared = my_tags & other_tags
                if shared and ("related-to", other_name) not in existing_targets:
                    new_rels.append({"type": "related-to", "target": other_name})

        if new_rels != existing_rels:
            _write_relationships(article, new_rels)
```

- [ ] **Step 5: Wire _infer_relationships() into lint()**

In `src/chronicles/linter.py`, in the `lint()` function, add the call after `_detect_contested()`:

```python
    _detect_contested(chronicles_dir, articles, report)
    _infer_relationships(chronicles_dir, articles, report)
    _detect_stale(chronicles_dir, articles, report)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_linter.py::test_lint_infers_contradicts_relationship tests/test_linter.py::test_lint_infers_related_to_from_tags -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. The existing `_add_related_sections()` still runs — it will coexist with relationships for now (Phase 2 will migrate it fully). The `generalizes` relationship type is deferred to Phase 2 since it requires the similarity engine integration with the linter, which happens alongside semantic dedup.

- [ ] **Step 8: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: add _infer_relationships() to linter (contradicts + related-to)"
```

---

### Task 6: Integration Test + Final Verification

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Read the current integration test**

Read `tests/test_integration.py` to understand the pattern.

- [ ] **Step 2: Write integration test for relationships end-to-end**

Add to `tests/test_integration.py`:

```python
def test_ingest_with_relationships(chronicles_dir):
    """Full pipeline: extractor returns relationships, writer persists them, linter infers more."""
    from unittest.mock import patch, MagicMock
    import json
    from pathlib import Path
    from chronicles.cli import _run_ingest
    from chronicles.templates import TemplateRenderer

    # Create a pre-existing article for the relationship target
    articles_dir = chronicles_dir / "wiki" / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)
    (articles_dir / "old-pattern.md").write_text(
        "---\ntype: pattern\nconfidence: medium\nsources:\n"
        '  - "[[2026-03-01_initial]]"\n  - "[[2026-03-15_confirm]]"\n'
        "tags: [auth]\nfirst_seen: 2026-03-01\nlast_confirmed: 2026-03-15\n---\n\n"
        "# Old Pattern\n\nThe old way.\n\n## Evidence\n- evidence\n\n## Implications\n- implication\n"
    )

    # Write a fixture transcript
    fixture = chronicles_dir.parent / "session.jsonl"
    fixture.write_text(
        '{"type":"human","timestamp":"2026-04-09T10:00:00Z","message":{"content":"update the pattern"}}\n'
        '{"type":"assistant","timestamp":"2026-04-09T10:01:00Z","message":{"content":[{"type":"text","text":"Done."}]}}\n'
    )

    extractor_response = json.dumps({
        "branch": "feat/new-pattern",
        "status": "complete",
        "tags": ["auth"],
        "duration": "10min",
        "files_changed": ["src/auth.py"],
        "objective": "Update pattern",
        "outcome": "Pattern updated",
        "decisions": [],
        "problems": [],
        "discovered": [],
        "continuity": {"unfinished": [], "open_questions": [], "next": []},
        "wiki_instructions": [{
            "action": "create",
            "path": "wiki/articles/new-pattern.md",
            "data": {
                "title": "New Pattern",
                "type": "pattern",
                "confidence": "medium",
                "tags": ["auth"],
                "body": "The new way of doing things.",
                "evidence": ["From this session"],
                "implications": ["Use new pattern"],
            },
            "relationships": [
                {"type": "supersedes", "target": "old-pattern"}
            ],
        }],
    })

    with patch("chronicles.extractors.copilot_cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=extractor_response, stderr=""
        )

        args = MagicMock()
        args.paths = [fixture]
        args.source = "claude-code"
        args.since = None
        args.chronicles_dir = chronicles_dir
        args.no_enrich = True

        _run_ingest(args)

    # Verify the new article was written with relationships
    new_article = articles_dir / "new-pattern.md"
    assert new_article.exists()
    content = new_article.read_text()
    assert "relationships:" in content
    assert "type: supersedes" in content
    assert "target: old-pattern" in content

    # Verify related-to was inferred (both share "auth" tag)
    assert "type: related-to" in content
    assert "target: old-pattern" in content or "target: old-pattern" in content
```

- [ ] **Step 3: Run integration test**

Run: `uv run pytest tests/test_integration.py::test_ingest_with_relationships -v`
Expected: PASS

- [ ] **Step 4: Run the full test suite one final time**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for relationships end-to-end"
```
