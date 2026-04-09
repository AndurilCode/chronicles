# Copilot VS Code Hook Setup

> **Note:** VS Code Copilot hooks are currently in **Preview**.

Hooks are configured in `.vscode/hooks.json` in the workspace:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "./scripts/chronicles-hook.sh",
        "osx": "./scripts/chronicles-hook.sh",
        "windows": "powershell -File scripts/chronicles-hook.ps1",
        "timeout": 600
      }
    ]
  }
}
```

Wrapper script (`scripts/chronicles-hook.sh`):

```bash
#!/bin/bash
TRANSCRIPT_PATH=$(cat /dev/stdin | python3 -c 'import sys,json; print(json.load(sys.stdin)["transcript_path"])')
chronicles ingest "$TRANSCRIPT_PATH" --chronicles-dir ./chronicles
```

## Hook input

The hook receives JSON on stdin:

```json
{
  "timestamp": 1704618000000,
  "cwd": "/path/to/project",
  "sessionId": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "hookEventName": "Stop"
}
```

## Notes

- VS Code Copilot **does** provide `transcript_path` — no discovery needed
- Uses `Stop` event (no separate `SessionEnd`)
- Supports platform-specific commands via `osx`, `linux`, `windows` fields
- This feature is in Preview and may change
