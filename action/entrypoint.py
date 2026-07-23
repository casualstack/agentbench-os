#!/usr/bin/env python3
"""GitHub Action entrypoint: run agentbench gate and emit a JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentbench.eval.gate.evaluator import Evaluator


def run_gate(
    tasks: Path,
    trajectory: Path,
    report: Path | None,
    *,
    manifest: Path | None = None,
) -> int:
    """Run gate over all tasks and optionally write a JSON report."""
    evaluator = Evaluator()
    task_files = None
    if manifest is not None:
        from agentbench.eval.gate.manifest import load_task_manifest

        task_files = load_task_manifest(manifest)

    results = evaluator.evaluate_directory(tasks, trajectory, task_files=task_files)

    if not results:
        print(f"No task JSON files found in {tasks}", file=sys.stderr)
        return 1

    failed = sum(1 for result in results if not result.passed)
    passed = len(results) - failed

    for result in results:
        print(result.summary())
        print()

    print(f"Gate summary: {passed}/{len(results)} tasks passed")

    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "passed": failed == 0,
            "tasks_total": len(results),
            "tasks_passed": passed,
            "tasks_failed": failed,
            "tasks": [
                {
                    "task_id": result.task_id,
                    "passed": result.passed,
                    "oracle_results": [
                        {
                            "oracle_type": oracle.oracle_type,
                            "passed": oracle.passed,
                            "message": oracle.message,
                        }
                        for oracle in result.oracle_results
                    ],
                }
                for result in results
            ],
        }
        report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote report to {report}")

    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentBench gate entrypoint")
    parser.add_argument("--tasks", type=Path, required=True, help="Directory of task JSON files")
    parser.add_argument("--trajectory", type=Path, required=True, help="Agent trajectory JSON")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional manifest JSON listing compatible task_files",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to write gate results JSON",
    )
    args = parser.parse_args(argv)
    return run_gate(args.tasks, args.trajectory, args.report, manifest=args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
