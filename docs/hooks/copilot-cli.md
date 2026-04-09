# Copilot CLI Hook Setup

## Recommended: Plugin install

```bash
copilot plugin install AndurilCode/chronicles:plugin
```

This auto-installs both `sessionStart` (GOLD.md context injection) and `sessionEnd` (transcript ingestion) hooks. The plugin is safe to install globally — it only activates in projects that have a `chronicles/` directory.

Requires `uvx` ([install uv](https://docs.astral.sh/uv/)).

> **Note:** Context injection from plugin-sourced `sessionStart` hooks may have limitations. If GOLD.md is not injected, copy the hook config to `.github/hooks/hooks.json` manually (see below).

## Manual setup

Copilot CLI hooks are configured in `.github/hooks/hooks.json`.

```json
{
  "version": 1,
  "hooks": {
    "sessionEnd": [
      {
        "type": "command",
        "bash": "./scripts/chronicles-hook.sh",
        "timeoutSec": 600
      }
    ]
  }
}
```

Wrapper script (`scripts/chronicles-hook.sh`):

```bash
#!/bin/bash
chronicles ingest \
  --source copilot-cli \
  --since 1d \
  --chronicles-dir ./chronicles
```

## Hook input

The hook receives JSON on stdin:

```json
{
  "timestamp": 1704618000000,
  "cwd": "/path/to/project",
  "reason": "complete"
}
```

`reason` is one of: `complete`, `error`, `abort`, `timeout`, `user_exit`.

## Notes

- Copilot CLI does **not** provide `transcript_path` in the hook input
- The `--since 1d` flag triggers session discovery, finding the most recent transcript by matching timestamps
- Hook config uses `bash` / `powershell` fields for platform-specific commands (not `command`)
