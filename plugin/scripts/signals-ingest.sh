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

DIR="${CHRONICLES_DIR:-chronicles}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Only run if chronicles directory exists
[ -d "$CHRONICLES_DIR" ] || exit 0

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles signals "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" || true
else
    uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
        chronicles signals --since 1d --last 1 --chronicles-dir "$CHRONICLES_DIR" || true
fi
