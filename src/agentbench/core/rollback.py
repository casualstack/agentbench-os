"""Rollback capability for destructive agent actions."""

import os
import shutil
import subprocess
from pathlib import Path
from agentbench.core.trajectory import TrajectoryStep

def rollback_step(step: TrajectoryStep, project_root: str | Path) -> bool:
    """Attempts to roll back a trajectory step's changes."""
    project_root = Path(project_root)
    
    if step.tool_name in ("write_file", "edit_file", "str_replace", "Write", "StrReplace"):
        # For file modifications, we can reverse them by checking git if available
        # or if we kept backups. For now, rely on git.
        target = step.tool_args.get("path") or step.tool_args.get("file_path") or step.tool_args.get("target_file")
        if not target:
            return False
            
        target_path = project_root / target
        
        try:
            subprocess.run(["git", "checkout", "--", str(target)], cwd=str(project_root), check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False
            
    elif step.tool_name in ("run_command", "shell", "bash", "Bash", "execute"):
        # For bash commands, we can't reliably roll them back automatically
        # unless it's a git commit.
        cmd = step.tool_args.get("command") or step.tool_args.get("cmd", "")
        if isinstance(cmd, str) and "git commit" in cmd:
            try:
                subprocess.run(["git", "reset", "--soft", "HEAD~1"], cwd=str(project_root), check=True, capture_output=True)
                return True
            except subprocess.CalledProcessError:
                return False
                
    return False
