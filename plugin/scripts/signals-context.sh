#!/bin/bash
# SessionStart hook — inject active signals as context
set -euo pipefail

INPUT=$(cat)

# Extract cwd and hook event name from input
read -r CWD EVENT_NAME < <(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('cwd', ''), d.get('hook_event_name', 'SessionStart'))
except Exception:
    print(' SessionStart')
" 2>/dev/null)
EVENT_NAME="${EVENT_NAME:-SessionStart}"

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

HOOK_EVENT_NAME="$EVENT_NAME" python3 -c "
import json, os, sys
context = sys.stdin.read()
event = os.environ.get('HOOK_EVENT_NAME', 'SessionStart')
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context}}))
else:
    print(json.dumps({'additionalContext': context}))
" <<< "$CONTEXT"

