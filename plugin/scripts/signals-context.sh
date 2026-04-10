#!/bin/bash
# SessionStart hook — inject active signals as context
set -euo pipefail
source "$(dirname "$0")/_common.sh"

parse_input hook_event_name
resolve_chronicles_dir

SIGNALS_PATH="${CHRONICLES_DIR}/SIGNALS.md"
[ -f "$SIGNALS_PATH" ] || exit 0

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

[ -z "$SIGNALS" ] && exit 0

emit_context "Operational signals from past sessions — follow these rules:
${SIGNALS}"
