# run_project_script

**Command name:** `run_project_script`  
**Class:** `RunProjectScriptCommand`  
**Source:** `code_analysis/commands/run_project_script_command.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The run_project_script command runs a Python script from a registered project inside a sandbox. Only code that belongs to that project (and the standard library) can be executed: the working directory and PYTHONPATH are set to the project root, so imports are restricted to the project tree.

Operation flow:
1. Resolves project root from database by project_id (project must be registered)
2. Normalizes file_path (relative to project root, no leading slash)
3. Validates that the resolved script path lies strictly inside the project root
4. Requires project venv: .venv or venv under project root (fails with VENV_NOT_FOUND if missing)
5. Runs the script in a subprocess with cwd=project root, PYTHONPATH=project root, and project venv
6. Optionally enforces timeout_seconds (subprocess interrupted if exceeded; stdout/stderr reflect output captured before termination)
7. Optionally waits `post_run_delay_seconds` after the subprocess exits (same captured stdout/stderr)
8. Returns stdout, stderr, returncode, timed_out, and post_run_delay_seconds_applied

**Execution mode:** By default this command uses the **job queue** (`use_queue=True`). Submit the command, then use `queue_get_job_status` (and related queue commands) until the job completes; the finished result includes **stdout** and **stderr** for the model. Inline execution is not the default.

Sandbox behavior:
- cwd: Set to the project root directory
- PYTHONPATH: Set only to the project root (no parent paths or system paths)
- Imports: Only modules under the project root and the standard library are available
- Path: Script path must be inside the project root; path traversal (e.g. '..') is rejected

Use cases:
- Run tests or scripts for a specific registered project
- Execute project entry points (e.g. main.py, scripts/run.py) in isolation
- Validate that code runs without depending on external packages outside the project
- Run one-off scripts with a timeout for safety

Important notes:
- Project must have .venv or venv in its root; otherwise VENV_NOT_FOUND is returned
- Project must be registered (use list_projects or create_project)
- file_path is always relative to the project root; absolute paths are not accepted for the script
- On timeout, returncode is None and timed_out is True; stdout/stderr contain output before kill
- Script runs in a separate process; it cannot access the server process or other projects

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from projectid file or list_projects). Project must be registered in the database. Root path is resolved from the projects table. |
| `file_path` | string | **Yes** | Path to the Python script relative to project root. Must not be empty. Leading slashes and backslashes are normalized. Resolved path must lie strictly inside the project root (path traversal is reject |
| `args` | array | No | Optional list of arguments passed to the script as argv[1:]. If omitted, the script receives no additional arguments. |
| `timeout_seconds` | integer | No | Optional timeout in seconds. If the script runs longer, the subprocess is interrupted and the result has timed_out=True and returncode=None. |
| `post_run_delay_seconds` | integer | No | Optional non-negative seconds to wait after the subprocess exits before returning (stdout/stderr unchanged). For short settle time after the script finishes. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `stdout`: Standard output of the script
- `stderr`: Standard error of the script
- `returncode`: Process exit code (None if timed out)
- `timed_out`: True if process was killed due to timeout
- `post_run_delay_seconds_applied`: Seconds waited after subprocess exit (from `post_run_delay_seconds`, or 0)
- `script`: Normalized script path relative to project root
- `project_id`: Project UUID used

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** VALIDATION_ERROR, INVALID_FILE_PATH, INVALID_PATH, FILE_NOT_FOUND, VENV_NOT_FOUND, INTERNAL_ERROR (and others).

---

## Examples

### Correct usage

**Run main entry point**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "main.py"
}
```

Runs main.py from the project root. No arguments and no timeout.

**Run script with arguments and timeout**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "scripts/run.py",
  "args": [
    "--verbose"
  ],
  "timeout_seconds": 30
}
```

Runs scripts/run.py with one argument and a 30-second timeout. If the script exceeds 30 seconds, it is killed and timed_out is True.

**Run test module**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "tests/test_foo.py"
}
```

Runs a test file. Imports are limited to the project and stdlib.

### Incorrect usage

- **VALIDATION_ERROR**: project_id not in database or root_path missing on disk. Ensure the project is registered (list_projects) and the root path exists.

- **INVALID_FILE_PATH**: file_path='' or file_path='/''. Provide a non-empty path relative to the project root.

- **INVALID_PATH**: file_path='../../../etc/passwd' or path escapes root. Use a path relative to the project root that does not leave it.

- **FILE_NOT_FOUND**: file_path='missing.py' or path points to a directory. Verify the file exists under the project root and is a regular file.

- **VENV_NOT_FOUND**: Neither .venv/bin/python nor venv/bin/python exists under project root. Create a venv in the project root: python -m venv .venv (or venv). The command requires project venv to run scripts.

- **INTERNAL_ERROR**: Exception in sandbox or subprocess handling. Check server logs for details.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `VALIDATION_ERROR` | Project not found or project root path does not exist | Ensure the project is registered (list_projects) a |
| `INVALID_FILE_PATH` | file_path is empty after normalization | Provide a non-empty path relative to the project r |
| `INVALID_PATH` | Resolved script path is outside the project root | Use a path relative to the project root that does  |
| `FILE_NOT_FOUND` | Script file does not exist or is not a file | Verify the file exists under the project root and  |
| `VENV_NOT_FOUND` | Project virtual environment (.venv or venv) not found | Create a venv in the project root: python -m venv  |
| `INTERNAL_ERROR` | Unexpected error during execution | Check server logs for details. |

## Best practices

- Use only for registered projects; ensure project_id is from list_projects or projectid
- Use relative file_path (e.g. main.py, scripts/run.py) without leading slash
- Set timeout_seconds for long-running or untrusted scripts to avoid hanging
- Check returncode and timed_out in the response to detect failures and timeouts
- Script cannot access other projects or server state; use for isolated execution only

---
