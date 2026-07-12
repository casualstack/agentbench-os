#!/usr/bin/env bash
# Build the AgentBench desktop client with PyInstaller (macOS/Linux).
# Prereqs: pip install -e ".[app]" pyinstaller
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

# AgentBench.spec is the single source of truth for PyInstaller options
# (icon, version resource, one-dir layout, upx) — CI builds the same way.
python -m PyInstaller --noconfirm AgentBench.spec

echo
if [ -d "dist/AgentBench.app" ]; then
  echo "Built: $repo/dist/AgentBench.app"
else
  echo "Built: $repo/dist/AgentBench/AgentBench"
fi
