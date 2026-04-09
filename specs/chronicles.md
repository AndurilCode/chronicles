# Chronicles System Spec

> Automatic knowledge extraction from agent session transcripts into a codebase-local Obsidian wiki.

## Design Principles

- **Zero agent awareness**: The agent reads `GOLD.md` (validated knowledge) and `CHRONICLES.md` (recent activity) then works normally. It never writes to chronicles directly.
- **Every session is captured**: A post-session hook extracts structured knowledge from the full transcript.
- **Knowledge compounds**: Individual session records are mined into a wiki. Cross-session patterns increase confidence. High-confidence notes surface in `GOLD.md`.
- **Human curation is conversational**: Saying "this convention is wrong" in any session is enough. The extraction pipeline picks it up, lint reconciles it.
- **Platform-agnostic**: Supports multiple agent platforms (Claude Code, Copilot CLI, Copilot VS Code) through a pluggable adapter pattern. Adding a new platform means implementing one adapter.
- **Pluggable LLM backend**: The extraction LLM is configurable. Default is Copilot CLI (free tier). No vendor lock-in.

---

## Directory Structure

```
chronicles/
├── config.yaml                      # Pipeline configuration
├── GOLD.md                          # Agent entry point — high-confidence notes only
├── CHRONICLES.md                    # Session index — headers + wikilinks to records
├── records/
│   └── YYYY-MM-DD_branch-slug.md    # Full session chronicle
├── archives/
│   └── YYYY-QN/                     # Rotated old records
├── templates/
│   ├── record.md.j2                 # Record file template
│   ├── wiki_article.md.j2           # Wiki article template
│   ├── wiki_query.md.j2             # Wiki query template
│   ├── wiki_category.md.j2          # Wiki category index template
│   ├── chronicles_entry.md.j2       # CHRONICLES.md entry template
│   └── gold.md.j2                   # GOLD.md template
└── wiki/
    ├── articles/                    # Concept, convention, pattern, decision pages
    ├── categories/                  # Taxonomy index pages (tag clusters)
    └── queries/                     # Human questions answered from the KB
```

---

## Configuration

```yaml
# chronicles/config.yaml

llm:
  provider: copilot-cli              # copilot-cli | claude-code
  model: gpt-5-mini                  # model name or provider/model
  max_concurrent: 3                  # parallel extraction calls

sources:
  - claude-code
  - copilot-cli
  - copilot-vscode

confidence:
  promotion_threshold: 3             # sessions needed for medium -> high

archive:
  after_days: 90                     # rotate records older than this
```

Providers are extensible via the `BaseExtractor` interface. Two ship by default:
- **copilot-cli**: `copilot -p '{prompt}' --model {model}` (default, free tier)
- **claude-code**: `claude --print '{prompt}'`

---

## Architecture

### Pipeline Overview

```
Hook / CLI
    |
    v
chronicles ingest <path...> [--source X] [--since Nd]
    |
    |-- 1. Source Adapter (auto-detect or --source)
    |     Parse platform-specific JSONL -> Transcript
    |     Map tool names to canonical set
    |
    |-- 2. Cleaner
    |     Strip results from Read/Grep/Glob/Bash
    |     Keep results from Edit/Write/errors/tests
    |     Chunk at turn boundaries if needed
    |
    |-- 3. Extractor (pluggable LLM backend from config.yaml)
    |     LLM reads cleaned transcript
    |     Returns structured JSON (Record + wiki instructions)
    |
    +-- 4. Writer
          Write record to records/ (rendered via template)
          Append to CHRONICLES.md
          Create wiki stubs/articles from instructions

chronicles lint
    |
    |-- Structural validation
    |-- Link integrity
    |-- Duplicate detection + merge
    |-- Confidence lifecycle (promote/contest/stale)
    |-- Workaround tagging
    +-- GOLD.md regeneration
```

### Two-Phase Design

