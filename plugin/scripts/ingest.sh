#!/bin/bash
# Chronicles plugin — SessionEnd hook
# Ingests the session transcript into the chronicles wiki via uvx.
set -uo pipefail
source "$(dirname "$0")/_common.sh"

guard_recursion
parse_input transcript_path
resolve_chronicles_dir
run_chronicles ingest

exit 0
