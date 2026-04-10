# Chronicles

Automatic knowledge extraction from agent session transcripts into a codebase-local wiki.

Every Claude Code / Copilot session is a source of engineering knowledge. Chronicles hooks into session end, extracts structured knowledge via LLM, and builds a wiki that compounds across sessions.

## Install

### Plugin (recommended)

Install the plugin to automatically capture knowledge from every session. Requires [uv](https://docs.astral.sh/uv/).

```bash
# Claude Code
claude plugin marketplace add AndurilCode/chronicles
claude plugin install chronicles@chronicles

# Copilot CLI
copilot plugin install AndurilCode/chronicles:plugin
```

The plugin is safe to install globally — it only activates in projects that have a `chronicles/` directory. To start using chronicles in a project:

```bash
chronicles init
```

This scaffolds the directory structure and generates a `config.yaml` through an interactive wizard. You can also pass flags for scripted setup:

```bash
chronicles init --provider ollama --model gemma3:12b --source claude-code --source copilot-cli
```

The plugin installs four hooks:
- **SessionStart** — injects `GOLD.md` and operational signals into the agent's context
- **SubagentStart** — injects operational signals into subagent context
- **SubagentStop** — extracts signals from subagent transcripts (async)
- **SessionEnd** — ingests the session transcript and extracts signals (async)

### Manual (pip)

```bash
pip install chronicles          # base (LLM-based dedup)
pip install chronicles[tfidf]   # recommended (fast local dedup via scikit-learn)
```

## Usage

```bash
# Initialize chronicles in a project (interactive or with flags)
chronicles init

# Ingest a session transcript
chronicles ingest path/to/session.jsonl

# Auto-discover recent sessions (most recent only)
chronicles ingest --since 7d --last 1

# Run wiki maintenance standalone
chronicles lint

# Generate category summaries
chronicles enrich

# Extract operational signals (agent mistakes, efficient patterns, user rules)
chronicles signals --since 7d --last 1
```

## What it produces

```
chronicles/
  config.yaml                # LLM provider, sources, and tuning options
  GOLD.md                    # High-confidence knowledge (read before acting)
  CHRONICLES.md              # Session index
  CONTESTED.md               # Articles with conflicting evidence
  SIGNALS.md                 # Operational rules extracted from agent behavior
  records/                   # Full session records
  archives/                  # Rotated old records
  wiki/
    articles/                # Convention, decision, pattern, trap pages
    categories/              # Auto-generated tag clusters with LLM summaries
```

## How knowledge compounds

1. **Session 1** extracts articles at `low`/`medium` confidence
2. **Session 2** confirms or contradicts — linter promotes (`medium` -> `high`) or contests
3. **Semantic dedup** merges overlapping articles, preserving sources
4. **Decay** demotes stale articles not confirmed in recent sessions
5. **GOLD.md** regenerates from `high`-confidence articles only
6. **Signals** extracts operational patterns — mistakes to avoid, efficient workflows, user rules

## Supported platforms

| Platform | Transcript format | Source key |
|----------|------------------|-----------|
| Claude Code | `.jsonl` | `claude-code` |
| Copilot CLI | `events.jsonl` | `copilot-cli` |
| Copilot VS Code | `.json` | `copilot-vscode` |

## Configuration

Run `chronicles init` to generate a config interactively, or create `chronicles/config.yaml` manually:

```yaml
# chronicles/config.yaml
llm:
  provider: claude-code        # claude-code | copilot-cli | ollama
  model: claude-haiku-4-5-20251001
  max_concurrent: 8

  # Per-step overrides (inherit from global if not set):
  # extract:
  #   model: claude-sonnet-4-5-20250514
  # enrich:
  #   model: claude-haiku-4-5-20251001

# Required for provider: ollama
# ollama:
#   base_url: http://localhost:11434
#   timeout: 300

sources:
  - claude-code
  - copilot-cli
  - copilot-vscode

similarity:
  engine: tfidf                # tfidf (fast, local) | llm (accurate, slow)
  threshold: 0.2

confidence:
  promotion_threshold: 3       # sessions needed for medium -> high

decay:
  high_to_medium_days: 180
  archive_after_days: 365

signals:
  max_active: 50
  demoted_retention_days: 90
```

See [docs/config.md](docs/config.md) for the full configuration reference.

## License

MIT
