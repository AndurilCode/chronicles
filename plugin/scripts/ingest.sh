#!/bin/bash
# Chronicles plugin — SessionEnd hook
# Ingests the session transcript into the chronicles wiki via uvx.

set -uo pipefail

# Guard against infinite recursion: chronicles ingest calls `claude --print`,
# which triggers SessionEnd, which would call ingest again.
if [ "${CHRONICLES_RUNNING:-}" = "1" ]; then
    exit 0
fi
export CHRONICLES_RUNNING=1

# Read stdin JSON
INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)
TRANSCRIPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || true)
CWD="${CWD:-.}"

# Resolve chronicles directory
DIR="${CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR:-${CHRONICLES_DIR:-chronicles}}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Guard: only activate in projects with a chronicles directory
if [ ! -d "$CHRONICLES_DIR" ]; then
    echo "chronicles: skipping ingest — $CHRONICLES_DIR not found" >&2
    exit 0
fi

# Check uvx is available
if ! command -v uvx &>/dev/null; then
    echo "chronicles: uvx not found. Install uv (https://docs.astral.sh/uv/) to use the chronicles plugin." >&2
    exit 0
fi

# Ingest (always exit 0 — never block the session on ingestion failure)
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    # Claude Code / Copilot VS Code: transcript_path provided
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles ingest "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" || true
else
    # Copilot CLI: discover the most recent session
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles ingest --since 1d --last 1 --chronicles-dir "$CHRONICLES_DIR" || true
fi

exit 0
