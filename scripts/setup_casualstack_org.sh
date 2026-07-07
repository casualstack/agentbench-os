#!/usr/bin/env bash
# Create the Casualstack GitHub org and push the org profile repo (casualstack/.github).
#
# Does NOT create or push product repos (agentbench-os, witness, k8sattest).
#
# Usage:
#   ./scripts/setup_casualstack_org.sh
#   ./scripts/setup_casualstack_org.sh /path/to/casualstack-github-org

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE_REPO_PATH="${1:-$(cd "${REPO_ROOT}/.." && pwd)/casualstack-github-org}"

ORG_NAME="casualstack"
ORG_DESCRIPTION="Execution accountability for AI agents"
REMOTE_REPO="${ORG_NAME}/.github"

ensure_gh_cli() {
  if command -v gh >/dev/null 2>&1; then
    return 0
  fi

  echo "GitHub CLI (gh) is not installed." >&2
  case "$(uname -s)" in
    Darwin)
      echo "Install with: brew install gh" >&2
      ;;
    Linux)
      echo "Install from: https://cli.github.com/" >&2
      ;;
    *)
      echo "Install from: https://cli.github.com/" >&2
      ;;
  esac
  exit 1
}

ensure_gh_auth() {
  if gh auth status >/dev/null 2>&1; then
    echo "gh auth: OK"
    return 0
  fi

  echo "gh is not authenticated." >&2
  echo "Authenticate with: gh auth login" >&2
  exit 1
}

ensure_org() {
  if gh api "orgs/${ORG_NAME}" >/dev/null 2>&1; then
    echo "Organization '${ORG_NAME}' already exists — skipping creation."
    return 0
  fi

  echo "Creating organization '${ORG_NAME}'..."
  if ! gh org create "${ORG_NAME}" --description "${ORG_DESCRIPTION}"; then
    echo "Failed to create organization '${ORG_NAME}'. The slug may be taken or your account may lack org-creation permissions." >&2
    exit 1
  fi
  echo "Organization '${ORG_NAME}' created."
}

ensure_profile_repo() {
  local local_path="$1"

  if [[ ! -f "${local_path}/profile/README.md" ]]; then
    echo "Profile README not found at ${local_path}/profile/README.md" >&2
    exit 1
  fi

  if [[ ! -d "${local_path}/.git" ]]; then
    echo "Initializing git in ${local_path}..."
  (
    cd "${local_path}"
    git init
    git branch -M main
    git add profile/ CODE_OF_CONDUCT.md SECURITY.md
    if [[ -n "$(git status --porcelain)" ]]; then
      git commit -m "Add Casualstack org profile (coming soon)"
    fi
  )
  fi

  if gh repo view "${REMOTE_REPO}" >/dev/null 2>&1; then
    echo "Remote repo '${REMOTE_REPO}' already exists."
  (
    cd "${local_path}"
    if ! git remote get-url origin >/dev/null 2>&1; then
      git remote add origin "https://github.com/${REMOTE_REPO}.git"
    fi
    git push -u origin main
  )
    return 0
  fi

  echo "Creating and pushing '${REMOTE_REPO}'..."
  (
    cd "${local_path}"
    gh repo create "${REMOTE_REPO}" --public --source=. --remote=origin --push \
      --description "Casualstack organization profile"
  )
}

echo "=== Casualstack GitHub org setup ==="
echo "Profile source: ${PROFILE_REPO_PATH}"
echo ""

ensure_gh_cli
ensure_gh_auth
ensure_org
ensure_profile_repo "${PROFILE_REPO_PATH}"

cat <<EOF

=== Done ===

Org profile:  https://github.com/${ORG_NAME}
Profile repo: https://github.com/${REMOTE_REPO}

Next steps (manual):
  1. Org settings → require 2FA for all members
  2. Org settings → base permissions: No permission (or Read)
  3. Org settings → Actions: allow selected or all (per policy)
  4. See docs/GITHUB_ORG_RUNBOOK.md for branch protection when product repos go public

NOT pushed (by design):
  - casualstack/agentbench-os
  - casualstack/witness
  - casualstack/k8sattest

Remove "coming soon" from profile/README.md before publishing product repos.
EOF
