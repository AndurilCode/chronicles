# Agentic Signals Extractor

## Overview

A parallel pipeline that extracts agentic operational patterns from session transcripts and injects them as natural language rules into future sessions via `SIGNALS.md`.

While the existing wiki pipeline captures **what was learned** about the codebase (conventions, decisions, traps), the signals pipeline captures **how the agent behaved** — tool mistakes, inefficient sequences, and successful patterns that help future agents operate more effectively.

## Architecture

The signals pipeline runs parallel to the wiki pipeline, sharing only the source layer:

```
Transcript (JSONL)
    |
    +-- Wiki Pipeline (existing)
    |   cleaner -> extractor -> writer -> CHRONICLES.md, wiki/articles/
    |
    +-- Signals Pipeline (new)
        signals_cleaner -> signals_extractor -> signals_writer -> SIGNALS.md
```

### Shared with wiki pipeline

- Source parsers (`sources/`) — same transcript format
- Config (`config.yaml`) — LLM settings, model
- Models (`models.py`) — `Transcript`, `Message`, `TranscriptMetadata`

### Independent from wiki pipeline

- Cleaner logic, extractor prompts, writer output, lifecycle management
- CLI command, hook scripts

## Components

### 1. Signals Cleaner (`signals_cleaner.py`)

The current wiki cleaner strips tool results as low-signal. The signals cleaner does the opposite — tool interactions are the primary signal source.

**Keeps:**

- All tool calls with their parameters (which tool, what arguments)
- Tool results — especially errors, retries, and empty results
- Agent reasoning/thinking that led to tool choices
- Permission denials and hook feedback
- User corrections ("no, not that", "stop", "wrong file")

**Strips:**

- File content returned by Read/Grep (the actual code is not relevant to behavioral patterns)
- Large bash output (keep exit codes and first/last few lines)
- User messages that are pure requirements/instructions

**Chunking:** Sequences of related tool calls grouped by operational intent. A new chunk starts when the agent switches from one activity to another (e.g., searching to editing, or navigating to testing). Chunk boundaries are detected by: change in tool type category (search tools vs. edit tools vs. execution tools), user messages that redirect the agent, or explicit agent reasoning that shifts focus. Each chunk represents an operational unit the extractor can evaluate.

Output is a `CleanedTranscript` (same model, different content) — a compact representation of what the agent did, not what it learned.

### 2. Signals Extractor (`signals_extractor.py`)

An LLM-powered extractor with a prompt focused on detecting two categories.

#### Mistakes (anti-patterns)

- Wrong tool for the task (e.g., `Bash` with `grep` when `Grep` tool available)
- Failed searches that could have been avoided with codebase knowledge
- Circular exploration — searching the same thing multiple ways before finding it
- Unnecessary retries or repeated failed approaches
- Overly broad operations (reading entire files when a specific range was needed)

#### Efficient patterns (worth repeating)

- Direct navigation to the right file/location without searching
- Effective tool combinations for common tasks
- Good recovery strategies after initial failures

#### Extraction output

A list of signals, each with:

- `pattern`: natural language description of what happened
- `type`: `mistake` or `efficient`
- `rule`: the imperative instruction for future agents (e.g., "When looking for test files in this repo, check `tests/` not `test/`")
- `context`: relevant file paths, tool names, or codebase areas this applies to
- `severity`: `high` (wasted significant effort) or `low` (minor inefficiency)

#### Contradiction detection

The extractor receives current `SIGNALS.md` content. If it observes behavior that contradicts an existing signal (e.g., a signal says "do X" but the agent succeeded by doing the opposite), it marks that signal for removal.

### 3. Signals Writer (`signals_writer.py`)

Maintains a single `SIGNALS.md` file in the chronicles directory.

#### Format

```markdown
# Signals

## Active

- When searching for source modules, check `src/chronicles/` directly — the `src/` directory has only one package. [tool:Glob,Grep] [area:navigation]
- Use `Grep` tool instead of `Bash` with `rg` — the dedicated tool has better permissions and output handling. [tool:Bash,Grep] [area:tool-choice]
- The `plugin/` directory contains hooks and scripts — don't search `src/` for hook-related code. [tool:Glob] [area:navigation]

## Demoted

- ~~Check `lib/` for utility functions~~ (contradicted: session abc123, 2026-04-08 — no `lib/` directory exists)
```

#### Design choices

- Flat list of natural language rules under `## Active`
- Lightweight tags in brackets for tool and area context (hints for the LLM reader, not structured for machines)
- `## Demoted` section for contradicted signals — kept for auditability, pruned after a configurable period
- High-severity signals at the top of the list
- No frontmatter, no YAML — this file is meant to be injected raw into a system prompt

#### Size management

Cap at 50 active signals. When the list exceeds this, drop the oldest low-severity signals first.

### 4. CLI

New command independent of the wiki ingest:

```
chronicles signals <transcript_path> --chronicles-dir <path>
```

Command flow:

1. Parse transcript via appropriate source adapter
2. Clean transcript with signals cleaner (preserve tool interactions)
3. Load current `SIGNALS.md` for contradiction detection
4. Run signals extractor
5. Update `SIGNALS.md` — add new signals, demote contradicted ones, enforce cap

### 5. Hook Integration

Two new scripts alongside the existing hooks:

**`plugin/scripts/signals-ingest.sh`** (SessionEnd):
- Same pattern as `ingest.sh` but calls `chronicles signals <path>`

**`plugin/scripts/signals-context.sh`** (SessionStart):
- Reads `chronicles/SIGNALS.md`, extracts the `## Active` section, outputs it as system context

Updated `plugin/hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/gold-context.sh\"", "timeout": 10 },
          { "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/signals-context.sh\"", "timeout": 10 }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/ingest.sh\"", "timeout": 600 },
          { "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/signals-ingest.sh\"", "timeout": 600 }
        ]
      }
    ]
  }
}
```

Both SessionEnd hooks run independently — if one fails, the other still proceeds.

## Signal Lifecycle

1. **First observation** — signal is extracted and added to `## Active` immediately
2. **Active** — injected into every future session via SessionStart hook
3. **Contradicted** — if a later session shows the signal is wrong, it moves to `## Demoted` with the contradicting session reference
4. **Pruned** — demoted signals are removed after a configurable period (default: same as `archive.after_days` in config)
5. **Overflow** — when active signals exceed 50, oldest low-severity signals are dropped

No promotion threshold. The value is in fast feedback loops — agentic mistakes are expensive to repeat, and a wrong signal in `SIGNALS.md` is low-cost (an agent can override it).

## Configuration

Extends `config.yaml` with a `signals` section:

```yaml
signals:
  max_active: 50
  demoted_retention_days: 90
```

Reuses existing `llm` config for model and concurrency settings.
