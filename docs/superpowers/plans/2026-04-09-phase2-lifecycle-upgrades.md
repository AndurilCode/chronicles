# Phase 2: Lifecycle Upgrades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace string-matching dedup with semantic similarity, add confidence calibration, implement time-based decay/pruning, and build conflict resolution workflows with evidence trails and CONTESTED.md.

**Architecture:** Four new linter steps (`_semantic_dedup()`, `_calibrate_confidence()`, `_apply_decay()`, `_resolve_contested()`) plus a CONTESTED.md template and writer support for `action: "resolve"`. The linter gains access to the similarity engine via config. The existing `_detect_and_merge_duplicates()` is replaced. New step ordering follows the spec.

**Tech Stack:** Python 3.11+, PyYAML, Jinja2, existing similarity engine from Phase 1

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/chronicles/linter.py` | Replace `_detect_and_merge_duplicates` with semantic dedup; add `_calibrate_confidence`, `_apply_decay`, `_resolve_contested`, `_regenerate_contested`; reorder `lint()` steps |
| Modify | `src/chronicles/writer.py` | Handle `action: "resolve"` in `write_wiki_pages()` |
| Create | `src/chronicles/templates/contested.md.j2` | CONTESTED.md template |
| Modify | `src/chronicles/extractors/copilot_cli.py` | Extend prompt for contested article awareness |
| Modify | `src/chronicles/cli.py` | Pass config to `lint()` for similarity engine access |
| Modify | `tests/test_linter.py` | Tests for all new linter steps |
| Modify | `tests/test_writer.py` | Test for `action: "resolve"` |
| Modify | `tests/test_templates.py` | Test for contested template |
| Modify | `tests/test_integration.py` | End-to-end lifecycle test |

---

### Task 1: Semantic Dedup

**Files:**
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing tests for semantic dedup**

Add to `tests/test_linter.py`:

```python
def test_semantic_dedup_merges_similar_articles(chronicles_dir):
    """Semantic dedup merges articles with similar content, adds supersedes relationship."""
    from unittest.mock import patch, MagicMock

    _write_article(chronicles_dir, "token-refresh-pattern",
                   confidence="low", article_type="pattern", tags=["auth", "tokens"],
                   sources=["2026-04-01_session-a"])
    _write_article(chronicles_dir, "oauth-token-refresh",
                   confidence="low", article_type="pattern", tags=["auth", "oauth"],
                   sources=["2026-04-05_session-b"])

    mock_engine = MagicMock()
    # Return high similarity between the two articles
    mock_engine.batch_score.return_value = [(0, 1, 0.85)]

    with patch("chronicles.linter._get_similarity_engine", return_value=mock_engine):
        report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 1
    content = articles[0].read_text()
    assert "session-a" in content
    assert "session-b" in content
    # Surviving article gains supersedes relationship
    assert "type: supersedes" in content