**`chronicles ingest`** handles stages 1-4: parse, clean, extract, write. Called by post-session hooks or manually.

**`chronicles lint`** handles wiki maintenance: validation, dedup merging, confidence lifecycle, GOLD.md regeneration. Runs after ingest, or standalone (e.g., after manual wiki edits).

### Parallelization

When processing multiple sessions:

1. **Parse + clean**: parallel across sessions (`ProcessPoolExecutor`)
2. **Extract**: parallel across sessions (`ThreadPoolExecutor`, I/O-bound subprocess calls). Concurrency controlled by `llm.max_concurrent` in config.
3. **Write**: records written in parallel (no conflicts). Wiki updates applied sequentially (handles overlaps, dedup, merge decisions in deterministic order).

---

## Source Adapters

Borrows the adapter pattern from Sift (`claude-token-analysis`). Each platform implements `BaseSource`:

```python
class BaseSource(ABC):
    def name(self) -> str: ...        # Human-readable, e.g. "Claude Code"
    def key(self) -> str: ...         # Machine key, e.g. "claude-code"
    def available(self) -> bool: ...  # Check if data directory exists
    def parse_session(self, session_path: str) -> Transcript: ...
    def discover_sessions(self, since: datetime) -> list[str]: ...
```

`discover_sessions` supports the batch use case (`--since`). `parse_session` supports the hook use case (single path).

### Source Detection

