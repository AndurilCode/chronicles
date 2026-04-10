#!/bin/bash
# SubagentStop hook — extract agentic signals from completed subagent session
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
    print(json.load(sys.stdin).get('agent_transcript_path', ''))
except Exception:
    print('')
" 2>/dev/null)

DIR="${CHRONICLES_DIR:-chronicles}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Only run if chronicles directory exists and transcript is available
[ -d "$CHRONICLES_DIR" ] || exit 0
[ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] || exit 0

uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
    chronicles signals "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" || true
