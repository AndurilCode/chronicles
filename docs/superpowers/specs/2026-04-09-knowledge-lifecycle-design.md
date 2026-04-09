# Knowledge Lifecycle Evolution — Design Spec

> Evolve Chronicles from a write-once wiki into an active knowledge system with confidence calibration, semantic deduplication, typed relationships, decay/pruning, conflict resolution workflows, and knowledge gap detection.

## Approach

Three-phase layered implementation. Each phase builds on the previous and is independently shippable.

- **Phase 1 — Infrastructure**: Pluggable similarity engine, relationship types in frontmatter, config extensions
- **Phase 2 — Lifecycle upgrades**: Semantic dedup, confidence calibration, decay/pruning, conflict resolution workflows
- **Phase 3 — Intelligence**: Knowledge gap analysis (git churn + session-based), GAPS.md generation

---

## Phase 1: Infrastructure

### 1.1 Pluggable Similarity Engine

New `src/chronicles/similarity/` package:

```
similarity/
  __init__.py          # get_similarity_engine() factory
  base.py              # BaseSimilarityEngine ABC
  llm.py               # LLMSimilarityEngine (default)
```

**`BaseSimilarityEngine` interface:**

```python
class BaseSimilarityEngine(ABC):
    def __init__(self, config: SimilarityConfig): ...

    @abstractmethod
    def score(self, text_a: str, text_b: str) -> float:
        """Return 0.0-1.0 similarity score between two texts."""

    @abstractmethod
    def batch_score(self, items: list[str], threshold: float) -> list[tuple[int, int, float]]:
        """Return (i, j, score) tuples for all pairs scoring above threshold."""
```

**`LLMSimilarityEngine`**: Sends pairs to the configured LLM backend with a prompt: "Rate the semantic similarity of these two texts on a scale of 0-10. Return only the number." Normalizes to 0.0-1.0. Batches comparisons to minimize API calls.

**Config:**

```yaml
similarity:
  engine: llm           # llm | (future: embeddings, tfidf)
  threshold: 0.7        # minimum similarity to consider a match
```

**`SimilarityConfig` dataclass** added to `config.py`:

```python
@dataclass
class SimilarityConfig:
    engine: str = "llm"
    threshold: float = 0.7
```

### 1.2 Relationship Types

New optional frontmatter field on wiki articles:

```yaml
relationships:
  - type: supersedes
    target: old-article-slug
    source: "[[2026-04-09_record]]"
  - type: depends-on
    target: other-article-slug
```

**Valid relationship types:**

| Type | Meaning | Populated by |
|------|---------|-------------|
| `contradicts` | This article disagrees with the target | Extractor + linter |
| `supersedes` | This article replaces the target | Extractor + linter (on merge) |
| `depends-on` | This article assumes the target is true | Extractor |
| `generalizes` | This article is a broader version of the target | Linter (via similarity + tag subset) |
| `related-to` | Topically related, no directional meaning | Linter (replaces current `## Related`) |

**Extractor prompt extension**: `wiki_instructions` gains an optional `relationships` field:

```json
{
  "action": "create",
  "path": "wiki/articles/new-article.md",
  "data": { "..." : "..." },
  "relationships": [
    {"type": "supersedes", "target": "old-article-slug"}
  ]
}
```

**Writer changes**: `write_wiki_pages()` writes relationships into frontmatter. The `wiki_article.md.j2` template gains a `relationships` block.

**Linter changes**: New `_infer_relationships()` step that:
- Converts existing `## Related` sections into `related-to` relationships in frontmatter
- Uses similarity engine to find `generalizes` candidates (high similarity + tag superset)
- Integrates with existing `_detect_contested()` to create `contradicts` relationships

### 1.3 Config Extensions

New sections added to `config.yaml` schema:

```yaml
similarity:
  engine: llm
  threshold: 0.7

decay:
  high_to_medium_days: 180
  medium_to_low_days: 270
  archive_after_days: 365

gaps:
  enabled: true
  git_lookback_days: 90
```

**New dataclasses** in `config.py`:

