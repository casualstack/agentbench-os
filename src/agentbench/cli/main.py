"""AgentBench CLI — run evals, CI gates, and benchmark matrices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentbench.matrix import MatrixRunner, detect_score_drift
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
