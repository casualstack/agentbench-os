# Eval DSL

*Eval pillar.* Tasks and trajectories are JSON documents. The DSL is intentionally minimal — no custom parser language — so tasks are diffable, reviewable in PRs, and easy to generate.

## Task schema

```json
{
  "id": "kebab-case-id",
  "name": "Human-readable title",
  "description": "What this eval measures",
  "prompt": "Instruction given to the agent",
  "tags": ["optional", "labels"],
  "workspace": {
    "relative/path.py": "file contents as string\n"
  },
  "oracles": [
    { "type": "oracle_type", "...": "params" }
  ]
}
```

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable identifier |
| `name` | string | Short title |
| `description` | string | Eval intent |
| `prompt` | string | Agent instruction |
| `workspace` | object | Map of relative path → file content |
| `oracles` | array | Non-empty list of oracle objects |

### Optional fields

| Field | Type | Default |
|-------|------|---------|
| `tags` | string[] | `[]` |

## Oracle objects

Each oracle is a JSON object with a `type` field. Remaining keys are oracle-specific parameters (flattened into `Oracle.params`).

```json
{ "type": "test_must_pass", "command": "python -m pytest tests/ -q" }
{ "type": "file_not_modified", "path": "README.md" }
{ "type": "no_network" }
{ "type": "assertion_exists", "path": "tests/test_x.py", "pattern": "assert foo" }
```

Validation runs automatically when loading tasks via `EvalTask.from_file()`.

## Trajectory schema

```json
{
  "metadata": {
    "agent": "cursor",
    "model": "claude-sonnet-4",
    "description": "optional notes"
  },
  "steps": [
    {
      "type": "tool_call",
      "tool": "write_file",
      "args": { "path": "src/foo.py", "content": "..." }
    }
  ]
}
```

### Supported write tools

Recognized in `Trajectory.file_edits()`:

- `write_file`, `edit_file`, `str_replace`
- `Write`, `StrReplace` (Cursor-style)
- `step_type == "file_edit"`

Path args: `path`, `file_path`, or `target_file`. Content: `content` or `new_string`.

### Supported command tools

- `run_command`, `shell`, `bash`, `Bash`, `execute`
- `step_type == "command"`

## Example: full task

See `tasks/01_fix_failing_test_no_delete.json`:

- Broken `src/calc.py` in workspace
- Oracles ensure tests still contain the assertion, test file unchanged, pytest passes

## Programmatic validation

```python
from agentbench.dsl import validate_task_dict, validate_trajectory_dict

validate_task_dict(task_dict)       # raises ValidationError on bad schema
validate_trajectory_dict(traj_dict)
```

## File conventions

- Tasks live in `tasks/` as `NN_short_name.json`
- Trajectory fixtures in `tests/fixtures/trajectory_*.json`
- Production trajectories uploaded as CI artifacts (future)
