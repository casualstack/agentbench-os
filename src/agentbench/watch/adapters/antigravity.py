"""Antigravity adapter: detected-but-not-parsed stub.

TODO(antigravity-format): Antigravity's session-log location and format are
not publicly documented as of this writing. The directories checked below
are a best guess by analogy with other editor-based agents (Cursor keeps
per-workspace state under ``.../User/...``); confirm and correct once the
real layout is known, then implement ``discover``/``parse_session`` for
real (and the tailing hooks too, if it turns out to be JSONL).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbench.watch.adapters.base import SessionSource, SourceAdapter


class AntigravityAdapter(SourceAdapter):
    client_name = "antigravity"
    display_name = "Antigravity"
    supports_tail = False
    detect_only = True

    def _roots(self, home: Path) -> list[Path]:
        # Derived from `home` rather than the real %APPDATA% env var, so a
        # fake `home` (tests) gets full isolation. See CursorAdapter.
        return [
            home / ".antigravity",  # linux/mac CLI-style state (guess)
            home / "Library" / "Application Support" / "Antigravity",  # macOS (guess)
            home / ".config" / "Antigravity",  # linux (guess)
            home / "AppData" / "Roaming" / "Antigravity",  # Windows (guess)
        ]

    def detect(self, home: Path) -> bool:
        return any(root.is_dir() for root in self._roots(home))

    def discover(self, home: Path) -> list[SessionSource]:
        return []  # detected only — no parser yet, see module docstring

    def parse_session(self, path: Path) -> dict[str, Any]:
        return {"metadata": {"agent": self.client_name, "source": str(path)}, "steps": []}
