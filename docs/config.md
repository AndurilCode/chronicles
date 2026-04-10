# Configuration Reference

Chronicles is configured via `chronicles/config.yaml`. All sections are optional — sensible defaults are used when absent.

## Full Example

```yaml
# ──────────────────────────────────────────────────
# LLM Provider
# ──────────────────────────────────────────────────
llm:
  provider: claude-code          # claude-code | copilot-cli | ollama
  model: claude-haiku-4-5-20251001
  max_concurrent: 8              # parallel LLM calls (extraction, enrichment)

  # Per-step overrides (optional).
  # Each step inherits from the global llm settings above.
  # Only specify the fields you want to override.
  extract:
    provider: ollama
    model: gemma4:26b
  enrich:
    model: claude-haiku-4-5-20251001
  signals:
    provider: ollama
    model: qwen3.5:9b
  similarity:
    model: claude-haiku-4-5-20251001

# ──────────────────────────────────────────────────
# Ollama Settings (only used when provider is "ollama")
# ──────────────────────────────────────────────────
ollama:
  base_url: http://localhost:11434   # Ollama server address
  timeout: 300                       # seconds per request
  temperature: 0.0                   # 0 = greedy decoding
  num_ctx: 0                         # context window size (0 = model default)
  num_predict: 0                     # max output tokens (0 = model default)

# ──────────────────────────────────────────────────
# Transcript Sources
# ──────────────────────────────────────────────────
sources:
  - claude-code
  - copilot-cli
  - copilot-vscode

# ──────────────────────────────────────────────────
# Wiki Confidence Lifecycle
# ──────────────────────────────────────────────────
confidence:
  promotion_threshold: 3       # sessions confirming an article before promotion to high

# ──────────────────────────────────────────────────
# Confidence Decay
# ──────────────────────────────────────────────────
decay:
  high_to_medium_days: 180     # days without confirmation before high → medium
  medium_to_low_days: 270      # days without confirmation before medium → low
  archive_after_days: 365      # days without confirmation before archiving

# ──────────────────────────────────────────────────
# Record Archiving
# ──────────────────────────────────────────────────
archive:
  after_days: 90               # move records to archives/ after N days

# ──────────────────────────────────────────────────
# Enrichment
# ──────────────────────────────────────────────────
enrich:
  enabled: true                # auto-enrich after ingest (category summaries)

# ──────────────────────────────────────────────────
# Similarity / Deduplication
# ──────────────────────────────────────────────────
similarity:
  engine: tfidf                # tfidf | llm
  threshold: 0.2               # minimum score to flag as potential duplicate
  confirm_engine: ""           # optional second-stage engine (e.g. "llm")
  confirm_threshold: 0.7       # threshold for second-stage confirmation

# ──────────────────────────────────────────────────
# Knowledge Gaps Detection
# ──────────────────────────────────────────────────
gaps:
  enabled: true
  git_lookback_days: 90        # how far back to scan git history

# ──────────────────────────────────────────────────
# Operational Signals
# ──────────────────────────────────────────────────
signals:
  max_active: 50               # max active signals before oldest are demoted
  demoted_retention_days: 90   # days to keep demoted signals before removal
  subagents: true              # also extract signals from subagent sessions
```

---

## Section Details

### `llm`

The global LLM configuration used across all pipeline steps.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | string | `copilot-cli` | LLM backend: `claude-code`, `copilot-cli`, or `ollama` |
| `model` | string | `gpt-5-mini` | Model name passed to the provider |
| `max_concurrent` | int | `3` | Max parallel LLM calls |

#### Per-step Overrides

Each pipeline step that uses an LLM can override `provider` and/or `model`. Unspecified fields inherit from the global `llm` section. `max_concurrent` is always inherited.

| Step | Used by | Description |
|------|---------|-------------|
| `extract` | `chronicles ingest` | Knowledge extraction from transcripts |
| `enrich` | `chronicles enrich` | Category summary generation |
| `signals` | `chronicles signals` | Operational signal detection |
| `similarity` | `chronicles lint` | LLM-backed duplicate detection (when `similarity.engine: llm`) |

