"""Queryable incident backlog layered on top of the audit trail.

Every alert becomes exactly one incident -- 1:1, no cross-alert dedup or
grouping (noted as future work, see docs/ACCOUNTABILITY.md). Incidents
live in their own ``incidents`` table in the same ``audit.db`` file as
the hash-chained ``events`` table, but are deliberately NOT part of the
chain: status/note/resolution are meant to be mutated as someone works
through the backlog, and mutability after the fact is exactly what the
chain exists to catch on the ``events`` side.

``IncidentStore`` earns "a queryable backlog with disposition, not just a
scrolling terminal stream" -- it does not earn assignment, SLAs, or
grouping; those are explicitly out of scope for Phase 1.
"""

from __future__ import annotations

import getpass
import hashlib
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentbench.accountability.audit.store import EVENTS_SCHEMA, default_db_path
from agentbench.accountability.rules import is_within

OPEN = "open"
ACKNOWLEDGED = "acknowledged"
RESOLVED = "resolved"
STATUSES = (OPEN, ACKNOWLEDGED, RESOLVED)

_INCIDENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    event_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    note TEXT,
    resolved_at TEXT,
    resolved_by TEXT,
    FOREIGN KEY (event_id) REFERENCES events(id)
)
"""


def incident_id_for(session_id: str, step_index: int, rule: str) -> str:
    """Stable id for one alert: the same alert always maps to the same incident.

    Same signature across repeated ``watch`` runs over the same session
    history, so re-observing an alert doesn't create a duplicate incident
    even though the (append-only, never-deduped) events table gets a new
    row each time.
    """
    digest = hashlib.sha256(f"{session_id}:{step_index}:{rule}".encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass
class Incident:
    """One alert plus its human disposition."""

    incident_id: str
    event_id: int
    status: str
    note: str | None
    resolved_at: str | None
    resolved_by: str | None
    # Denormalized from the linked event (via JOIN) so callers get the
    # full picture in one query.
    ts: str
    agent: str
    session_id: str
    cwd: str | None
    model: str | None
    step_index: int
    rule: str
    severity: str
    title: str
    detail: str
    path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "event_id": self.event_id,
            "status": self.status,
            "note": self.note,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "ts": self.ts,
            "agent": self.agent,
            "session_id": self.session_id,
            "cwd": self.cwd,
            "model": self.model,
            "step_index": self.step_index,
            "rule": self.rule,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "path": self.path,
        }


_SELECT = (
    "SELECT incidents.incident_id, incidents.event_id, incidents.status, "
    "incidents.note, incidents.resolved_at, incidents.resolved_by, "
    "events.ts, events.agent, events.session_id, events.cwd, events.model, "
    "events.step_index, events.rule, events.severity, events.title, "
    "events.detail, events.path "
    "FROM incidents JOIN events ON incidents.event_id = events.id"
)


def _row_to_incident(row: sqlite3.Row) -> Incident:
    return Incident(
        incident_id=row["incident_id"],
        event_id=row["event_id"],
        status=row["status"],
        note=row["note"],
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
        ts=row["ts"],
        agent=row["agent"],
        session_id=row["session_id"],
        cwd=row["cwd"],
        model=row["model"],
        step_index=row["step_index"],
        rule=row["rule"],
        severity=row["severity"],
        title=row["title"],
        detail=row["detail"],
        path=row["path"],
    )


class IncidentStore:
    """1:1 alert -> incident backlog with open/acknowledged/resolved status."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.path = Path(db_path) if db_path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # Ensure both tables exist regardless of whether AuditStore has
        # touched this file yet -- incidents references events by FK.
        self._conn.execute(EVENTS_SCHEMA)
        self._conn.execute(_INCIDENTS_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> IncidentStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def sync(self) -> int:
        """Create incidents for any chained events that don't have one yet.

        Called automatically by list()/get() so the backlog is always
        current without a separate sync step in the watch poll loop.
        incident_id_for() is deterministic over (session_id, step_index,
        rule), so re-syncing an alert that's been observed again in a new
        events row is a harmless no-op (INSERT OR IGNORE on the existing
        incident_id). Returns how many new incidents were created.
        """
        with self._lock:
            missing = self._conn.execute(
                "SELECT id, session_id, step_index, rule FROM events "
                "WHERE id NOT IN (SELECT event_id FROM incidents)"
            ).fetchall()
            created = 0
            for row in missing:
                iid = incident_id_for(row["session_id"], row["step_index"], row["rule"])
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO incidents (incident_id, event_id, status) "
                    "VALUES (?, ?, ?)",
                    (iid, row["id"], OPEN),
                )
                if cur.rowcount:
                    created += 1
            self._conn.commit()
        return created

    def list(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        project: str | None = None,
        since: str | None = None,
    ) -> list[Incident]:
        self.sync()
        query = _SELECT + " WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            query += " AND incidents.status = ?"
            params.append(status)
        if severity is not None:
            query += " AND events.severity = ?"
            params.append(severity)
        if since is not None:
            query += " AND events.ts >= ?"
            params.append(since)
        query += " ORDER BY events.id ASC"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()

        incidents = [_row_to_incident(row) for row in rows]
        if project is not None:
            incidents = [
                i
                for i in incidents
                if i.cwd and (is_within(i.cwd, project) or is_within(project, i.cwd))
            ]
        return incidents

    def get(self, incident_id: str) -> Incident | None:
        self.sync()
        with self._lock:
            row = self._conn.execute(
                _SELECT + " WHERE incidents.incident_id = ?", (incident_id,)
            ).fetchone()
        return _row_to_incident(row) if row is not None else None

    def acknowledge(self, incident_id: str, *, note: str | None = None) -> Incident | None:
        self.sync()
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET status = ?, note = COALESCE(?, note) "
                "WHERE incident_id = ?",
                (ACKNOWLEDGED, note, incident_id),
            )
            self._conn.commit()
        return self.get(incident_id)

    def resolve(self, incident_id: str, *, note: str | None = None) -> Incident | None:
        self.sync()
        try:
            resolved_by = getpass.getuser()
        except OSError:
            resolved_by = None
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET status = ?, note = COALESCE(?, note), "
                "resolved_at = ?, resolved_by = ? WHERE incident_id = ?",
                (
                    RESOLVED,
                    note,
                    datetime.now(timezone.utc).isoformat(),
                    resolved_by,
                    incident_id,
                ),
            )
            self._conn.commit()
        return self.get(incident_id)
