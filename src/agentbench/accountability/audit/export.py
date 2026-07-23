"""Durable, historical equivalent of ``watch --digest``.

``watch --digest`` renders whatever ``SessionWatcher`` has seen in memory
during the current run. ``agentbench audit export`` renders the same
markdown shape from what's actually persisted in the audit trail --
regroups a flat incident list back into the ``{"agent":..., "alerts":
[...]}`` session shape ``digest.py`` already knows how to render, so the
rendering logic itself isn't duplicated.
"""

from __future__ import annotations

from typing import Any

from agentbench.accountability.audit.incidents import Incident


def sessions_from_incidents(incidents: list[Incident]) -> list[dict[str, Any]]:
    """Group a flat incident list back into per-session dicts for render_digest().

    Each alert dict carries a "status" key (open/acknowledged/resolved)
    that live watch alerts never have -- digest.py renders it when present.
    No "steps" key: there's no live step count to report from history, so
    digest.py omits that line rather than showing a misleading 0.
    """
    by_session: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []

    for incident in incidents:
        key = (incident.agent, incident.session_id)
        if key not in by_session:
            by_session[key] = {
                "agent": incident.agent,
                "session_id": incident.session_id,
                "cwd": incident.cwd,
                "model": incident.model,
                "alerts": [],
            }
            order.append(key)
        by_session[key]["alerts"].append(
            {
                "rule": incident.rule,
                "severity": incident.severity,
                "title": incident.title,
                "detail": incident.detail,
                "step_index": incident.step_index,
                "path": incident.path,
                "status": incident.status,
            }
        )

    return [by_session[key] for key in order]