def test_semantic_dedup_fallback_without_engine(chronicles_dir):
    """When similarity engine is unavailable, falls back to SequenceMatcher."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "connection-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-01_session-a"])
    _write_article(chronicles_dir, "conn-suffix-pattern",
                   confidence="low", tags=["naming"],
                   sources=["2026-04-05_session-b"])

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 1


def test_semantic_dedup_respects_type_filter(chronicles_dir):
    """Articles with different types are never merged, even if semantically similar."""
    from unittest.mock import patch, MagicMock

    _write_article(chronicles_dir, "retry-convention",
                   confidence="low", article_type="convention", tags=["retry"],
                   sources=["2026-04-01_s1"])
    _write_article(chronicles_dir, "retry-pattern",
                   confidence="low", article_type="pattern", tags=["retry"],
                   sources=["2026-04-05_s2"])

    mock_engine = MagicMock()
    mock_engine.batch_score.return_value = [(0, 1, 0.95)]

    with patch("chronicles.linter._get_similarity_engine", return_value=mock_engine):
        report = lint(chronicles_dir)

    articles = list((chronicles_dir / "wiki" / "articles").glob("*.md"))
    assert len(articles) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_linter.py::test_semantic_dedup_merges_similar_articles tests/test_linter.py::test_semantic_dedup_fallback_without_engine tests/test_linter.py::test_semantic_dedup_respects_type_filter -v`
Expected: FAIL — `_get_similarity_engine` not found

- [ ] **Step 3: Implement semantic dedup**

In `src/chronicles/linter.py`:

1. Add import at top:
```python
from chronicles.similarity import get_similarity_engine
from chronicles.similarity.base import BaseSimilarityEngine
```

2. Add helper function to get similarity engine (returns None on failure):
```python
def _get_similarity_engine(config) -> BaseSimilarityEngine | None:
    """Try to create a similarity engine from config. Returns None on failure."""
    try:
        return get_similarity_engine(config.similarity, llm_config=config.llm)
    except (ValueError, Exception) as e:
        log.warning("Similarity engine unavailable, using fallback: %s", e)
        return None
```

3. Replace `_detect_and_merge_duplicates` with a new function that uses the similarity engine when available, falls back to SequenceMatcher otherwise:

```python
def _detect_and_merge_duplicates(
    articles: list[dict],
    report: LintReport,
    similarity_engine: BaseSimilarityEngine | None = None,
) -> list[dict]:
    """Detect and merge duplicate articles using semantic similarity or string fallback."""
    if len(articles) < 2:
        return articles

    if similarity_engine is not None:
        return _semantic_dedup(articles, report, similarity_engine)
    return _fallback_dedup(articles, report)


def _semantic_dedup(
    articles: list[dict],
    report: LintReport,
    engine: BaseSimilarityEngine,
) -> list[dict]:
    """Use similarity engine to find and merge duplicate articles."""
    # Build comparison texts: title + first paragraph
    texts: list[str] = []
    for a in articles:
        title = a["path"].stem.replace("-", " ")
        body_match = re.match(r"^---\n.*?\n---\n\s*#[^\n]*\n\n(.+?)(\n\n|\n#|$)", a["text"], re.DOTALL)
        body = body_match.group(1).strip() if body_match else ""
        texts.append(f"{title}: {body}")

    # Get similarity pairs above threshold
    pairs = engine.batch_score(texts, engine.config.threshold)

    merged_indices: set[int] = set()
    for i, j, score in sorted(pairs, key=lambda p: -p[2]):
        if i in merged_indices or j in merged_indices:
            continue
        a, b = articles[i], articles[j]
        # Same type required
        if a["frontmatter"].get("type") != b["frontmatter"].get("type"):
            continue
        report.warnings.append(
            f"Merged duplicate: {b['path'].stem} into {a['path'].stem} (similarity: {score:.2f})"
        )
        _merge_article(a, b)
        # Add supersedes relationship on surviving article
        existing_rels = _parse_relationships(a["text"])
        existing_rels.append({"type": "supersedes", "target": b["path"].stem})
        _write_relationships(a, existing_rels)
        merged_indices.add(j)
        b["path"].unlink()

    return [a for i, a in enumerate(articles) if i not in merged_indices]


def _fallback_dedup(articles: list[dict], report: LintReport) -> list[dict]:
    """Fallback dedup using SequenceMatcher when similarity engine is unavailable."""
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
            if a["frontmatter"].get("type") != b["frontmatter"].get("type"):
                continue
            ratio = SequenceMatcher(None, a["path"].stem, b["path"].stem).ratio()
            if ratio < 0.6:
                continue
            a_tags = set(a["frontmatter"].get("tags", []))
            b_tags = set(b["frontmatter"].get("tags", []))
            shared_tags = a_tags & b_tags
            all_tags = a_tags | b_tags
            if not shared_tags or (len(shared_tags) / len(all_tags) < 0.5):
                continue
            report.warnings.append(f"Merged duplicate: {b['path'].stem} into {a['path'].stem}")
            _merge_article(a, b)
            merged_indices.add(j)
            b["path"].unlink()
    return [a for i, a in enumerate(articles) if i not in merged_indices]
```

4. Update `lint()` to get the similarity engine and pass it:

In the `lint()` function, after `config = load_config(chronicles_dir)` and before `articles_dir`, add:
```python
    similarity_engine = _get_similarity_engine(config)
```

Change the dedup call from:
```python
    articles = _detect_and_merge_duplicates(articles, report)
```
to:
```python
    articles = _detect_and_merge_duplicates(articles, report, similarity_engine)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_linter.py -v`
Expected: All linter tests PASS

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: replace string-based dedup with semantic similarity engine"
```

---

### Task 2: Decay and Pruning

**Files:**
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing tests for decay**

Add to `tests/test_linter.py`:

```python
def test_decay_demotes_high_to_medium(chronicles_dir):
    """High-confidence article with old last_confirmed gets demoted to medium."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "old-high", confidence="high",
                   sources=["2025-01-01_ancient", "2025-02-01_old", "2025-03-01_also-old"])
    # Override last_confirmed to be very old
    path = chronicles_dir / "wiki" / "articles" / "old-high.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2025-06-01")
    path.write_text(text)

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = path.read_text()
    assert "confidence: medium" in content
    assert any("old-high" in w and "high -> medium" in w for w in report.warnings)


def test_decay_medium_to_low_requires_no_inbound_links(chronicles_dir):
    """Medium article is NOT demoted to low if other articles link to it."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "referenced-medium", confidence="medium",
                   sources=["2025-01-01_ancient", "2025-02-01_old"])
    path = chronicles_dir / "wiki" / "articles" / "referenced-medium.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2025-01-01")
    path.write_text(text)

    # Create another article that links to it via wikilink in body
    linker = chronicles_dir / "wiki" / "articles" / "linker.md"
    linker.write_text(
        "---\ntype: convention\nconfidence: low\nsources:\n"
        '  - "[[2026-04-01_recent]]"\ntags: [other]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Linker\n\nSee [[referenced-medium]] for details.\n"
    )

    # Create the record so linker doesn't trigger "empty sources" errors
    (chronicles_dir / "records" / "2026-04-01_recent.md").write_text(
        "---\ndate: 2026-04-01\n---\n# Recent\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = path.read_text()
    assert "confidence: medium" in content  # NOT demoted


def test_decay_archives_old_low_article(chronicles_dir):
    """Low-confidence article with no links gets archived after archive_after_days."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "ancient-low", confidence="low",
                   sources=["2024-01-01_very-old"])
    path = chronicles_dir / "wiki" / "articles" / "ancient-low.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2024-01-01")
    path.write_text(text)

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    # Article moved to archived dir
    assert not path.exists()
    archived = chronicles_dir / "wiki" / "archived" / "ancient-low.md"
    assert archived.exists()
    content = archived.read_text()
    assert "archived_reason: decay" in content


