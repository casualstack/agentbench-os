#!/usr/bin/env python3
"""PyInstaller entry point for the AgentBench desktop client."""

from __future__ import annotations

import sys
from pathlib import Path

from agentbench.ui.app import run_app

if __name__ == "__main__":
    # Double-clicked exe starts in its install dir — open the user's home
    # instead; projects are switched in-app via Browse.
    root = sys.argv[1] if len(sys.argv) > 1 else Path.home()
    sys.exit(run_app(root))
