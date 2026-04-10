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

# Extract Steers + Active sections (skip Demoted)
SIGNALS=$(python3 -c "
import sys
content = open('$SIGNALS_PATH').read()
parts = []
for section in ('## Steers', '## Active'):
    if section not in content:
        continue
    text = content.split(section)[1]
    if '## ' in text:
        text = text.split('## ', 1)[0]
    text = text.strip()
    if text:
        parts.append(text)
if parts:
    print('\n'.join(parts))
" 2>/dev/null)

if [ -z "$SIGNALS" ]; then
    exit 0
fi

CONTEXT="Operational signals from past sessions — follow these rules:
${SIGNALS}"

python3 -c "
import json, os, sys
context = sys.stdin.read()
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
else:
    print(json.dumps({'additionalContext': context}))
" <<< "$CONTEXT"