```python
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

These are added to `ChroniclesConfig` with defaults so existing `config.yaml` files continue to work.

### 1.4 Template Changes

`wiki_article.md.j2` gains optional blocks for relationships and resolution history:

```jinja2
{% if relationships %}
relationships:
{% for r in relationships %}  - type: {{ r.type }}
    target: {{ r.target }}
{% if r.source %}    source: {{ r.source }}
{% endif %}{% endfor %}{% endif %}
```

---

## Phase 2: Lifecycle Upgrades

### 2.1 Semantic Dedup

Replaces `SequenceMatcher` in `_detect_and_merge_duplicates()`.

**New flow:**
1. For each article, build comparison text: title + first paragraph of body
2. Call `similarity_engine.batch_score(texts, threshold)` to get candidate pairs
3. Filter: same `type` required (unchanged constraint)
4. Merge as today — the surviving article gains a `supersedes` relationship pointing to the merged article's slug

**Fallback**: If the similarity engine is unavailable (e.g., no LLM configured), fall back to the current `SequenceMatcher` approach. Log a warning.

### 2.2 Confidence Calibration

New `_calibrate_confidence()` step in the linter, runs after `_manage_confidence()`.

**New frontmatter field**: `promoted_on: YYYY-MM-DD` — set when an article is promoted to `high`.

**Calibration logic:**
- If an article promoted to `high` is contested within 3 sessions of its promotion, emit a warning: "Article {slug} contested shortly after promotion — type '{type}' may need higher promotion_threshold"
- Articles that survive contestation (contested then resolved in their favor) get `calibration: validated` in frontmatter — these have been stress-tested
- The linter report includes a calibration summary: promotion count, contestation rate, validation rate

**No automatic threshold changes.** Calibration is observational — it surfaces data for humans to tune `confidence.promotion_threshold`.

### 2.3 Decay and Pruning

New `_apply_decay()` step in the linter, runs before `_manage_confidence()` (so demotions happen before promotions in the same lint pass).

**Last confirmation date** is computed as the most recent of:
- `last_confirmed` frontmatter field
- Most recent record date among records that contain a wikilink to this article

**Demotion rules:**

| Current | Condition | New | Safety check |
|---------|-----------|-----|-------------|
| `high` | No confirmation for `high_to_medium_days` | `medium` | None — reversible |
| `medium` | No confirmation for `medium_to_low_days` | `low` | Zero inbound wikilinks from non-archived records |
| `low` | No confirmation for `archive_after_days` | archived | Zero inbound wikilinks from any article |

**Archive behavior:**
- Archived articles move to `wiki/archived/` directory (created if absent)
- `archived_reason: decay` and `archived_on: YYYY-MM-DD` added to frontmatter
- Articles with `relationships` pointing to them as `depends-on` targets are never auto-archived — the linter warns instead

**Reporting**: Demotions and archives are logged in `LintReport.warnings`.

### 2.4 Conflict Resolution Workflows

Extends `_detect_contested()` into a full workflow.

**Surfacing — `CONTESTED.md`:**

New file generated by the linter (like GOLD.md), listing all contested articles:

```markdown
---
type: contested-index
last_updated: 2026-04-09
contested_count: 2
---

# Contested Knowledge

> These articles have conflicting evidence. Sessions working in related areas should note which side they observe.

## [[refresh-strategy]]
- **Original claim**: Refresh tokens before expiry
- **Contested by**: [[2026-04-15_refactor-auth]] — claims refresh-on-401 is better
- **Evidence for original**: 2 sessions | **Evidence against**: 1 session
```

Template: `contested.md.j2`

**Extractor integration:**
- When wiki context includes contested articles, the prompt instructs the LLM: "The following articles are CONTESTED — if this session provides evidence for either side, include a wiki_instruction with action: 'resolve' and the article path"
- New `action: "resolve"` in wiki_instructions:

```json
{
  "action": "resolve",
  "path": "wiki/articles/refresh-strategy.md",
  "data": {
    "supports": "original",
    "evidence": "Session confirmed refresh-before-expiry prevents cascading failures"
  }
}
```

**Writer changes**: `write_wiki_pages()` handles `action: "resolve"` by appending evidence to a tracking structure in frontmatter:

```yaml
resolution_evidence:
  - record: "[[2026-04-18_perf-review]]"
    supports: original
  - record: "[[2026-04-20_auth-fix]]"
    supports: original
```

**Auto-resolution in linter:**
- New `_resolve_contested()` step, runs after `_detect_contested()`
- If 2+ sessions after contestation support one side, resolve:
  - Winning side: restore `confidence: high`, clear contested fields
  - Append `## Resolution History` section to the article body:

```markdown
## Resolution History
- **2026-04-15**: Contested by [[2026-04-15_refactor-auth]] — claimed refresh-on-401 is better
- **2026-04-20**: Resolved in favor of original ([[2026-04-18_perf-review]], [[2026-04-20_auth-fix]]) — refresh-before-expiry prevents cascading failures
```

- Losing side: if a separate article was created, add `supersedes` relationship from winner to loser and demote loser to `low`

**CONTESTED.md regeneration**: Like GOLD.md, fully regenerated each lint pass from all articles with `confidence: contested`.

---

## Phase 3: Intelligence

### 3.1 Knowledge Gap Analysis

New `src/chronicles/gaps.py` module.

**Git churn analysis:**
1. Run `git log --numstat --since={git_lookback_days}d` via subprocess
2. Aggregate change counts by directory (2 levels deep: `src/auth/`, not individual files)
3. Cross-reference against all records' `files_changed` fields and wiki articles that reference those paths in their body or evidence
4. Score: `churn_count / wiki_coverage_count` — high ratio = gap

