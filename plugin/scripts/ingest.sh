#!/bin/bash
# Chronicles plugin — SessionEnd hook
# Ingests the session transcript into the chronicles wiki via uvx.

set -euo pipefail

# Read stdin JSON
INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)
TRANSCRIPT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || true)
CWD="${CWD:-.}"

# Resolve chronicles directory
DIR="${CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR:-${CHRONICLES_DIR:-chronicles}}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Guard: only activate in projects with a chronicles directory
[ -d "$CHRONICLES_DIR" ] || exit 0

# Check uvx is available
if ! command -v uvx &>/dev/null; then
    echo "chronicles: uvx not found. Install uv (https://docs.astral.sh/uv/) to use the chronicles plugin." >&2
    exit 1
fi

# Ingest
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    # Claude Code / Copilot VS Code: transcript_path provided
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles ingest "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR"
else
    # Copilot CLI: discover the most recent session
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles ingest --since 1d --last 1 --chronicles-dir "$CHRONICLES_DIR"
fi
