# Claude Code Hook Setup

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "chronicles ingest $TRANSCRIPT_PATH --chronicles-dir ./chronicles"
          }
        ]
      }
    ]
  }
}
```