**Session analysis:**
1. Scan all non-archived records for `problems` and `discovered` entries
2. Group by tags and `files_changed` directories
3. Identify patterns:
   - Directories where agents repeatedly hit problems but no `trap` or `workaround` article exists
   - Dead ends that recur across 2+ sessions without documentation
   - Tags that appear in records but have no corresponding wiki articles

**Combined scoring:**
Each directory/topic gets a gap score combining:
- Git churn weight (normalized 0-1)
- Problem recurrence weight (normalized 0-1)
- Inverse wiki coverage (0 = fully covered, 1 = zero articles)

Top gaps by score are reported.

**Output — `GAPS.md`:**

```markdown
---
type: gaps-report
last_updated: 2026-04-09
gap_count: 5
---

# Knowledge Gaps

> Areas of the codebase with high activity but low wiki coverage.

## High-Churn, Low-Coverage
- `src/auth/` — 47 changes in 90 days, 0 wiki articles reference files here
- `src/api/middleware/` — 31 changes, 1 article (stale)

## Recurring Problems Without Documentation
- Rate limiting retry logic — 3 sessions hit issues, no trap/workaround article exists
- Config file parsing edge cases — 2 dead ends, no article

## Agent Blind Spots
- `tests/integration/` — 12 sessions touched this, 0 knowledge extracted
```

Template: `gaps.md.j2`

**Linter integration:**
- `_analyze_gaps()` runs as the final linter step
- Only runs if `gaps.enabled` is true and either git is available or records exist
- Falls back gracefully: if `git` is not available, skips churn analysis and does session-only analysis
- Gap count added to `LintReport`

**Graceful degradation:**
- No git repo: session analysis only
- No records: git churn only
- Neither: skip entirely, log info message

---

## New Files Summary

```
src/chronicles/
  similarity/
    __init__.py
    base.py
    llm.py
  gaps.py

templates/  (inside src/chronicles/templates/)
  contested.md.j2
  gaps.md.j2
```

## Modified Files Summary

| File | Changes |
|------|---------|
| `config.py` | Add `SimilarityConfig`, `DecayConfig`, `GapsConfig` dataclasses |
| `models.py` | No changes needed — relationships live in frontmatter, not ExtractionResult |
| `extractors/copilot_cli.py` | Extend prompt with relationship instructions and contested article context |
| `writer.py` | Handle `relationships` in wiki_instructions, handle `action: "resolve"` |
| `linter.py` | Add `_infer_relationships()`, `_calibrate_confidence()`, `_apply_decay()`, `_resolve_contested()`, `_analyze_gaps()`, CONTESTED.md generation |
| `cli.py` | Wire similarity engine into linter calls |
| `templates/wiki_article.md.j2` | Add relationships and resolution_history blocks |

## Testing Strategy

Each phase adds tests for its new functionality:

- **Phase 1**: Similarity engine unit tests (mock LLM responses), relationship parsing/writing tests, config loading tests for new fields
- **Phase 2**: Semantic dedup tests (mock similarity engine), decay tests with various date scenarios, conflict resolution workflow tests (contest → evidence → resolve lifecycle), calibration tests
- **Phase 3**: Gap analysis tests with mock git output and fixture records, GAPS.md rendering tests

Integration tests: full ingest → lint cycle exercising the new lifecycle (contest an article, add evidence across sessions, verify resolution).

## Linter Step Ordering (Phase 2+)

After all phases are implemented, the linter runs steps in this order:

1. `rotate_records()` — archive old records
2. `_load_articles()` — load and validate
3. `_detect_and_merge_duplicates()` — semantic dedup (Phase 2)
4. `_check_wikilinks()` — link integrity
5. `_infer_relationships()` — add implicit relationships (Phase 1)
6. `_apply_decay()` — demote/archive stale articles (Phase 2)
7. `_manage_confidence()` — promote articles by source count
8. `_calibrate_confidence()` — track promotion quality (Phase 2)
9. `_detect_contested()` — flag contradictions
10. `_resolve_contested()` — auto-resolve with evidence (Phase 2)
11. `_detect_stale()` — flag stale high-confidence articles
12. `_regenerate_categories()` — rebuild category pages
13. `_add_related_sections()` — update related links (migrates to relationships in Phase 1)
14. `_regenerate_gold()` — rebuild GOLD.md
15. `_regenerate_contested()` — rebuild CONTESTED.md (Phase 2)
16. `_analyze_gaps()` — generate GAPS.md (Phase 3)

## Dependencies

No new external dependencies. The LLM similarity engine reuses the existing subprocess-based LLM backend. Future similarity engines (embeddings, TF-IDF) would add optional dependencies.
