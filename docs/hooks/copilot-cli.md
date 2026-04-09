# Copilot CLI Hook Setup

Add to `.copilot/config.yml`:

```yaml
hooks:
  sessionEnd:
    - command: |
        chronicles ingest \
          --source copilot-cli \
          --since 1d \
          --chronicles-dir ./chronicles
```

Note: Copilot CLI does not provide `transcript_path` in hook context.
The `--since 1d` flag triggers session discovery, finding the most recent
transcript by matching timestamps.