`chronicles ingest` auto-detects the source by inspecting file content (each platform's JSONL has distinct event shapes). Override with `--source` flag when needed.

### Platform Compatibility Matrix

| Platform | Transcript path | Source detection | Hook trigger |
|---|---|---|---|
| Claude Code | Provided by hook | Auto-detect from content | `post_session` |
| Copilot VS Code | Provided by hook | Auto-detect from content | `sessionEnd` |
| Copilot CLI | Inferred from timestamp + cwd | Auto-detect from content | `sessionEnd` |

### Tool Name Normalization

Each adapter maps platform-specific tool names to a canonical set:

```python
# Example: Copilot CLI adapter
TOOL_NAME_MAP = {
    "readFile": "Read",
    "editFile": "Edit",
    "runCommand": "Bash",
    # ...
}
```

The cleaner operates on canonical names only — one set of filtering rules regardless of source.

---

## Transcript Format

### Common Interface

All adapters produce a `Transcript` dataclass:

```python
@dataclass
class Message:
    role: str              # "user" | "assistant" | "tool_call" | "tool_result"
    content: str
    timestamp: str         # ISO 8601
    tool_name: str = ""    # for tool_call / tool_result (canonical name)
    tool_input: dict = {}  # for tool_call

@dataclass
class Transcript:
    session_id: str
    source: str            # "claude-code" | "copilot-cli" | "copilot-vscode"
    project: str
    repository: str
    branch: str
    cwd: str
    timestamp_start: str
    timestamp_end: str
    model: str
    messages: list[Message]
```

### Cleaning Rules

The cleaner filters tool results based on canonical tool names:

**Strip results from** (high-volume, low-signal):
- `Read`, `Grep`, `Glob`, `Bash`, `ls`, `cat`

**Keep results from** (high-signal):
- `Edit`, `Write`, `NotebookEdit` (what changed)
- Failed commands (non-zero exit, error output)
- Test output, lint output

Tool calls (name + input) are always preserved regardless of filtering.

### Turn-Based Chunking

A "turn" = user message + assistant response + associated tool calls/results.

- If the cleaned transcript fits in context, it is sent as a single chunk
- If not, it is split at turn boundaries — never mid-turn
- Each chunk after the first receives a preamble: a running summary of what previous chunks covered (generated by the extractor after processing each chunk)
- Final output merges extracted knowledge from all chunks, deduplicating

```python
@dataclass
class CleanedTranscript:
    metadata: TranscriptMetadata  # session_id, source, project, branch, etc.
    chunks: list[list[Message]]   # list of chunks, each a list of messages
```

---

## Extractor

Pluggable LLM backend. Takes a `CleanedTranscript`, returns structured JSON.

```python
class BaseExtractor(ABC):
    def extract(self, transcript: CleanedTranscript) -> Record: ...

class CopilotCLIExtractor(BaseExtractor):
    """Runs: copilot -p '{prompt}' --model {model}"""

class ClaudeCodeExtractor(BaseExtractor):
    """Runs: claude --print '{prompt}'"""
```

### Extractor Output Schema

The LLM returns structured JSON:

```json
{
  "branch": "feat/oauth-connections",
  "status": "complete",
  "tags": ["oauth", "mcp-connections", "rate-limiting"],
  "duration": "45min",
  "files_changed": ["src/connections/refresh.ts", "tests/refresh.test.ts"],
  "objective": "Implement OAuth token refresh for MCP connections",
  "outcome": "Working refresh flow, 3 new tests, discovered rate-limit edge case",
  "decisions": [
    {
      "description": "Chose refresh-before-expiry over refresh-on-401",
      "rationale": "avoids retry complexity, trades ~5% unnecessary refreshes"
    }
  ],
  "problems": [
    {
      "description": "token_endpoint returns 403 when scope param includes offline_access",
      "root_cause": "provider expects space-delimited, we sent comma-delimited",
      "dead_end": false
    }
  ],
  "discovered": [
    {"type": "convention", "description": "All MCP connection configs use _connection suffix pattern"},
    {"type": "missing-context", "description": "No docs on token introspection support"},
    {"type": "workaround", "description": "Rate-limit retry uses hardcoded 60s -- needs backoff"}
  ],
  "continuity": {
    "unfinished": ["Error UX when refresh fails -- user sees raw 403"],
    "open_questions": ["Should expired tokens auto-disconnect or queue?"],
    "next": ["Add backoff to rate-limit retry, then wire error UX"]
  },
  "wiki_instructions": [
    {
      "action": "create",
      "path": "wiki/articles/mcp-connection-config-suffix-pattern.md",
      "data": {
        "title": "MCP Connection Config Suffix Pattern",
        "type": "convention",
        "confidence": "low",
        "tags": ["naming", "mcp", "conventions"],
        "body": "All MCP connection configurations use the `_connection` suffix.",
        "evidence": ["Discovered in feat/oauth-connections session"],
        "implications": ["New connection configs MUST follow this pattern"]
      }
    }
  ]
}
```

For multi-chunk transcripts: the extractor processes chunks sequentially, carrying forward a summary context. Final output merges extracted knowledge from all chunks, deduplicating.

---

## Templates

All output files are rendered via Jinja2 templates in `chronicles/templates/`. Users can customize formatting without touching the extraction prompt.

### Record Template (`templates/record.md.j2`)

Renders to `records/YYYY-MM-DD_branch-slug.md`:

```markdown
---
date: {{date}}
branch: {{branch}}
status: {{status}}
tags: {{tags}}
agent: {{source}}
duration: {{duration}}
files_changed:
{% for f in files_changed %}  - {{f}}
{% endfor %}---

# {{branch}}

> **Objective**: {{objective}}
> **Outcome**: {{outcome}}

## Decisions
{% for d in decisions %}- {{d.description}} -- {{d.rationale}}
{% endfor %}
## Problems
{% for p in problems %}{% if p.dead_end %}- Dead end: {{p.description}}, {{p.root_cause}}
{% else %}- `{{p.description}}`
  -> root cause: {{p.root_cause}}
{% endif %}{% endfor %}
## Discovered
{% for d in discovered %}- [{{d.type}}] {{d.description}}
{% endfor %}
## Continuity
{% for u in continuity.unfinished %}- **Unfinished**: {{u}}
{% endfor %}{% for q in continuity.open_questions %}- **Open question**: {{q}}
{% endfor %}{% for n in continuity.next %}- **Next**: {{n}}
{% endfor %}
```

### Wiki Article Template (`templates/wiki_article.md.j2`)

```markdown
---
type: {{type}}
confidence: {{confidence}}
sources:
{% for s in sources %}  - "[[{{s}}]]"
{% endfor %}first_seen: {{first_seen}}
last_confirmed: {{last_confirmed}}
tags: {{tags}}
---

# {{title}}

{{body}}

## Evidence
{% for e in evidence %}- {{e}}
{% endfor %}
## Implications
{% for i in implications %}- {{i}}
{% endfor %}
```

### Wiki Query Template (`templates/wiki_query.md.j2`)

```markdown
---
type: query
asked_by: {{asked_by}}
date: {{date}}
answered_from:
{% for a in answered_from %}  - "[[{{a}}]]"
{% endfor %}tags: {{tags}}
---

# {{question}}

{{answer}}
```

### Wiki Category Template (`templates/wiki_category.md.j2`)

```markdown
---
type: category
tags: {{tags}}
---

# {{title}}

{% for a in articles %}- [[{{a}}]]
{% endfor %}
{% if open_questions %}## Open Questions
{% for q in open_questions %}- [[{{q}}]]
{% endfor %}{% endif %}
```

### CHRONICLES.md Entry Template (`templates/chronicles_entry.md.j2`)

```markdown
## [[{{date}}_{{slug}}|{{branch}}]] | {{status_icon}} {{status_label}}
> **Objective**: {{objective}}
> **Outcome**: {{outcome}}
> **Tags**: {{tags_as_hashtags}}
```

Status icon mapping: `complete` -> checkmark, `partial` -> warning, `failed` -> cross, `exploratory` -> magnifying glass.

### GOLD.md Template (`templates/gold.md.j2`)

Fully regenerated by lint from all `confidence: high` articles:

```markdown
---
type: gold-index
last_updated: {{date}}
promoted_count: {{count}}
---

# Gold Notes

> High-confidence, validated knowledge for this repository. Read before acting.

{% for group_name, articles in groups %}## {{group_name}}
{% for a in articles %}- [[{{a.title}}]] -- {{a.summary}}
{% endfor %}
{% endfor %}
```

Groups are derived from article `type`: `convention` -> "Conventions", `decision` -> "Architecture Decisions", `trap` -> "Known Traps", `workaround` -> "Workarounds".

### Contested Article Extension

When lint marks an article as contested, additional frontmatter is added:

```yaml
confidence: contested
contested_by: "[[2026-05-03_refactor-connections]]"
previous_confidence: high
```

Agent seeing `contested` reads both sides before acting. Lint flags contested gold notes for human attention.

---

## Formats

### CHRONICLES.md (Index)

```yaml
---
type: chronicles-index
last_updated: 2026-04-09
record_count: 47
---
```

```markdown
# Chronicles

## [[2026-04-09_feat-oauth|feat/oauth-connections]] | complete
> **Objective**: Implement OAuth token refresh for MCP connections
> **Outcome**: Working refresh flow, discovered rate-limit edge case
> **Tags**: #oauth #mcp-connections #rate-limiting

## [[2026-04-08_fix-retry|fix/retry-backoff]] | partial
> **Objective**: Add exponential backoff to rate-limit retry
> **Outcome**: Backoff implemented, edge case with concurrent refreshes unresolved
> **Tags**: #rate-limiting #retry
```

Navigation design: an agent scans headers (~30 tokens each) to decide which records to read in full.

### GOLD.md (Agent Entry Point)

```yaml
---
type: gold-index
last_updated: 2026-04-09
promoted_count: 12
---
```

```markdown
# Gold Notes

> High-confidence, validated knowledge for this repository. Read before acting.

## Conventions
- [[MCP Connection Config Suffix Pattern]] -- all connection configs use `_connection` suffix
- [[Token Storage in Config Not Env]] -- credentials persist in config, not env vars

## Architecture Decisions
- [[Refresh Before Expiry Strategy]] -- proactive refresh, no retry-on-401

## Known Traps
- [[Scope Param Delimiter]] -- space-delimited, not comma -- multiple agents hit this

## Workarounds
- [[Rate Limit Retry Backoff]] -- workaround in place, proper fix pending
```

Auto-generated by lint from `confidence: high` articles. One-liner per entry -- the agent gets the essence without following links.

---

## Pipeline Detail

### Extraction (chronicles ingest)

**Input**: One or more transcript file paths, or `--since Nd` for batch discovery.

**Steps**:

1. For each path, auto-detect source (or use `--source` override)
2. Parse via source adapter into `Transcript`
3. Clean: normalize tool names, apply filtering rules, chunk at turn boundaries
4. Extract via configured LLM backend: send cleaned transcript, receive structured JSON
5. Validate JSON against expected schema
6. Render record via template, write to `records/`
7. Append entry to `CHRONICLES.md` via template
8. Process `wiki_instructions`: create/update articles, queries, category indexes

Steps 1-4 run in parallel across sessions. Step 5-8 run sequentially for wiki consistency.

### Lint (chronicles lint)

**Input**: Entire `chronicles/` directory.

**Output**: Fixes applied in-place + report.

**Responsibilities**:

1. **Structural validation**: frontmatter consistency, required fields present
2. **Link integrity**: detect broken `[[wikilinks]]`, flag orphan articles (no inbound links)
3. **Duplicate detection**: articles covering the same concept -> merge
4. **Confidence lifecycle**:
   - `low` -> `medium`: article confirmed by 2+ independent sessions
   - `medium` -> `high`: confirmed by N sessions (configurable `promotion_threshold`) or human validation in transcript
   - `high` -> `contested`: contradicted by a later session -- flag, don't auto-demote
   - Stale detection: high-confidence notes not referenced in N sessions
5. **GOLD.md regeneration**: rebuild from all `confidence: high` articles via template, grouped by type
6. **Workaround tagging**: workarounds in records get linked to wiki articles tagged `workaround`

### Confidence Lifecycle

| Transition | Trigger | Actor |
|---|---|---|
| -> `low` | First mention in a single session | Extraction (ingest) |
| -> `medium` | Human states directly in conversation, OR confirmed by 2+ sessions | Extraction (ingest) |
| -> `high` | Confirmed by N independent sessions OR human explicit validation | Lint |
| -> `contested` | Contradicted by a later session | Lint |
| `contested` -> resolved | Human clarifies in conversation, next extraction picks it up | Extraction + lint |
| Stale detection | High-confidence note not referenced in N sessions | Lint (flag only) |

---

## Archive Policy

Records older than a configurable threshold (default: 90 days) are moved to `archives/YYYY-QN/`. Their wiki contributions persist -- only the raw records rotate. `CHRONICLES.md` entries for archived records get a `(archived)` suffix but remain in the index for navigability.

---

## CLAUDE.md / AGENTS.md Integration

```markdown
## Chronicles
This repo maintains a knowledge base in `chronicles/`.
Read `chronicles/GOLD.md` before any task -- it contains validated
conventions, decisions, and known traps.
Read `chronicles/CHRONICLES.md` to understand recent session activity,
ongoing work, and current state of the codebase.
Deeper context available in `chronicles/wiki/` if needed.
```

The agent does not need to know how chronicles are produced. It reads. It works. Its session becomes the next chronicle automatically.

---

## Technology

- **Language**: Python
- **Templates**: Jinja2
- **CLI**: `chronicles ingest` and `chronicles lint`
- **Parallelization**: `ProcessPoolExecutor` (parse/clean), `ThreadPoolExecutor` (extract)
- **LLM backends**: Copilot CLI (default), Claude Code CLI (extensible via `BaseExtractor`)
