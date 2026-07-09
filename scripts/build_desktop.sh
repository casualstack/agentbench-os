#!/usr/bin/env bash
# Build the AgentBench desktop client with PyInstaller (macOS/Linux).
# Prereqs: pip install -e ".[app]" pyinstaller
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

python -m PyInstaller --noconfirm --onefile --windowed --name AgentBench \
  --collect-data agentbench --collect-all webview scripts/desktop_entry.py

echo
if [ -d "dist/AgentBench.app" ]; then
  echo "Built: $repo/dist/AgentBench.app"
else
  echo "Built: $repo/dist/AgentBench"
fi
