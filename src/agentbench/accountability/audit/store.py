"""Durable, hash-chained storage for the alerts AgentBench raises.

One append-only ``events`` table. Every row's ``record_hash`` commits to
its own content plus the previous row's hash (see ``audit/chain.py``), so
``verify()`` can prove the stored history hasn't been silently edited
since it was written. See the module docstring on ``chain.py`` for exactly
what that claim does and doesn't cover.

Default path is the global ``~/.agentbench/audit.db`` (reviewer ruling:
one machine-wide audit trail, not one per project) -- pass ``db_path`` to
point at a different file, which is how tests and ``--audit-db`` stay
isolated from the real one.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from agentbench.accountability.audit.chain import GENESIS, compute_hash, verify_chain
from agentbench.accountability.rules import is_within

if TYPE_CHECKING:
    from agentbench.accountability.rules import Alert

def default_db_path() -> Path:
    """The global audit trail path, resolved fresh on every call.

    Deliberately a function rather than a module-level constant: computing
    ``Path.home()`` once at import time would freeze the wrong value if
    something (a test, ``HOME``/``USERPROFILE`` set differently, etc.)
    changes home afterward.
    """
    return Path.home() / ".agentbench" / "audit.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent TEXT NOT NULL,
    session_id TEXT NOT NULL,
    cwd TEXT,
    model TEXT,
    step_index INTEGER,
    rule TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    path TEXT,
    source_path TEXT,
    source_size INTEGER,
    source_mtime REAL,
    record_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL
)
"""

# Columns as stored, in insert order (id/record_hash/prev_hash are
# computed by append(), not supplied by the caller).
_RECORD_FIELDS = (
    "ts",
    "agent",
    "session_id",
    "cwd",
    "model",
    "step_index",
    "rule",
    "severity",
    "title",
    "detail",
    "path",
    "source_path",
    "source_size",
    "source_mtime",
)


class AuditStore:
    """Append-only, hash-chained record of alerts AgentBench has raised."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.path = Path(db_path) if db_path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> AuditStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def append(self, record: dict[str, Any]) -> int:
        """Append one event; returns its assigned id.

        ``record`` carries the event's content fields (ts, agent,
        session_id, ..., source_mtime) -- id, record_hash, and prev_hash
        are computed here, under a write lock, in a single INSERT. Cheap
        enough to call fire-and-forget from a hot polling loop (task 6);
        never call this from anywhere latency-sensitive like a future
        hook-based interception path.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                last = self._conn.execute(
                    "SELECT id, record_hash FROM events ORDER BY id DESC LIMIT 1"
                ).fetchone()
                next_id = (last["id"] + 1) if last is not None else 1
                prev_hash = last["record_hash"] if last is not None else GENESIS

                full = {**record, "id": next_id}
                record_hash = compute_hash(full, prev_hash)

                self._conn.execute(
                    "INSERT INTO events "
                    "(id, ts, agent, session_id, cwd, model, step_index, "
                    "rule, severity, title, detail, path, "
                    "source_path, source_size, source_mtime, "
                    "record_hash, prev_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        next_id,
                        *(record.get(field) for field in _RECORD_FIELDS),
                        record_hash,
                        prev_hash,
                    ),
                )
                self._conn.commit()
                return next_id
            except BaseException:
                self._conn.rollback()
                raise

    def iter_events(
        self,
        *,
        agent: str | None = None,
        session_id: str | None = None,
        severity: str | None = None,
        project: str | None = None,
        since: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield stored events in id order, optionally filtered.

        ``project`` matches sessions whose recorded cwd is under (or
        contains) the given path -- same semantics as `watch --project`
        (``accountability.rules.is_within``), not exact string equality.
        """
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []
        if agent is not None:
            query += " AND agent = ?"
            params.append(agent)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if severity is not None:
            query += " AND severity = ?"
            params.append(severity)
        if since is not None:
            query += " AND ts >= ?"
            params.append(since)
        query += " ORDER BY id ASC"

        with self._lock:
            rows = [dict(row) for row in self._conn.execute(query, params).fetchall()]

        for row in rows:
            if project is not None:
                cwd = row.get("cwd")
                if not cwd or not (is_within(cwd, project) or is_within(project, cwd)):
                    continue
            yield row

    def verify(self) -> int | None:
        """Verify the whole chain; returns the first broken row id, or None."""
        with self._lock:
            rows = [dict(row) for row in self._conn.execute(
                "SELECT * FROM events ORDER BY id ASC"
            ).fetchall()]
        return verify_chain(rows)


def record_from_alert(
    *,
    agent: str,
    session_id: str,
    cwd: str | None,
    model: str | None,
    alert: Alert,
    source_path: str | None = None,
    source_size: int | None = None,
    source_mtime: float | None = None,
) -> dict[str, Any]:
    """Build an ``append()``-ready record from one alert.

    Pulled out into its own function so the watch poll loop (cli/main.py)
    can call it without ``watcher.py`` itself knowing anything about
    SQLite or the audit trail -- ``SessionWatcher.poll()`` returns plain
    ``WatchEvent``/``Alert`` dataclasses and stays storage-agnostic.
    """
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "session_id": session_id,
        "cwd": cwd,
        "model": model,
        "step_index": alert.step_index,
        "rule": alert.rule,
        "severity": alert.severity,
        "title": alert.title,
        "detail": alert.detail,
        "path": alert.path,
        "source_path": source_path,
        "source_size": source_size,
        "source_mtime": source_mtime,
    }
