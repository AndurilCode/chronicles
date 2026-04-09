#!/bin/bash
# SessionStart hook — inject active signals as context
set -euo pipefail

INPUT=$(cat)

CWD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('cwd', ''))
except Exception:
    print('')
" 2>/dev/null)

DIR="${CHRONICLES_DIR:-chronicles}"
CHRONICLES_DIR="${CWD}/${DIR}"

SIGNALS_PATH="${CHRONICLES_DIR}/SIGNALS.md"

# Only inject if SIGNALS.md exists and has active content
if [ ! -f "$SIGNALS_PATH" ]; then
    exit 0
fi

# Extract Active section only
ACTIVE=$(python3 -c "
import sys
content = open('$SIGNALS_PATH').read()
if '## Active' not in content:
    sys.exit(0)
active = content.split('## Active')[1]
if '## Demoted' in active:
    active = active.split('## Demoted')[0]
active = active.strip()
if active:
    print(active)
" 2>/dev/null)

if [ -z "$ACTIVE" ]; then
    exit 0
fi

CONTEXT="Agentic operational signals from past sessions — follow these rules when using tools:
${ACTIVE}"

python3 -c "
import json, os, sys
context = sys.stdin.read()
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
else:
    print(json.dumps({'additionalContext': context}))
" <<< "$CONTEXT"