### `ollama`

Configuration for the Ollama provider. Only relevant when at least one step uses `provider: ollama`. These settings apply globally to all ollama calls.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `base_url` | string | `http://localhost:11434` | Ollama server URL. Change for remote servers or custom ports. |
| `timeout` | int | `300` | Request timeout in seconds. Increase for large models or slow hardware. |
| `temperature` | float | `0.0` | Sampling temperature. `0` = deterministic (greedy). |
| `num_ctx` | int | `0` | Context window size. `0` = use model default. Set explicitly for models that support large contexts. |
| `num_predict` | int | `0` | Max output tokens. `0` = use model default. |

### `sources`

List of transcript sources to scan when using `--since`. Available sources:

- `claude-code` — Claude Code CLI sessions (`~/.claude/projects/`)
- `copilot-cli` — GitHub Copilot CLI sessions
- `copilot-vscode` — Copilot Chat in VS Code

### `confidence`

Controls how wiki articles are promoted from `medium` to `high` confidence.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `promotion_threshold` | int | `3` | Number of independent sessions confirming an article before it reaches `high` confidence |

### `decay`

Controls automatic confidence demotion when articles are not reconfirmed.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `high_to_medium_days` | int | `180` | Days without confirmation before `high` → `medium` |
| `medium_to_low_days` | int | `270` | Days without confirmation before `medium` → `low` |
| `archive_after_days` | int | `365` | Days without confirmation before article is archived |

### `archive`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `after_days` | int | `90` | Move ingestion records from `records/` to `archives/` after this many days |

### `enrich`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Automatically run enrichment after ingestion |

### `similarity`

Controls wiki deduplication during lint.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `engine` | string | `tfidf` | Similarity engine: `tfidf` (fast, local) or `llm` (uses configured LLM) |
| `threshold` | float | `0.2` | Minimum similarity score to flag as potential duplicate |
| `confirm_engine` | string | `""` | Optional second-stage engine for higher-confidence dedup |
| `confirm_threshold` | float | `0.7` | Threshold for second-stage confirmation |

### `gaps`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enable knowledge gap detection based on git history |
| `git_lookback_days` | int | `90` | How far back to scan git history for uncovered areas |

### `signals`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_active` | int | `50` | Maximum active signals. Oldest are demoted when exceeded. |
| `demoted_retention_days` | int | `90` | Days to keep demoted signals in `SIGNALS.md` |
| `subagents` | bool | `true` | Also process subagent transcripts for signals |

---

## Use Case Configurations

### Cloud API only (default)

Use Claude or Copilot as the sole provider. Simple setup, nothing to run locally.

```yaml
llm:
  provider: claude-code
  model: claude-haiku-4-5-20251001
  max_concurrent: 8
```

### Fully local with Ollama

Run everything on your own hardware. No API keys needed.

```yaml
llm:
  provider: ollama
  model: gemma4:26b
  max_concurrent: 4

ollama:
  timeout: 600        # local models are slower
```

### Hybrid: smart model for extraction, fast model for the rest

Use a capable model for the hard task (knowledge extraction) and a cheaper/faster model for simpler tasks.

```yaml
llm:
  provider: claude-code
  model: claude-haiku-4-5-20251001
  max_concurrent: 8
  extract:
    model: claude-sonnet-4-5-20250514
```

### Hybrid: local extraction, cloud enrichment

Extract locally to avoid sending full transcripts to the cloud, but use a cloud model for the smaller enrichment prompts.

```yaml
llm:
  provider: claude-code
  model: claude-haiku-4-5-20251001
  max_concurrent: 8
  extract:
    provider: ollama
    model: gemma4:26b
  signals:
    provider: ollama
    model: gemma4:26b

ollama:
  timeout: 600
```

### Remote Ollama server

Run Ollama on a beefy machine and connect from your laptop.

```yaml
llm:
  provider: ollama
  model: qwen3.5:35b-a3b
  max_concurrent: 2

ollama:
  base_url: http://192.168.1.50:11434
  timeout: 600
  num_ctx: 32768
```
