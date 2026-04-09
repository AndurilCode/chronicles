# Chronicles

Automatic knowledge extraction from agent session transcripts into a codebase-local wiki.

Every Claude Code / Copilot session is a source of engineering knowledge. Chronicles hooks into session end, extracts structured knowledge via LLM, and builds a wiki that compounds across sessions.

## Install

```bash
pip install chronicles          # base (LLM-based dedup)
pip install chronicles[tfidf]   # recommended (fast local dedup via scikit-learn)
```

## Usage

```bash
# Ingest a session transcript
chronicles ingest path/to/session.jsonl

# Auto-discover recent sessions
chronicles ingest --since 7d

# Run wiki maintenance standalone
chronicles lint --chronicles-dir chronicles

# Generate category summaries
chronicles enrich --chronicles-dir chronicles
```

## What it produces

```
chronicles/
  GOLD.md                    # High-confidence knowledge (read before acting)
  CHRONICLES.md              # Session index
  CONTESTED.md               # Articles with conflicting evidence
  records/                   # Full session records
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

## Supported platforms

| Platform | Transcript format | Hook trigger |
|----------|------------------|-------------|
| Claude Code | `.jsonl` | `post_session` |
| Copilot CLI | `events.jsonl` | `sessionEnd` |
| Copilot VS Code | `.json` | `sessionEnd` |

## Configuration

```yaml
# chronicles/config.yaml
llm:
  provider: claude-code        # claude-code | copilot-cli
  model: claude-haiku-4-5
  max_concurrent: 8

similarity:
  engine: tfidf                # tfidf (fast, local) | llm (accurate, slow)
  threshold: 0.2
  confirm_engine: ""           # optional: llm for two-stage dedup
  confirm_threshold: 0.7

confidence:
  promotion_threshold: 3       # sessions needed for medium -> high

decay:
  high_to_medium_days: 180
  archive_after_days: 365
```

## License

MIT
