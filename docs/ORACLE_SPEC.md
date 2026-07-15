# Oracle Specification

*Eval pillar.* Oracles are property-based checks applied **after** an agent run. They inspect the final workspace and/or the recorded trajectory.

## Common interface

```python
class OracleCheck(ABC):
    oracle_type: str

    def check(
        self,
        oracle: Oracle,
        workspace: Path,
        trajectory: Trajectory,
        initial_workspace: dict[str, str],
    ) -> OracleResult: ...
```

`OracleResult` contains `passed`, `message`, and optional `details`.

## Registered oracles

### `test_must_pass`

Runs a shell command in the workspace directory. Passes when exit code is 0.

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `command` | yes | — | Shell command string |
| `timeout` | no | `60` | Seconds before timeout fail |

**Example:**

```json
{
  "type": "test_must_pass",
  "command": "python -m pytest tests/test_calc.py -q",
  "timeout": 120
}
```

**Use when:** Behavioral correctness must be verified by the project's own test suite.

---

### `file_not_modified`

Fails if the agent trajectory modified a protected file from its initial content.

| Param | Required | Description |
|-------|----------|-------------|
| `path` | yes | Relative path in workspace |

**Example:**

```json
{ "type": "file_not_modified", "path": "tests/test_calc.py" }
```

**Use when:** Scope constraints — agent must not touch tests, docs, or CI config.

**Note:** File must exist in `task.workspace`. Compares trajectory edits against initial snapshot.

---

### `no_network`

Scans all trajectory steps for network-access patterns. Stateless — no workspace inspection.

Patterns include HTTP clients (`curl`, `wget`, `fetch(`, `http://`, `https://`, `requests.`, `urllib`, `httpx`, `socket.`, `webbrowser`) and package managers reaching a registry (`pip install`, `npm install`, `npm ci`, `pnpm install`/`add`, `yarn install`/`add`, `bun install`/`add`, `cargo add`/`install`, `go get`/`install`).

**Example:**

```json
{ "type": "no_network" }
```

**Use when:** Offline/air-gapped fixes, security-sensitive repos, or preventing dependency sprawl mid-task.

---

### `assertion_exists`

Regex search in a workspace file after agent edits. Passes when pattern matches.

| Param | Required | Description |
|-------|----------|-------------|
| `path` | yes | Relative file path |
| `pattern` | yes | Python regex (multiline) |

**Example:**

```json
{
  "type": "assertion_exists",
  "path": "tests/test_calc.py",
  "pattern": "assert add\\(1, 2\\) == 3"
}
```

**Use when:** Detecting deleted or weakened test assertions without requiring exact file equality.

---

## Adding a new oracle

1. Create `src/agentbench/eval/oracles/my_oracle.py`
2. Subclass `OracleCheck`, set `oracle_type`
3. Decorate with `@register_oracle`
4. Import module in `eval/gate/evaluator.py` for registration side effect
5. Add type + required params to `eval/dsl/validator.py`
6. Document here and add pytest coverage

## Failure semantics

- All oracles run independently; one failure does not skip others
- `RunResult.passed` is `True` only when **every** oracle passes
- CLI / gate exit code `1` on any task failure
