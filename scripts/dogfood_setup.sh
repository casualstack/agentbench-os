#!/usr/bin/env bash
# Copy an AgentBench gate workflow into a target repository.
#
# Usage:
#   ./scripts/dogfood_setup.sh /path/to/target-repo [python|infra-k8s]
#
# Creates:
#   .github/workflows/agentbench-gate.yml
#   .agentbench/.gitkeep
#   .agentbench/tasks/.gitkeep  (optional starter tasks dir)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TARGET_REPO="${1:-}"
TEMPLATE="${2:-python}"

usage() {
  echo "Usage: $0 <target-repo-path> [python|infra-k8s]" >&2
  exit 1
}

if [[ -z "${TARGET_REPO}" ]]; then
  usage
fi

if [[ ! -d "${TARGET_REPO}" ]]; then
  echo "Error: target repo not found: ${TARGET_REPO}" >&2
  exit 1
fi

case "${TEMPLATE}" in
  python)
    SRC="${REPO_ROOT}/examples/dogfood/generic-python-repo-workflow.yml"
    ;;
  infra-k8s)
    SRC="${REPO_ROOT}/examples/dogfood/infra-k8s-workflow.yml"
    ;;
  *)
    echo "Error: unknown template '${TEMPLATE}'. Use python or infra-k8s." >&2
    exit 1
    ;;
esac

if [[ ! -f "${SRC}" ]]; then
  echo "Error: template not found: ${SRC}" >&2
  exit 1
fi

DEST_DIR="${TARGET_REPO}/.github/workflows"
DEST_FILE="${DEST_DIR}/agentbench-gate.yml"
AGENTBENCH_DIR="${TARGET_REPO}/.agentbench"
TASKS_DIR="${AGENTBENCH_DIR}/tasks"

mkdir -p "${DEST_DIR}" "${TASKS_DIR}"
cp "${SRC}" "${DEST_FILE}"
touch "${AGENTBENCH_DIR}/.gitkeep" "${TASKS_DIR}/.gitkeep"

cat <<EOF
AgentBench gate workflow installed.

  Workflow: ${DEST_FILE}
  Trajectory dir: ${AGENTBENCH_DIR}/
  Tasks dir: ${TASKS_DIR}/

Next steps:
  1. Add .agentbench/last-run.json (recorded agent trajectory)
  2. Optionally copy task JSON from ${REPO_ROOT}/tasks/ into ${TASKS_DIR}/
  3. Commit and open a PR — see docs/GITHUB_ACTION.md
EOF
