"""Run oracles against trajectory + workspace snapshot."""

from __future__ import annotations

from pathlib import Path

from agentbench.models.task import EvalTask, RunResult
from agentbench.oracles.base import get_oracle

# Import oracle modules to register them in the registry.
import agentbench.oracles.assertion_exists  # noqa: F401
import agentbench.oracles.file_not_modified  # noqa: F401
import agentbench.oracles.no_network  # noqa: F401
import agentbench.oracles.test_must_pass  # noqa: F401

from agentbench.runner.agent_runner import AgentRunner
from agentbench.core.trajectory import Trajectory


class Evaluator:
    """Evaluate a task against a recorded agent trajectory."""

    def evaluate(
        self,
        task: EvalTask,
        trajectory: Trajectory,
        *,
        keep_workspace: bool = False,
    ) -> RunResult:
        runner = AgentRunner(task, trajectory)
        try:
            workspace = runner.run()
            results = []

            for oracle in task.oracles:
                checker = get_oracle(oracle.type)
                result = checker.check(
                    oracle,
                    workspace,
                    trajectory,
                    task.workspace,
                )
                results.append(result)

            passed = all(r.passed for r in results)
            return RunResult(
                task_id=task.id,
                passed=passed,
                oracle_results=results,
                workspace_path=workspace if keep_workspace else None,
            )
        finally:
            if not keep_workspace:
                runner.cleanup()

    def evaluate_files(
        self,
        task_path: Path | str,
        trajectory_path: Path | str,
    ) -> RunResult:
        task = EvalTask.from_file(task_path)
        trajectory = Trajectory.from_file(trajectory_path)
        return self.evaluate(task, trajectory)

    def evaluate_directory(
        self,
        tasks_dir: Path | str,
        trajectory_path: Path | str,
        *,
        task_files: list[str] | None = None,
    ) -> list[RunResult]:
        tasks_dir = Path(tasks_dir)
        trajectory = Trajectory.from_file(trajectory_path)
        results: list[RunResult] = []

        if task_files:
            task_paths = [tasks_dir / name for name in task_files]
        else:
            task_paths = sorted(
                path
                for path in tasks_dir.glob("*.json")
                if path.name != "manifest_pass.json"
            )

        for task_file in task_paths:
            task = EvalTask.from_file(task_file)
            results.append(self.evaluate(task, trajectory))

        return results
