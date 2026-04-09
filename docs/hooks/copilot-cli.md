# Copilot CLI Hook Setup

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