def test_decay_skips_depends_on_targets(chronicles_dir):
    """Articles that are depends-on targets of other articles are never archived."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "depended-upon", confidence="low",
                   sources=["2024-01-01_very-old"])
    path = chronicles_dir / "wiki" / "articles" / "depended-upon.md"
    text = path.read_text().replace("last_confirmed: 2026-04-09", "last_confirmed: 2024-01-01")
    path.write_text(text)

    # Create an article that depends on it (via relationships in frontmatter)
    depender = chronicles_dir / "wiki" / "articles" / "depender.md"
    depender.write_text(
        "---\ntype: convention\nconfidence: medium\nsources:\n"
        '  - "[[2026-04-01_recent]]"\n  - "[[2026-04-02_recent2]]"\ntags: [other]\n'
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n"
        "relationships:\n  - type: depends-on\n    target: depended-upon\n---\n\n"
        "# Depender\n\nDepends on depended-upon.\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    assert path.exists()  # NOT archived
    assert any("depended-upon" in w and "depends-on" in w for w in report.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_linter.py::test_decay_demotes_high_to_medium tests/test_linter.py::test_decay_archives_old_low_article tests/test_linter.py::test_decay_skips_depends_on_targets -v`
Expected: FAIL

- [ ] **Step 3: Implement `_apply_decay()`**

Add to `src/chronicles/linter.py`:

```python
def _compute_last_confirmation(article: dict, chronicles_dir: Path) -> str:
    """Compute the most recent confirmation date for an article.

    Returns ISO date string. Checks last_confirmed frontmatter and record wikilinks.
    """
    fm = article["frontmatter"]
    last_confirmed = fm.get("last_confirmed", "")

    # Also check records for wikilinks to this article
    records_dir = chronicles_dir / "records"
    article_name = article["path"].stem
    if records_dir.exists():
        wikilink_re = re.compile(r"\[\[" + re.escape(article_name) + r"(?:\|[^\]]+)?\]\]")
        for record_path in sorted(records_dir.glob("*.md"), reverse=True):
            content = record_path.read_text()
            if wikilink_re.search(content):
                # Extract date from record filename (YYYY-MM-DD_slug.md)
                record_date = record_path.stem[:10]
                if record_date > last_confirmed:
                    last_confirmed = record_date
                break  # sorted reverse, first match is most recent

    return last_confirmed


def _has_inbound_wikilinks(article_name: str, articles: list[dict], chronicles_dir: Path) -> bool:
    """Check if any non-archived article or record contains a wikilink to this article."""
    wikilink_re = re.compile(r"\[\[" + re.escape(article_name) + r"(?:\|[^\]]+)?\]\]")

    # Check other articles' bodies
    for other in articles:
        if other["path"].stem == article_name:
            continue
        body_match = re.match(r"^---\n.*?\n---\n(.*)", other["text"], re.DOTALL)
        body = body_match.group(1) if body_match else ""
        if wikilink_re.search(body):
            return True

    # Check non-archived records
    records_dir = chronicles_dir / "records"
    if records_dir.exists():
        for record_path in records_dir.glob("*.md"):
            if wikilink_re.search(record_path.read_text()):
                return True

    return False


def _is_depends_on_target(article_name: str, articles: list[dict]) -> bool:
    """Check if any article has a depends-on relationship targeting this article."""
    for other in articles:
        if other["path"].stem == article_name:
            continue
        rels = other["frontmatter"].get("relationships", []) or []
        for r in rels:
            if r.get("type") == "depends-on" and r.get("target") == article_name:
                return True
    return False


def _apply_decay(
    chronicles_dir: Path,
    articles: list[dict],
    config,
    report: LintReport,
) -> list[dict]:
    """Demote or archive stale articles based on time since last confirmation.

    Returns the (possibly reduced) article list after archival.
    """
    today = _today()
    decay = config.decay
    archived_indices: set[int] = set()

    for i, article in enumerate(articles):
        fm = article["frontmatter"]
        confidence = fm.get("confidence", "low")
        if confidence in ("contested",):
            continue  # Don't decay contested articles

        last_confirmed = _compute_last_confirmation(article, chronicles_dir)
        if not last_confirmed:
            continue

        # Compute days since last confirmation
        try:
            from datetime import date as date_cls
            last_date = date_cls.fromisoformat(last_confirmed)
            today_date = date_cls.fromisoformat(today)
            days_stale = (today_date - last_date).days
        except (ValueError, TypeError):
            continue

        name = article["path"].stem
        path: Path = article["path"]

        if confidence == "high" and days_stale >= decay.high_to_medium_days:
            # Demote high -> medium
            old_text = article["text"]
            new_text = re.sub(r"^confidence: high", "confidence: medium", old_text, count=1, flags=re.MULTILINE)
            path.write_text(new_text)
            article["text"] = new_text
            article["frontmatter"] = {**fm, "confidence": "medium"}
            report.warnings.append(f"Decay: {name} high -> medium ({days_stale}d since confirmation)")

        elif confidence == "medium" and days_stale >= decay.medium_to_low_days:
            # Demote medium -> low only if no inbound wikilinks
            if not _has_inbound_wikilinks(name, articles, chronicles_dir):
                old_text = article["text"]
                new_text = re.sub(r"^confidence: medium", "confidence: low", old_text, count=1, flags=re.MULTILINE)
                path.write_text(new_text)
                article["text"] = new_text
                article["frontmatter"] = {**fm, "confidence": "low"}
                report.warnings.append(f"Decay: {name} medium -> low ({days_stale}d since confirmation)")

        elif confidence == "low" and days_stale >= decay.archive_after_days:
            # Archive only if no inbound wikilinks AND not a depends-on target
            if _is_depends_on_target(name, articles):
                report.warnings.append(
                    f"Decay: {name} would be archived but is a depends-on target — skipping"
                )
                continue
            if _has_inbound_wikilinks(name, articles, chronicles_dir):
                continue

            # Move to wiki/archived/
            archived_dir = chronicles_dir / "wiki" / "archived"
            archived_dir.mkdir(parents=True, exist_ok=True)
            archived_path = archived_dir / path.name

            # Add archived metadata to frontmatter
            old_text = article["text"]
            new_text = re.sub(
                r"\n---\n",
                f"\narchived_reason: decay\narchived_on: {today}\n---\n",
                old_text,
                count=1,
            )
            archived_path.write_text(new_text)
            path.unlink()
            archived_indices.add(i)
            report.warnings.append(f"Archived: {name} (decay, {days_stale}d since confirmation)")

    return [a for i, a in enumerate(articles) if i not in archived_indices]
```

- [ ] **Step 4: Wire `_apply_decay()` into `lint()`**

In the `lint()` function, add the decay call BEFORE `_manage_confidence()`. Find:
```python
    promotions = _manage_confidence(articles, config.confidence.promotion_threshold)
```
Add before it:
```python
    articles = _apply_decay(chronicles_dir, articles, config, report)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_linter.py -v`
Expected: All PASS

- [ ] **Step 6: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: add decay and pruning with automatic demotion and archival"
```

---

### Task 3: Confidence Calibration

**Files:**
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing tests for calibration**

Add to `tests/test_linter.py`:

```python
def test_calibration_sets_promoted_on(chronicles_dir):
    """When an article is promoted to high, promoted_on is set."""
    from unittest.mock import patch

    _write_article(chronicles_dir, "promoted-article",
                   confidence="medium",
                   sources=["s1", "s2", "s3"])

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = (chronicles_dir / "wiki" / "articles" / "promoted-article.md").read_text()
    assert "confidence: high" in content
    assert "promoted_on:" in content


def test_calibration_warns_on_quick_contestation(chronicles_dir):
    """Warn when a recently promoted article gets contested."""
    from unittest.mock import patch

    path = chronicles_dir / "wiki" / "articles" / "fragile-convention.md"
    path.write_text(
        "---\ntype: convention\nconfidence: high\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\n  - "[[2026-04-03_s3]]"\n'
        "tags: [test]\nfirst_seen: 2026-04-01\nlast_confirmed: 2026-04-03\n"
        "promoted_on: 2026-04-03\n---\n\n# Fragile Convention\n\nContent.\n"
    )

    record = chronicles_dir / "records" / "2026-04-05_challenge.md"
    record.write_text(
        "---\ndate: 2026-04-05\n---\n\n# Challenge\n\n"
        "This contradicts [[fragile-convention]].\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    assert any("fragile-convention" in w and "contested shortly after promotion" in w
               for w in report.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_linter.py::test_calibration_sets_promoted_on tests/test_linter.py::test_calibration_warns_on_quick_contestation -v`
Expected: FAIL

- [ ] **Step 3: Implement `_calibrate_confidence()`**

Add to `src/chronicles/linter.py`:

```python
def _calibrate_confidence(
    articles: list[dict],
    report: LintReport,
) -> None:
    """Track confidence calibration — set promoted_on on new promotions, warn on quick contestation."""
    today = _today()

    for article in articles:
        fm = article["frontmatter"]
        path: Path = article["path"]

        # If just promoted to high (by _manage_confidence), set promoted_on
        if fm.get("confidence") == "high" and not fm.get("promoted_on"):
            old_text = article["text"]
            new_text = re.sub(
                r"\n---\n",
                f"\npromoted_on: {today}\n---\n",
                old_text,
                count=1,
            )
            path.write_text(new_text)
            article["text"] = new_text
            article["frontmatter"]["promoted_on"] = today

        # If contested and has promoted_on, check if contestation was quick
        if fm.get("confidence") == "contested" and fm.get("promoted_on"):
            promoted_on = fm["promoted_on"]
            report.warnings.append(
                f"Calibration: {path.stem} contested shortly after promotion "
                f"(promoted {promoted_on}) — type '{fm.get('type')}' may need higher promotion_threshold"
            )

        # If contested was resolved (confidence restored to high), mark as validated
        if fm.get("confidence") == "high" and fm.get("previous_confidence") == "high":
            if not fm.get("calibration"):
                old_text = article["text"]
                new_text = re.sub(
                    r"\n---\n",
                    "\ncalibration: validated\n---\n",
                    old_text,
                    count=1,
                )
                path.write_text(new_text)
                article["text"] = new_text
                article["frontmatter"]["calibration"] = "validated"
```

- [ ] **Step 4: Wire into `lint()` — add after `_manage_confidence()`**

After:
```python
    promotions = _manage_confidence(articles, config.confidence.promotion_threshold)
```
Add:
```python
    _calibrate_confidence(articles, report)
```

Also update `_manage_confidence()` to set `promoted_on` directly when promoting to high. In the function, after the `new_confidence = "high"` branch, track that this is a new promotion by also setting the `promoted_on` on the frontmatter dict so `_calibrate_confidence` can see it:

Actually, `_calibrate_confidence` checks for `promoted_on` not being set — so it will detect freshly promoted articles and add it. No change to `_manage_confidence` needed.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_linter.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicles/linter.py tests/test_linter.py
git commit -m "feat: add confidence calibration tracking"
```

---

### Task 4: CONTESTED.md Template

**Files:**
- Create: `src/chronicles/templates/contested.md.j2`
- Modify: `tests/test_templates.py`

- [ ] **Step 1: Write failing test for contested template**

Add to `tests/test_templates.py`:

```python
def test_render_contested():
    renderer = TemplateRenderer()
    data = {
        "date": "2026-04-09",
        "count": 1,
        "articles": [
            {
                "title": "refresh-strategy",
                "original_claim": "Refresh tokens before expiry",
                "contested_by": "2026-04-15_refactor-auth",
                "contested_reason": "claims refresh-on-401 is better",
                "evidence_for": 2,
                "evidence_against": 1,
            },
        ],
    }
    result = renderer.render("contested", data)
    assert "contested_count: 1" in result
    assert "[[refresh-strategy]]" in result
    assert "Refresh tokens before expiry" in result
    assert "[[2026-04-15_refactor-auth]]" in result
    assert "2 sessions" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_templates.py::test_render_contested -v`
Expected: FAIL — template not found

- [ ] **Step 3: Create contested template**

Create `src/chronicles/templates/contested.md.j2`:

```jinja2
---
type: contested-index
last_updated: {{ date }}
contested_count: {{ count }}
---

# Contested Knowledge

> These articles have conflicting evidence. Sessions working in related areas should note which side they observe.

{% for a in articles %}## [[{{ a.title }}]]
- **Original claim**: {{ a.original_claim }}
- **Contested by**: [[{{ a.contested_by }}]] — {{ a.contested_reason }}
- **Evidence for original**: {{ a.evidence_for }} sessions | **Evidence against**: {{ a.evidence_against }} sessions

{% endfor %}
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_templates.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/templates/contested.md.j2 tests/test_templates.py
git commit -m "feat: add CONTESTED.md template"
```

---

### Task 5: Conflict Resolution — Writer + Linter

**Files:**
- Modify: `src/chronicles/writer.py`
- Modify: `src/chronicles/linter.py`
- Modify: `tests/test_writer.py`
- Modify: `tests/test_linter.py`

- [ ] **Step 1: Write failing test for action: "resolve" in writer**

Add to `tests/test_writer.py`:

```python
def test_write_wiki_pages_resolve_action(chronicles_dir):
    """action: 'resolve' appends resolution_evidence to article frontmatter."""
    from chronicles.writer import write_wiki_pages

    # Pre-create a contested article
    article_path = chronicles_dir / "wiki" / "articles" / "refresh-strategy.md"
    article_path.write_text(
        "---\ntype: decision\nconfidence: contested\nsources:\n"
        '  - "[[2026-04-01_initial]]"\n'
        'contested_by: "[[2026-04-15_refactor-auth]]"\n'
        "previous_confidence: high\ntags: [auth]\n"
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Refresh Strategy\n\nRefresh before expiry.\n"
    )

    renderer = TemplateRenderer()
    result = ExtractionResult(
        branch="feat/perf-review",
        status="complete",
        tags=["auth"],
        duration="10min",
        files_changed=[],
        objective="Review",
        outcome="Reviewed",
        decisions=[],
        problems=[],
        discovered=[],
        continuity={"unfinished": [], "open_questions": [], "next": []},
        wiki_instructions=[{
            "action": "resolve",
            "path": "wiki/articles/refresh-strategy.md",
            "data": {
                "supports": "original",
                "evidence": "Session confirmed refresh-before-expiry prevents cascading failures",
            },
        }],
    )
    count = write_wiki_pages(chronicles_dir, result, "2026-04-09", renderer)
    assert count == 1
    content = article_path.read_text()
    assert "resolution_evidence:" in content
    assert "supports: original" in content
    assert "2026-04-09_feat-perf-review" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_writer.py::test_write_wiki_pages_resolve_action -v`
Expected: FAIL

- [ ] **Step 3: Implement action: "resolve" in writer**

In `src/chronicles/writer.py`, update `write_wiki_pages()`. After the `if action in ("create", "update"):` block, add:

```python
        elif action == "resolve":
            # Append resolution evidence to existing article's frontmatter
            if not out_path.exists():
                log.warning("Cannot resolve %s — article does not exist", rel_path)
                continue
            existing = out_path.read_text()
            record_ref_link = f'"[[{record_ref}]]"'
            supports = data.get("supports", "original")
            evidence_text = data.get("evidence", "")

            # Append to or create resolution_evidence block
            evidence_entry = (
                f"  - record: {record_ref_link}\n"
                f"    supports: {supports}\n"
            )
            if evidence_text:
                evidence_entry += f"    evidence: {evidence_text}\n"

            if "resolution_evidence:" in existing:
                # Append to existing block (before closing ---)
                existing = existing.replace(
                    "resolution_evidence:\n",
                    "resolution_evidence:\n" + evidence_entry,
                    1,
                )
            else:
                # Insert new block before closing ---
                existing = re.sub(
                    r"\n---\n",
                    f"\nresolution_evidence:\n{evidence_entry}---\n",
                    existing,
                    count=1,
                )
            out_path.write_text(existing)
            log.info("  wiki: %s (resolve evidence, supports=%s)", rel_path, supports)
            count += 1
```

Add `import re` at the top of writer.py if not already present (it is).

- [ ] **Step 4: Write failing tests for `_resolve_contested()` and `_regenerate_contested()` in linter**

Add to `tests/test_linter.py`:

```python
def test_resolve_contested_with_evidence(chronicles_dir):
    """Contested article is resolved when 2+ sessions support one side."""
    from unittest.mock import patch

    articles_dir = chronicles_dir / "wiki" / "articles"
    path = articles_dir / "refresh-strategy.md"
    path.write_text(
        "---\ntype: decision\nconfidence: contested\nsources:\n"
        '  - "[[2026-04-01_initial]]"\n  - "[[2026-04-05_confirm]]"\n  - "[[2026-04-10_confirm2]]"\n'
        'contested_by: "[[2026-04-15_refactor-auth]]"\n'
        "previous_confidence: high\ntags: [auth]\n"
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-10\n"
        "resolution_evidence:\n"
        '  - record: "[[2026-04-18_perf-review]]"\n'
        "    supports: original\n"
        '  - record: "[[2026-04-20_auth-fix]]"\n'
        "    supports: original\n"
        "---\n\n# Refresh Strategy\n\nRefresh before expiry.\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = path.read_text()
    assert "confidence: high" in content
    assert "## Resolution History" in content
    assert "Resolved in favor of original" in content


def test_regenerate_contested_md(chronicles_dir):
    """CONTESTED.md is regenerated from contested articles."""
    from unittest.mock import patch

    articles_dir = chronicles_dir / "wiki" / "articles"
    (articles_dir / "some-article.md").write_text(
        "---\ntype: decision\nconfidence: contested\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n'
        'contested_by: "[[2026-04-15_challenge]]"\n'
        "previous_confidence: high\ntags: [auth]\n"
        "first_seen: 2026-04-01\nlast_confirmed: 2026-04-01\n---\n\n"
        "# Some Article\n\nOriginal claim here.\n"
    )

    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    contested_md = chronicles_dir / "CONTESTED.md"
    assert contested_md.exists()
    content = contested_md.read_text()
    assert "contested_count: 1" in content
    assert "[[some-article]]" in content
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/test_linter.py::test_resolve_contested_with_evidence tests/test_linter.py::test_regenerate_contested_md -v`
Expected: FAIL

- [ ] **Step 6: Implement `_resolve_contested()` and `_regenerate_contested()`**

Add to `src/chronicles/linter.py`:

```python
def _resolve_contested(
    articles: list[dict],
    report: LintReport,
) -> None:
    """Auto-resolve contested articles when 2+ sessions support one side."""
    today = _today()

    for article in articles:
        fm = article["frontmatter"]
        if fm.get("confidence") != "contested":
            continue

        # Check resolution_evidence
        evidence = fm.get("resolution_evidence", []) or []
        if len(evidence) < 2:
            continue

        # Count support for each side
        support_counts: dict[str, int] = {}
        for e in evidence:
            side = e.get("supports", "")
            if side:
                support_counts[side] = support_counts.get(side, 0) + 1

        # Find winning side (2+ supporters)
        winner = None
        for side, count in support_counts.items():
            if count >= 2:
                winner = side
                break

        if winner is None:
            continue

        path: Path = article["path"]
        text = article["text"]

        # Restore confidence to high
        text = re.sub(r"^confidence: contested", "confidence: high", text, count=1, flags=re.MULTILINE)

        # Remove contested_by and previous_confidence lines
        text = re.sub(r"contested_by:.*\n", "", text)
        text = re.sub(r"previous_confidence:.*\n", "", text)

        # Remove resolution_evidence block
        text = re.sub(r"resolution_evidence:\n(?:  - .+\n(?:    .+\n)*)*", "", text)

        # Build resolution history entry
        contested_by = fm.get("contested_by", "unknown")
        evidence_records = [e.get("record", "").strip('"') for e in evidence if e.get("supports") == winner]
        evidence_refs = ", ".join(evidence_records)
        history_entry = (
            f"## Resolution History\n"
            f"- **{today}**: Resolved in favor of {winner} ({evidence_refs})\n"
        )

        # Append to body
        text = text.rstrip("\n") + "\n\n" + history_entry

        path.write_text(text)
        article["text"] = text
        article["frontmatter"] = {**fm, "confidence": "high"}
        report.warnings.append(f"Resolved: {path.stem} in favor of {winner}")


def _regenerate_contested(
    chronicles_dir: Path,
    articles: list[dict],
    renderer: TemplateRenderer,
) -> int:
    """Rebuild CONTESTED.md from all contested articles."""
    contested_articles = [
        a for a in articles if a["frontmatter"].get("confidence") == "contested"
    ]

    contested_data = []
    for a in contested_articles:
        fm = a["frontmatter"]
        # Extract first line of body as the original claim
        body_match = re.match(r"^---\n.*?\n---\n\s*#[^\n]*\n\n(.+?)(\n|$)", a["text"], re.DOTALL)
        original_claim = body_match.group(1).strip().split("\n")[0] if body_match else ""

        contested_by_raw = str(fm.get("contested_by", ""))
        contested_by_match = re.search(r"\[\[([^\]]+)\]\]", contested_by_raw)
        contested_by = contested_by_match.group(1) if contested_by_match else "unknown"

        # Count evidence
        evidence = fm.get("resolution_evidence", []) or []
        evidence_for = sum(1 for e in evidence if e.get("supports") == "original")
        evidence_against = sum(1 for e in evidence if e.get("supports") != "original")

        contested_data.append({
            "title": a["path"].stem,
            "original_claim": original_claim,
            "contested_by": contested_by,
            "contested_reason": "conflicting evidence",
            "evidence_for": evidence_for,
            "evidence_against": evidence_against,
        })

    contested_path = chronicles_dir / "CONTESTED.md"
    content = renderer.render(
        "contested",
        {
            "date": _today(),
            "count": len(contested_articles),
            "articles": contested_data,
        },
    )
    contested_path.write_text(content)
    return len(contested_articles)
```

- [ ] **Step 7: Wire into `lint()`**

In the `lint()` function:

1. Add `_resolve_contested(articles, report)` after `_infer_relationships()`:
```python
    _detect_contested(chronicles_dir, articles, report)
    _infer_relationships(chronicles_dir, articles, report)
    _resolve_contested(articles, report)
    _detect_stale(chronicles_dir, articles, report)
```

2. Add `_regenerate_contested()` after `_regenerate_gold()`:
```python
    gold_count = _regenerate_gold(chronicles_dir, articles, renderer)
    report.gold_count = gold_count
    log.info("GOLD.md: %d high-confidence article(s)", gold_count)

    contested_count = _regenerate_contested(chronicles_dir, articles, renderer)
    if contested_count:
        log.info("CONTESTED.md: %d contested article(s)", contested_count)
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicles/linter.py src/chronicles/writer.py tests/test_linter.py tests/test_writer.py
git commit -m "feat: add conflict resolution workflows with evidence trails and CONTESTED.md"
```

---

### Task 6: Reorder Linter Steps

**Files:**
- Modify: `src/chronicles/linter.py`

- [ ] **Step 1: Reorder `lint()` to match spec**

The spec defines this ordering:
1. `rotate_records()`
2. `_load_articles()`
3. `_detect_and_merge_duplicates()` (semantic dedup)
4. `_check_wikilinks()`
5. `_infer_relationships()`
6. `_apply_decay()`
7. `_manage_confidence()`
8. `_calibrate_confidence()`
9. `_detect_contested()`
10. `_resolve_contested()`
11. `_detect_stale()`
12. `_regenerate_categories()`
13. `_add_related_sections()`
14. `_regenerate_gold()`
15. `_regenerate_contested()`

Rewrite `lint()` to match this ordering:

```python
def lint(chronicles_dir: Path) -> LintReport:
    """Main linter function."""
    report = LintReport()
    config = load_config(chronicles_dir)

    # 1. Archive old records
    moved = rotate_records(chronicles_dir, config.archive.after_days)
    if moved:
        log.info("Archived %d old record(s)", len(moved))
        report.warnings.append(f"Archived {len(moved)} old record(s)")

    renderer = TemplateRenderer()
    similarity_engine = _get_similarity_engine(config)

    # 2. Load articles
    articles_dir = chronicles_dir / "wiki" / "articles"
    articles, load_errors = _load_articles(articles_dir)
    report.errors.extend(load_errors)
    log.info("Loaded %d wiki article(s)", len(articles))

    # 3. Semantic dedup
    articles = _detect_and_merge_duplicates(articles, report, similarity_engine)

    # 4. Link integrity
    warnings = _check_wikilinks(articles)
    report.warnings.extend(warnings)
    if warnings:
        log.info("Found %d broken wikilink(s)", len(warnings))

    # 5. Infer relationships
    _infer_relationships(chronicles_dir, articles, report)

    # 6. Decay and pruning
    articles = _apply_decay(chronicles_dir, articles, config, report)

    # 7. Promote confidence
    promotions = _manage_confidence(articles, config.confidence.promotion_threshold)
    report.promotions.extend(promotions)
    if promotions:
        log.info("Promoted %d article(s): %s", len(promotions), ", ".join(promotions))

    # 8. Calibrate confidence
    _calibrate_confidence(articles, report)

    # 9. Detect contested
    _detect_contested(chronicles_dir, articles, report)

    # 10. Resolve contested
    _resolve_contested(articles, report)

    # 11. Detect stale
    _detect_stale(chronicles_dir, articles, report)

    # 12. Regenerate categories
    _regenerate_categories(chronicles_dir, articles, renderer)
    cat_dir = chronicles_dir / "wiki" / "categories"
    cat_count = len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0
    log.info("Regenerated %d category page(s)", cat_count)

    # 13. Related sections
    related_count = _add_related_sections(articles)
    if related_count:
        log.info("Added Related sections to %d article(s)", related_count)

    # 14. Regenerate GOLD.md
    gold_count = _regenerate_gold(chronicles_dir, articles, renderer)
    report.gold_count = gold_count
    log.info("GOLD.md: %d high-confidence article(s)", gold_count)

    # 15. Regenerate CONTESTED.md
    contested_count = _regenerate_contested(chronicles_dir, articles, renderer)
    if contested_count:
        log.info("CONTESTED.md: %d contested article(s)", contested_count)

    return report
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/chronicles/linter.py
git commit -m "refactor: reorder linter steps to match spec ordering"
```

---

### Task 7: Extractor Contested Awareness

**Files:**
- Modify: `src/chronicles/extractors/copilot_cli.py`
- Modify: `src/chronicles/cli.py`
- Modify: `tests/test_extractors/test_copilot_cli.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_extractors/test_copilot_cli.py`:

```python
def test_prompt_includes_contested_context():
    config = LLMConfig(provider="copilot-cli", model="gpt-5-mini")
    extractor = CopilotCLIExtractor(config)
    transcript = _make_cleaned_transcript()
    wiki_context = [
        {"title": "Refresh Strategy", "type": "decision", "tags": ["auth"],
         "path": "wiki/articles/refresh-strategy.md", "confidence": "contested"},
    ]
    prompt = extractor._build_prompt(transcript, wiki_context)
    assert "CONTESTED" in prompt
    assert "Refresh Strategy" in prompt
    assert '"resolve"' in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extractors/test_copilot_cli.py::test_prompt_includes_contested_context -v`
Expected: FAIL

- [ ] **Step 3: Extend `_build_prompt` to surface contested articles**

In `src/chronicles/extractors/copilot_cli.py`, in the `_build_prompt` method, after the existing wiki context block, add a contested section:

```python
        # Surface contested articles for resolution
        if wiki_context:
            contested = [a for a in wiki_context if a.get("confidence") == "contested"]
            if contested:
                lines.append("")
                lines.append("--- CONTESTED ARTICLES ---")
                lines.append("The following articles are CONTESTED — if this session provides evidence for either side, "
                             'include a wiki_instruction with action: "resolve" and the article path.')
                for article in contested:
                    lines.append(f"- {article['title']} (path={article.get('path', '?')})")
                lines.append("--- END CONTESTED ---")
```

Also update `_load_wiki_context` in `src/chronicles/cli.py` to include the `confidence` field:

In the `context.append(...)` call, add:
```python
            "confidence": fm.get("confidence", ""),
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicles/extractors/copilot_cli.py src/chronicles/cli.py tests/test_extractors/test_copilot_cli.py
git commit -m "feat: surface contested articles in extractor prompt for resolution"
```

---

### Task 8: Integration Test — Full Lifecycle


**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write integration test for the full lifecycle**

Add to `tests/test_integration.py`:

```python
def test_conflict_resolution_lifecycle(chronicles_dir):
    """Full lifecycle: article promoted -> contested -> evidence gathered -> resolved."""
    from unittest.mock import patch, MagicMock
    from chronicles.linter import lint, _parse_frontmatter

    articles_dir = chronicles_dir / "wiki" / "articles"
    records_dir = chronicles_dir / "records"

    # Step 1: Create a high-confidence article
    (articles_dir / "auth-pattern.md").write_text(
        "---\ntype: pattern\nconfidence: high\nsources:\n"
        '  - "[[2026-04-01_s1]]"\n  - "[[2026-04-02_s2]]"\n  - "[[2026-04-03_s3]]"\n'
        "tags: [auth]\nfirst_seen: 2026-04-01\nlast_confirmed: 2026-04-03\n---\n\n"
        "# Auth Pattern\n\nUse refresh-before-expiry.\n"
    )

    # Step 2: Create a record that contests it
    (records_dir / "2026-04-10_challenge.md").write_text(
        "---\ndate: 2026-04-10\n---\n\n# Challenge\n\n"
        "This contradicts [[auth-pattern]].\n"
    )

    # Run lint — should mark as contested
    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report = lint(chronicles_dir)

    content = (articles_dir / "auth-pattern.md").read_text()
    assert "confidence: contested" in content
    assert (chronicles_dir / "CONTESTED.md").exists()
    contested_md = (chronicles_dir / "CONTESTED.md").read_text()
    assert "auth-pattern" in contested_md

    # Step 3: Add resolution evidence (simulating what the writer would do)
    text = (articles_dir / "auth-pattern.md").read_text()
    text = text.replace(
        "\n---\n",
        "\nresolution_evidence:\n"
        '  - record: "[[2026-04-12_evidence1]]"\n'
        "    supports: original\n"
        '  - record: "[[2026-04-14_evidence2]]"\n'
        "    supports: original\n"
        "---\n",
        1,
    )
    (articles_dir / "auth-pattern.md").write_text(text)

    # Run lint again — should resolve
    with patch("chronicles.linter._get_similarity_engine", return_value=None):
        report2 = lint(chronicles_dir)

    content = (articles_dir / "auth-pattern.md").read_text()
    assert "confidence: high" in content
    assert "## Resolution History" in content
    assert "Resolved in favor of original" in content

    # CONTESTED.md should now be empty
    contested_md = (chronicles_dir / "CONTESTED.md").read_text()
    assert "contested_count: 0" in contested_md
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_integration.py::test_conflict_resolution_lifecycle -v`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add full conflict resolution lifecycle integration test"
```
