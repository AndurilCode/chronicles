#!/bin/bash
# Chronicles plugin — shared helpers for hook scripts.

# --- Recursion guard ---
# Call from SessionEnd/SubagentStop hooks to prevent infinite loops
# when chronicles itself spawns `claude --print`.
guard_recursion() {
    if [ "${CHRONICLES_RUNNING:-}" = "1" ]; then
        exit 0
    fi
    export CHRONICLES_RUNNING=1
}

# --- Parse stdin JSON ---
# Reads stdin once and exports requested fields.
# Usage: parse_input cwd transcript_path hook_event_name
#   -> sets CWD, TRANSCRIPT, EVENT_NAME
parse_input() {
    _INPUT=$(cat)
    CWD=$(echo "$_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)
    CWD="${CWD:-.}"

    # Optional fields — only set if the caller asked for them
    for field in "$@"; do
        case "$field" in
            transcript_path)
                TRANSCRIPT=$(echo "$_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || true)
                ;;
            agent_transcript_path)
                TRANSCRIPT=$(echo "$_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('agent_transcript_path',''))" 2>/dev/null || true)
                ;;
            hook_event_name)
                EVENT_NAME=$(echo "$_INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hook_event_name','SessionStart'))" 2>/dev/null || true)
                EVENT_NAME="${EVENT_NAME:-SessionStart}"
                ;;
        esac
    done
}

# --- Resolve and guard chronicles directory ---
# Sets CHRONICLES_DIR and exits 0 if the directory doesn't exist.
resolve_chronicles_dir() {
    local rel="${CLAUDE_PLUGIN_OPTION_CHRONICLES_DIR:-${CHRONICLES_DIR:-chronicles}}"
    CHRONICLES_DIR="${CWD}/${rel}"
    DIR="$rel"
    if [ ! -d "$CHRONICLES_DIR" ]; then
        echo "chronicles: skipping — $CHRONICLES_DIR not found" >&2
        exit 0
    fi
}

# --- Require uvx ---
require_uvx() {
    if ! command -v uvx &>/dev/null; then
        echo "chronicles: uvx not found. Install uv (https://docs.astral.sh/uv/) to use the chronicles plugin." >&2
        exit 0
    fi
}

# --- Run a chronicles subcommand via uvx ---
# Usage: run_chronicles <subcommand> [extra-args...]
# Automatically handles transcript vs discovery mode.
run_chronicles() {
    local subcmd="$1"; shift
    require_uvx
    if [ -n "${TRANSCRIPT:-}" ] && [ -f "${TRANSCRIPT:-}" ]; then
        uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
            chronicles "$subcmd" "$TRANSCRIPT" --chronicles-dir "$CHRONICLES_DIR" "$@" || true
    else
        uvx --from "git+https://github.com/AndurilCode/chronicles[tfidf]" \
            chronicles "$subcmd" --since 1d --last 1 --chronicles-dir "$CHRONICLES_DIR" "$@" || true
    fi
}

# --- Emit context JSON for SessionStart hooks ---
# Usage: emit_context "context string"
emit_context() {
    local context="$1"
    HOOK_EVENT_NAME="${EVENT_NAME:-SessionStart}" python3 -c "
import json, os, sys
context = sys.stdin.read()
event = os.environ.get('HOOK_EVENT_NAME', 'SessionStart')
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context}}))
else:
    print(json.dumps({'additionalContext': context}))
" <<< "$context"
}
