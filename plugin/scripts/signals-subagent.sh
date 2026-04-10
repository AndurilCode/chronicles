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

DIR="${CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR:-${CHRONICLES_DIR:-chronicles}}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Only run if chronicles directory exists and transcript is available
if [ ! -d "$CHRONICLES_DIR" ]; then
    echo "chronicles: skipping subagent signals — $CHRONICLES_DIR not found" >&2
    exit 0
fi
if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
    echo "chronicles: skipping subagent signals — no transcript at '$TRANSCRIPT'" >&2
    exit 0
fi

# Check if subagent extraction is enabled in config
ENABLED=$(python3 -c "
import yaml, sys
try:
    cfg = yaml.safe_load(open('${CHRONICLES_DIR}/config.yaml'))
    print(cfg.get('signals', {}).get('subagents', True))
except Exception:
    print('True')
" 2>/dev/null)
[ "$ENABLED" = "False" ] && exit 0

uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
    chronicles signals "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" || true
