"""Codex CLI adapter: detected-but-not-parsed stub.

TODO(codex-jsonl): Codex CLI writes JSONL rollout/session logs under
``~/.codex/sessions/*.jsonl``. We haven't reverse-engineered that record
format yet, so this stub only reports Codex's presence. Once the format is
known, promote this to a real adapter: implement ``discover``/
``parse_session`` (and ``metadata_from_text``/``steps_from_text`` if it
turns out to be append-only JSONL like Claude Code, in which case flip
``supports_tail`` to True) — ``detect`` should already be correct.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbench.watch.adapters.base import SessionSource, SourceAdapter


class CodexAdapter(SourceAdapter):
    client_name = "codex"
    display_name = "Codex CLI"
    supports_tail = False
    detect_only = True

    def _root(self, home: Path) -> Path:
        return home / ".codex"

    def detect(self, home: Path) -> bool:
        return self._root(home).is_dir()

    def discover(self, home: Path) -> list[SessionSource]:
        return []  # detected only — no parser yet, see module docstring

    def parse_session(self, path: Path) -> dict[str, Any]:
        return {"metadata": {"agent": self.client_name, "source": str(path)}, "steps": []}
