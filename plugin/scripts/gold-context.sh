#!/bin/bash
# Chronicles plugin — SessionStart hook
# Injects orientation blurb + GOLD.md content as additional context.

set -euo pipefail

# Read stdin JSON
INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)
CWD="${CWD:-.}"

# Resolve chronicles directory
DIR="${CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR:-${CHRONICLES_DIR:-chronicles}}"
CHRONICLES_DIR="${CWD}/${DIR}"

# Guard: only activate in projects with a chronicles directory
[ -d "$CHRONICLES_DIR" ] || exit 0

GOLD_PATH="${CHRONICLES_DIR}/GOLD.md"

# Check if GOLD.md has real content (not just empty frontmatter)
has_gold_content() {
    [ -f "$GOLD_PATH" ] || return 1
    [ -s "$GOLD_PATH" ] || return 1
    if grep -q "promoted_count: 0" "$GOLD_PATH" 2>/dev/null; then
        return 1
    fi
    return 0
}

# Build context string
CONTEXT="This project uses Chronicles — an automatic knowledge wiki built from agent sessions.
The chronicles wiki is at: ${DIR}/
- GOLD.md: High-confidence validated knowledge. Read this for known conventions, decisions, and traps.
- CHRONICLES.md: Session index with all ingested sessions.
- CONTESTED.md: Articles with conflicting evidence across sessions.
- wiki/articles/: Individual knowledge articles at various confidence levels.
- wiki/categories/: Auto-generated topic clusters."

if has_gold_content; then
    GOLD_CONTENT=$(cat "$GOLD_PATH")
    CONTEXT="${CONTEXT}

Validated project knowledge from GOLD.md:
---
${GOLD_CONTENT}"
fi

# Output as structured JSON for the platform
python3 -c "
import json, os, sys
context = sys.stdin.read()
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    # Claude Code format
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
else:
    # Copilot CLI / default format
    print(json.dumps({'additionalContext': context}))
" <<< "$CONTEXT"

exit 0
