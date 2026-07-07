#!/usr/bin/env bash
# Wrapper for the AgentBench model matrix CLI.
#
# Usage:
#   ./scripts/run_matrix.sh [--config CONFIG] [--tasks TASKS_DIR] [--output FORMAT]
#
# Defaults:
#   --config  configs/matrix.json
#   --tasks   tasks/
#   --output  markdown
#
# Passes through any extra args to: agentbench matrix

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG="${REPO_ROOT}/configs/matrix.json"
TASKS="${REPO_ROOT}/tasks"
OUTPUT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --tasks)
      TASKS="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--config PATH] [--tasks DIR] [--output markdown|json|csv] [-- extra args...]"
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if ! command -v agentbench >/dev/null 2>&1; then
  if [[ -d "${REPO_ROOT}/src/agentbench" ]]; then
    export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  fi
fi

exec agentbench matrix \
  --config "${CONFIG}" \
  --tasks "${TASKS}" \
  --output "${OUTPUT}" \
  "$@"
