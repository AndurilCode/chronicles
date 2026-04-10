#!/bin/bash
# SessionEnd hook — extract agentic signals from completed session
set -uo pipefail

INPUT=$(cat)

CWD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('cwd', ''))
except Exception:
    print('')
" 2>/dev/null)

TRANSCRIPT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('transcript_path', ''))
except Exception:
    print('')
" 2>/dev/null)

DIR="${CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR:-${CHRONICLES_DIR:-chronicles}}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Only run if chronicles directory exists
if [ ! -d "$CHRONICLES_DIR" ]; then
    echo "chronicles: skipping signals — $CHRONICLES_DIR not found" >&2
    exit 0
fi

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles signals "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" || true
else
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles signals --since 1d --last 1 --chronicles-dir "$CHRONICLES_DIR" || true
fi
