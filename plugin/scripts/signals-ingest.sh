#!/bin/bash
# SessionEnd hook — extract agentic signals from completed session
set -uo pipefail
source "$(dirname "$0")/_common.sh"

guard_recursion
parse_input transcript_path
resolve_chronicles_dir
run_chronicles signals
