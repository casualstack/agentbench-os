"""AgentBench CLI — run evals, CI gates, and benchmark matrices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentbench.diff_report import build_diff_report
from agentbench.gate.evaluator import Evaluator


def cmd_run(args: argparse.Namespace) -> int:
    evaluator = Evaluator()
    result = evaluator.evaluate_files(args.task, args.trajectory)
    print(result.summary())
    return 0 if result.passed else 1


def cmd_gate(args: argparse.Namespace) -> int:
    evaluator = Evaluator()
    task_files = None
    if args.manifest is not None:
        from agentbench.gate.manifest import load_task_manifest

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
    from agentbench.matrix import MatrixConfig, MatrixRunner, detect_score_drift

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

    from agentbench.watch.adapters import ADAPTERS
    from agentbench.watch.digest import render_digest
    from agentbench.watch.notify import backend_available, notify, summarize_alerts
    from agentbench.watch.watcher import SessionWatcher

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

    def _maybe_notify(poll_events: list) -> None:
        if not notifications_enabled:
            return
        summary = summarize_alerts(poll_events)
        if summary is not None:
            notify(*summary)

    def _maybe_write_digest() -> None:
        if args.digest:
            args.digest.write_text(render_digest(watcher.sessions()), encoding="utf-8")

    events = watcher.poll()  # first poll covers existing session history
    total_sessions = len(watcher.sessions())
    scope = f" for {args.project}" if args.project else ""
    print(f"Checked {total_sessions} recorded session(s){scope}.")
    critical = _print_watch_events(events)
    if not any(e.alerts for e in events):
        print("No problems found in recorded sessions.")
    _maybe_notify(events)

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
    except KeyboardInterrupt:
        print("\nStopped watching.")
    _maybe_write_digest()
    return 1 if critical and args.fail_on_alert else 0


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
    watch_parser.set_defaults(func=cmd_watch)

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
