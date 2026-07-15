"""AgentBench CLI — run evals, CI gates, and benchmark matrices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentbench.accountability.diff import build_diff_report
from agentbench.eval.gate.evaluator import Evaluator


def cmd_run(args: argparse.Namespace) -> int:
    evaluator = Evaluator()
    result = evaluator.evaluate_files(args.task, args.trajectory)
    print(result.summary())
    return 0 if result.passed else 1


def cmd_gate(args: argparse.Namespace) -> int:
    evaluator = Evaluator()
    task_files = None
    if args.manifest is not None:
        from agentbench.eval.gate.manifest import load_task_manifest

        task_files = load_task_manifest(args.manifest)

    results = evaluator.evaluate_directory(
        args.tasks,
        args.trajectory,
        task_files=task_files,
    )

    if not results:
        print(f"No task JSON files found in {args.tasks}")
        return 1

    failed = 0
    for result in results:
        print(result.summary())
        print()
        if not result.passed:
            failed += 1

    total = len(results)
    passed = total - failed
    print(f"Gate summary: {passed}/{total} tasks passed")
    return 0 if failed == 0 else 1


def cmd_matrix(args: argparse.Namespace) -> int:
    from agentbench.eval.matrix import MatrixConfig, MatrixRunner, detect_score_drift

    config = MatrixConfig.from_file(args.config)
    if args.tasks is not None:
        config = config.model_copy(update={"tasks_dir": args.tasks})

    runner = MatrixRunner()
    result = runner.run(config)
    print(result.summary())

    drift_report = None
    if config.baseline is not None:
        drift_report = detect_score_drift(
            result,
            config.baseline,
            threshold=config.drift_threshold,
        )
        print()
        print(drift_report.summary())

    if args.output:
        output = str(args.output)
        if output.lower() == "markdown":
            print()
            print(result.to_table(format="markdown"))
        else:
            payload = result.model_dump(mode="json")
            if drift_report is not None:
                payload["drift"] = drift_report.model_dump(mode="json")
            Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"\nWrote matrix results to {args.output}")

    if drift_report is not None and drift_report.drift_detected and args.fail_on_drift:
        return 1
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    from agentbench.ui.server import serve

    return serve(
        args.root,
        tasks_dir=str(args.tasks),
        port=args.port,
        open_browser=not args.no_browser,
    )


def cmd_app(args: argparse.Namespace) -> int:
    from agentbench.ui.app import run_app

    return run_app(args.root, tasks_dir=str(args.tasks))


_SEVERITY_MARK = {"critical": "[!]", "warning": "[~]"}


def _print_watch_events(events: list) -> int:
    """Print alerts in plain English; return count of critical ones."""
    critical = 0
    for event in events:
        for alert in event.alerts:
            if alert.severity == "critical":
                critical += 1
            where = event.cwd or str(event.path)
            mark = _SEVERITY_MARK.get(alert.severity, "[?]")
            print(f"{mark} {alert.title} — {event.agent} session {event.session_id[:8]} in {where}")
            print(f"    {alert.detail}")
    return critical


def cmd_watch(args: argparse.Namespace) -> int:
    import time

    from agentbench.accountability.audit import AuditStore, record_from_alert
    from agentbench.accountability.digest import render_digest
    from agentbench.accountability.notify import backend_available, notify, summarize_alerts
    from agentbench.accountability.watcher import SessionWatcher
    from agentbench.adapters import ADAPTERS

    # Alert copy uses em dashes; legacy Windows consoles default to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    watcher = SessionWatcher(project=args.project, skip_existing=args.live_only)

    detected = watcher.detected_agents()
    if not detected:
        print(
            "No AI coding agents found on this machine yet.\n"
            "AgentBench looks for Claude Code (~/.claude/projects) and Cursor "
            "sessions, and detects Codex and Antigravity."
        )
        return 1

    adapters = {a.client_name: a for a in ADAPTERS}
    names = []
    for agent in detected:
        adapter = adapters.get(agent)
        if adapter is None:
            names.append(agent)
        elif adapter.detect_only:
            names.append(f"{adapter.display_name} (detected — parsing coming soon)")
        else:
            names.append(adapter.display_name)
    print(f"Found: {', '.join(names)}")

    # Default: notify during the continuous loop when a backend is available;
    # --once is the CI/scripting path and stays quiet unless asked otherwise.
    notifications_enabled = args.notify
    if notifications_enabled is None:
        notifications_enabled = not args.once and backend_available()

    # Recorded by default: every alert is appended to the durable, hash-
    # chained audit trail unless the caller explicitly opts out.
    audit_store = None if args.no_audit_log else AuditStore(args.audit_db)

    def _maybe_notify(poll_events: list) -> None:
        if not notifications_enabled:
            return
        summary = summarize_alerts(poll_events)
        if summary is not None:
            notify(*summary)

    def _maybe_log_audit(poll_events: list) -> None:
        # Reviewer amendment: only real alerts are chained -- no
        # heartbeat/session_seen rows, so events with no alerts append
        # nothing here.
        if audit_store is None:
            return
        for event in poll_events:
            if not event.alerts:
                continue
            source_size = source_mtime = None
            try:
                stat = event.path.stat()
                source_size, source_mtime = stat.st_size, stat.st_mtime
            except OSError:
                pass
            for alert in event.alerts:
                record = record_from_alert(
                    agent=event.agent,
                    session_id=event.session_id,
                    cwd=event.cwd,
                    model=event.model,
                    alert=alert,
                    source_path=str(event.path),
                    source_size=source_size,
                    source_mtime=source_mtime,
                )
                try:
                    audit_store.append(record)
                except Exception as exc:  # never let a write failure kill watch
                    print(f"[!] Failed to write audit log entry: {exc}", file=sys.stderr)

    def _maybe_write_digest() -> None:
        if args.digest:
            args.digest.write_text(render_digest(watcher.sessions()), encoding="utf-8")

    try:
        events = watcher.poll()  # first poll covers existing session history
        total_sessions = len(watcher.sessions())
        scope = f" for {args.project}" if args.project else ""
        print(f"Checked {total_sessions} recorded session(s){scope}.")
        critical = _print_watch_events(events)
        if not any(e.alerts for e in events):
            print("No problems found in recorded sessions.")
        _maybe_notify(events)
        _maybe_log_audit(events)

        if args.once:
            _maybe_write_digest()
            return 1 if critical and args.fail_on_alert else 0

        print("\nWatching for new agent activity... (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(args.interval)
                poll_events = watcher.poll()
                critical += _print_watch_events(poll_events)
                _maybe_notify(poll_events)
                _maybe_log_audit(poll_events)
        except KeyboardInterrupt:
            print("\nStopped watching.")
        _maybe_write_digest()
        return 1 if critical and args.fail_on_alert else 0
    finally:
        if audit_store is not None:
            audit_store.close()


def cmd_audit_verify(args: argparse.Namespace) -> int:
    from agentbench.accountability.audit import AuditStore

    store = AuditStore(args.db)
    try:
        broken = store.verify()
    finally:
        store.close()

    if broken is None:
        print(f"OK: audit trail intact ({store.path})")
        return 0

    print(f"BROKEN: audit trail tampered starting at event id={broken} ({store.path})")
    return 1


_INCIDENT_SEVERITY_MARK = {"critical": "[!]", "warning": "[~]"}


def _format_incident_line(incident: Any) -> str:
    mark = _INCIDENT_SEVERITY_MARK.get(incident.severity, "[?]")
    where = incident.cwd or "unknown location"
    return (
        f"{mark} [{incident.status}] {incident.incident_id}  {incident.title} — "
        f"{incident.agent} session {incident.session_id[:8]} in {where}"
    )


def cmd_incidents_list(args: argparse.Namespace) -> int:
    from agentbench.accountability.audit import IncidentStore

    with IncidentStore(args.db) as store:
        incidents = store.list(
            status=args.status,
            severity=args.severity,
            project=str(args.project) if args.project else None,
        )

    if not incidents:
        print("No incidents found.")
        return 0

    for incident in incidents:
        print(_format_incident_line(incident))
    print(f"\n{len(incidents)} incident(s).")
    return 0


def cmd_incidents_show(args: argparse.Namespace) -> int:
    from agentbench.accountability.audit import IncidentStore

    with IncidentStore(args.db) as store:
        incident = store.get(args.incident_id)

    if incident is None:
        print(f"No incident found with id {args.incident_id}")
        return 1

    print(f"Incident {incident.incident_id} [{incident.status}]")
    print(f"  Rule: {incident.rule} ({incident.severity})")
    print(f"  Title: {incident.title}")
    print(f"  Detail: {incident.detail}")
    print(f"  Agent: {incident.agent}  Session: {incident.session_id}")
    print(f"  Project: {incident.cwd or 'unknown'}")
    print(f"  Path: {incident.path or '-'}")
    print(f"  Observed: {incident.ts}")
    if incident.note:
        print(f"  Note: {incident.note}")
    if incident.resolved_at:
        print(f"  Resolved: {incident.resolved_at} by {incident.resolved_by}")
    return 0


def cmd_incidents_ack(args: argparse.Namespace) -> int:
    from agentbench.accountability.audit import IncidentStore

    with IncidentStore(args.db) as store:
        incident = store.acknowledge(args.incident_id, note=args.note)

    if incident is None:
        print(f"No incident found with id {args.incident_id}")
        return 1
    print(f"Acknowledged {incident.incident_id}.")
    return 0


def cmd_incidents_resolve(args: argparse.Namespace) -> int:
    from agentbench.accountability.audit import IncidentStore

    with IncidentStore(args.db) as store:
        incident = store.resolve(args.incident_id, note=args.note)

    if incident is None:
        print(f"No incident found with id {args.incident_id}")
        return 1
    print(f"Resolved {incident.incident_id}.")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    report = build_diff_report(args.baseline, args.candidate)
    markdown = report.to_markdown()
    print(markdown, end="")

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix.lower() == ".json":
            output.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
        else:
            output.write_text(markdown, encoding="utf-8")
        print(f"\nWrote /diff report to {output}")

    if args.fail_on_change and report.changed:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbench",
        description="AgentBench OS — continuous agent reliability CI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a single eval task against a trajectory")
    run_parser.add_argument("--task", required=True, type=Path, help="Path to task JSON")
    run_parser.add_argument(
        "--trajectory", required=True, type=Path, help="Path to trajectory JSON"
    )
    run_parser.set_defaults(func=cmd_run)

    gate_parser = sub.add_parser("gate", help="Run all tasks in a directory as CI gate")
    gate_parser.add_argument("--tasks", required=True, type=Path, help="Directory of task JSONs")
    gate_parser.add_argument(
        "--trajectory", required=True, type=Path, help="Path to trajectory JSON"
    )
    gate_parser.add_argument(
        "--manifest",
        type=Path,
        help="JSON manifest listing task_files compatible with the trajectory",
    )
    gate_parser.set_defaults(func=cmd_gate)

    matrix_parser = sub.add_parser(
        "matrix",
        help="Run a model × prompt benchmark matrix and detect score drift",
    )
    matrix_parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to matrix YAML/JSON config (e.g. benchmarks/matrix.yaml)",
    )
    matrix_parser.add_argument(
        "--tasks",
        type=Path,
        help="Override tasks directory from config",
    )
    matrix_parser.add_argument(
        "--output",
        help="Write JSON results path, or 'markdown' to print a table",
    )
    matrix_parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit 1 when pass rates drift beyond baseline threshold",
    )
    matrix_parser.set_defaults(func=cmd_matrix)

    ui_parser = sub.add_parser(
        "ui",
        help="Launch the local dashboard (gate runner, task browser, recorder)",
    )
    ui_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root the dashboard reads tasks/trajectories from",
    )
    ui_parser.add_argument("--tasks", type=Path, default=Path("tasks"), help="Tasks directory")
    ui_parser.add_argument("--port", type=int, default=8321, help="Port on 127.0.0.1")
    ui_parser.add_argument(
        "--no-browser", action="store_true", help="Do not open a browser tab"
    )
    ui_parser.set_defaults(func=cmd_ui)

    app_parser = sub.add_parser(
        "app",
        help="Launch the desktop client (native window; needs agentbench[app])",
    )
    app_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root to open (switchable in-app)",
    )
    app_parser.add_argument("--tasks", type=Path, default=Path("tasks"), help="Tasks directory")
    app_parser.set_defaults(func=cmd_app)

    watch_parser = sub.add_parser(
        "watch",
        help="Auto-detect agent sessions on this machine and flag risky behavior",
    )
    watch_parser.add_argument(
        "--project",
        type=Path,
        help="Only watch sessions working in this folder (default: all)",
    )
    watch_parser.add_argument(
        "--once",
        action="store_true",
        help="Check recorded sessions and exit instead of watching live",
    )
    watch_parser.add_argument(
        "--live-only",
        action="store_true",
        help="Skip recorded history; only alert on activity from now on",
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between checks while watching (default: 2)",
    )
    watch_parser.add_argument(
        "--fail-on-alert",
        action="store_true",
        help="Exit 1 if any critical alert was raised",
    )
    notify_group = watch_parser.add_mutually_exclusive_group()
    notify_group.add_argument(
        "--notify",
        dest="notify",
        action="store_true",
        default=None,
        help="Send a desktop notification when a poll finds new alerts "
        "(default: on while watching live, if this machine supports it)",
    )
    notify_group.add_argument(
        "--no-notify",
        dest="notify",
        action="store_false",
        help="Never send desktop notifications",
    )
    watch_parser.add_argument(
        "--digest",
        type=Path,
        help="Write a plain-English markdown report of all watched sessions to this path",
    )
    watch_parser.add_argument(
        "--audit-db",
        type=Path,
        help="Path to the audit database (default: ~/.agentbench/audit.db)",
    )
    watch_parser.add_argument(
        "--no-audit-log",
        action="store_true",
        help="Don't record alerts to the durable audit trail (default: recorded)",
    )
    watch_parser.set_defaults(func=cmd_watch)

    audit_parser = sub.add_parser(
        "audit",
        help="Inspect the durable, tamper-evident audit trail",
    )
    audit_sub = audit_parser.add_subparsers(dest="audit_command", required=True)

    audit_verify_parser = audit_sub.add_parser(
        "verify",
        help="Verify the audit trail's hash chain hasn't been tampered with",
    )
    audit_verify_parser.add_argument(
        "--db",
        type=Path,
        help="Path to the audit database (default: ~/.agentbench/audit.db)",
    )
    audit_verify_parser.set_defaults(func=cmd_audit_verify)

    incidents_parser = sub.add_parser(
        "incidents",
        help="Queryable backlog of alert incidents (open/acknowledged/resolved)",
    )
    incidents_sub = incidents_parser.add_subparsers(dest="incidents_command", required=True)

    incidents_list_parser = incidents_sub.add_parser("list", help="List incidents")
    incidents_list_parser.add_argument(
        "--status",
        choices=["open", "acknowledged", "resolved"],
        help="Only show incidents in this status",
    )
    incidents_list_parser.add_argument(
        "--severity",
        choices=["critical", "warning"],
        help="Only show incidents of this severity",
    )
    incidents_list_parser.add_argument(
        "--project",
        type=Path,
        help="Only show incidents from sessions working in this folder",
    )
    incidents_list_parser.add_argument(
        "--db",
        type=Path,
        help="Path to the audit database (default: ~/.agentbench/audit.db)",
    )
    incidents_list_parser.set_defaults(func=cmd_incidents_list)

    incidents_show_parser = incidents_sub.add_parser("show", help="Show one incident in full")
    incidents_show_parser.add_argument("incident_id")
    incidents_show_parser.add_argument(
        "--db",
        type=Path,
        help="Path to the audit database (default: ~/.agentbench/audit.db)",
    )
    incidents_show_parser.set_defaults(func=cmd_incidents_show)

    incidents_ack_parser = incidents_sub.add_parser(
        "ack", help="Acknowledge an incident (seen, not yet resolved)"
    )
    incidents_ack_parser.add_argument("incident_id")
    incidents_ack_parser.add_argument("--note", help="Optional note to attach")
    incidents_ack_parser.add_argument(
        "--db",
        type=Path,
        help="Path to the audit database (default: ~/.agentbench/audit.db)",
    )
    incidents_ack_parser.set_defaults(func=cmd_incidents_ack)

    incidents_resolve_parser = incidents_sub.add_parser("resolve", help="Resolve an incident")
    incidents_resolve_parser.add_argument("incident_id")
    incidents_resolve_parser.add_argument("--note", help="Optional note to attach")
    incidents_resolve_parser.add_argument(
        "--db",
        type=Path,
        help="Path to the audit database (default: ~/.agentbench/audit.db)",
    )
    incidents_resolve_parser.set_defaults(func=cmd_incidents_resolve)

    diff_parser = sub.add_parser(
        "diff",
        help="Compare two trajectories and emit a git-like /diff report",
    )
    diff_parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="Baseline trajectory JSON (usually default branch)",
    )
    diff_parser.add_argument(
        "--candidate",
        required=True,
        type=Path,
        help="Candidate trajectory JSON (usually PR branch)",
    )
    diff_parser.add_argument(
        "--output",
        type=Path,
        help="Optional report path (.md or .json)",
    )
    diff_parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="Exit 1 if the candidate trajectory differs from baseline",
    )
    diff_parser.set_defaults(func=cmd_diff)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
