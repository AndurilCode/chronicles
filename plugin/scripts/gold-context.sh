#!/bin/bash
# Chronicles plugin — SessionStart hook
# Injects orientation blurb + GOLD.md content as additional context.
set -euo pipefail
source "$(dirname "$0")/_common.sh"

parse_input hook_event_name
resolve_chronicles_dir

GOLD_PATH="${CHRONICLES_DIR}/GOLD.md"

has_gold_content() {
    [ -f "$GOLD_PATH" ] || return 1
    [ -s "$GOLD_PATH" ] || return 1
    grep -q "promoted_count: 0" "$GOLD_PATH" 2>/dev/null && return 1
    return 0
}

CONTEXT="This project uses Chronicles — an automatic knowledge wiki built from agent sessions.
The chronicles wiki is at: ${DIR}/
- GOLD.md: High-confidence validated knowledge. Read this for known conventions, decisions, and traps.
- CHRONICLES.md: Session index with all ingested sessions.
- CONTESTED.md: Articles with conflicting evidence across sessions.
- wiki/articles/: Individual knowledge articles at various confidence levels.
- wiki/categories/: Auto-generated topic clusters."

if has_gold_content; then
    CONTEXT="${CONTEXT}

Validated project knowledge from GOLD.md:
---
$(cat "$GOLD_PATH")"
fi

emit_context "$CONTEXT"
exit 0
