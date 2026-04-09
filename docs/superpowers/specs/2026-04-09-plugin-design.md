# Chronicles Plugin Design

## Summary

A plugin directory inside the chronicles repo (`plugin/`) that auto-installs hooks for both Claude Code and Copilot CLI. The plugin:

1. **SessionEnd**: Ingests the session transcript via `uvx` from the GitHub repo
2. **SessionStart**: Injects GOLD.md content + orientation blurb as additional context

Install path: `claude plugin install AndurilCode/chronicles:plugin` / `copilot plugin install AndurilCode/chronicles:plugin`

## Structure

```
plugin/
├── .claude-plugin/
│   └── plugin.json              # Claude Code manifest
├── plugin.json                  # Copilot CLI manifest
├── hooks/
│   ├── claude-code.json         # SessionStart + SessionEnd (PascalCase events)
│   └── copilot-cli.json         # sessionStart + sessionEnd (camelCase events)
└── scripts/
    ├── ingest.sh                # Shared: ingest transcript on session end
    └── gold-context.sh          # Shared: inject GOLD.md + orientation on session start
```

## Manifests

### Claude Code (`.claude-plugin/plugin.json`)

```json
{
  "name": "chronicles",
  "version": "0.1.0",
  "description": "Auto-extract knowledge from agent sessions into a codebase wiki",
  "repository": "https://github.com/AndurilCode/chronicles",
  "license": "MIT",
  "hooks": "../hooks/claude-code.json",
  "userConfig": {
    "chronicles_dir": {
      "description": "Path to chronicles wiki directory (relative to project root)",
      "default": "chronicles"
    }
  }
}
```

### Copilot CLI (`plugin.json`)

```json
{
  "name": "chronicles",
  "version": "0.1.0",
  "description": "Auto-extract knowledge from agent sessions into a codebase wiki",
  "repository": "https://github.com/AndurilCode/chronicles",
  "license": "MIT",
  "hooks": "hooks/copilot-cli.json"
}
```

No `userConfig` — Copilot CLI doesn't support it. Uses `$CHRONICLES_DIR` env var or defaults to `chronicles`.

## Hooks

### Claude Code (`hooks/claude-code.json`)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/gold-context.sh",
        "timeout": 10
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.sh",
        "timeout": 600
      }
    ]
  }
}
```

### Copilot CLI (`hooks/copilot-cli.json`)

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "type": "command",
        "bash": "./scripts/gold-context.sh",
        "timeoutSec": 10
      }
    ],
    "sessionEnd": [
      {
        "type": "command",
        "bash": "./scripts/ingest.sh",
        "timeoutSec": 600
      }
    ]
  }
}
```

Note: Copilot CLI hooks use relative paths from the plugin root (no `$PLUGIN_ROOT` env var available).

## Scripts

### `scripts/gold-context.sh` — SessionStart context injection

Reads `cwd` from stdin JSON. Finds GOLD.md relative to cwd. Outputs orientation blurb + GOLD.md content.

**Config resolution order:**
1. `$CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR` (Claude Code userConfig)
2. `$CHRONICLES_DIR` (manual env var, works on both platforms)
3. Default: `chronicles`

**Output format:** Plain text to stdout (Claude Code injects stdout as context ≤10K chars). For Copilot CLI compatibility, wraps in `{"additionalContext": "..."}` JSON if the `COPILOT_CLI` env marker is detected — but since Copilot CLI plugin sessionStart context injection has known limitations, this is best-effort.

**Orientation blurb** (prepended before GOLD.md content):

```
This project uses Chronicles — an automatic knowledge wiki built from agent sessions.
The chronicles wiki is at: <dir>/
- GOLD.md: High-confidence validated knowledge. Read this for known conventions, decisions, and traps.
- CHRONICLES.md: Session index with all ingested sessions.
- CONTESTED.md: Articles with conflicting evidence across sessions.
- wiki/articles/: Individual knowledge articles at various confidence levels.
- wiki/categories/: Auto-generated topic clusters.
Read GOLD.md below for validated project knowledge:
```

**Behavior:**
- **Guard: exit early if chronicles dir doesn't exist** — `[ -d "$CHRONICLES_DIR" ] || exit 0`. This makes the plugin safe to install globally; it only activates in projects that have a chronicles directory.
- If GOLD.md is missing: output orientation blurb only (without the "Read GOLD.md below" line)
- If GOLD.md exists but is empty (only frontmatter, 0 promoted entries): output orientation blurb only (without GOLD.md content)
- If GOLD.md exists and has content: output orientation blurb + GOLD.md content
- Always exit 0 (non-blocking)

### `scripts/ingest.sh` — SessionEnd transcript ingestion

Reads stdin JSON for `transcript_path` and `cwd`. Calls `uvx` to run chronicles ingest.

**Config resolution:** Same as gold-context.sh.

**Logic:**
1. **Guard: exit early if chronicles dir doesn't exist** — `[ -d "$CHRONICLES_DIR" ] || exit 0`. Same guard as gold-context.sh. Plugin is a no-op in projects without a chronicles directory.
2. Check `uvx` is available; if not, print error to stderr and exit 1
3. If `transcript_path` is present and file exists → `chronicles ingest "$TRANSCRIPT_PATH" --chronicles-dir "$CHRONICLES_DIR"`
4. Else → `chronicles ingest --since 1d --chronicles-dir "$CHRONICLES_DIR"` (Copilot CLI fallback)

**uvx command:**
```bash
uvx --from "git+https://github.com/AndurilCode/chronicles" \
    chronicles ingest "$TRANSCRIPT_PATH" --chronicles-dir "$CHRONICLES_DIR"
```

## Known limitations

1. **Copilot CLI sessionStart context injection from plugin hooks** may not work due to `_startupPrompts` only being extracted from project/user-level hooks. Users may need to copy the hook to `.github/hooks/hooks.json` manually.
2. **`uvx` must be installed** on the user's system. The plugin does not auto-install it.
3. **GOLD.md output is capped at 10K chars** by Claude Code. Large GOLD.md files will be truncated (content saved to a file with path reference instead).

## Update to existing docs

After creating the plugin, update the hook docs (`docs/hooks/claude-code.md`, `docs/hooks/copilot-cli.md`, `docs/hooks/copilot-vscode.md`) to mention the plugin as the recommended install method, keeping manual setup as an alternative.
