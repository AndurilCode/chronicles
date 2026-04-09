# Claude Code Hook Setup

Use the `SessionEnd` event — it fires once when the session terminates and provides `transcript_path` via stdin JSON.

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "type": "command",
        "command": "chronicles ingest \"$(cat /dev/stdin | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"transcript_path\"])')\" --chronicles-dir ./chronicles",
        "timeout": 600
      }
    ]
  }
}
```

Alternatively, use a wrapper script for readability:

```bash
#!/bin/bash
# scripts/chronicles-hook.sh
TRANSCRIPT_PATH=$(cat /dev/stdin | python3 -c 'import sys,json; print(json.load(sys.stdin)["transcript_path"])')
chronicles ingest "$TRANSCRIPT_PATH" --chronicles-dir ./chronicles
```

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "type": "command",
        "command": "./scripts/chronicles-hook.sh",
        "timeout": 600
      }
    ]
  }
}
```

## Hook input

The hook receives JSON on stdin:

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "cwd": "/Users/.../project",
  "hook_event_name": "SessionEnd"
}
```

## Notes

- `SessionEnd` fires once at termination (cannot block the session)
- `Stop` fires per-response — use `SessionEnd` for chronicles to avoid duplicate ingestion
- `transcript_path` is provided directly — no discovery needed
