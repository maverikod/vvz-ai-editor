# run_project_module

**Command name:** `run_project_module`  
**Class:** `RunProjectModuleCommand`  
**Source:** `code_analysis/commands/run_project_module_command.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The run_project_module command runs a Python module in a registered project as python -m <module> [args] inside the same sandbox used by run_project_script: working directory and PYTHONPATH are set to the project root, and the project's virtual environment (.venv or venv) is used for the interpreter.

**Execution mode:** This command runs **inline** (not via the job queue: `use_queue=False`). Sandbox work is still offloaded with `asyncio.to_thread`, but there is no `queue_get_job_status` step. By contrast, **`run_project_script` is queued by default** so clients poll the queue for completion. `run_project_module` stays inline because the bounded job queue applies a maximum runtime and may kill the worker, which would wrongly terminate long-lived `python -m` processes (for example application servers). To run a file with the default queued path, use `run_project_script`.

Operation flow:
1. Resolves project root from database by project_id (project must be registered)
2. Validates module is non-empty (after stripping whitespace)
3. Requires project venv: .venv or venv under project root (fails with VENV_NOT_FOUND if missing)
4. Runs python -m <module> [args] in a subprocess with cwd=project root, PYTHONPATH=project root, and project venv
5. Optionally enforces timeout_seconds (process killed if exceeded)
6. Returns stdout, stderr, returncode, and timed_out flag

Sandbox behavior (same as run_project_script):
- cwd: Set to the project root directory
- PYTHONPATH: Set only to the project root
- Interpreter: Project's .venv/bin/python or venv/bin/python
- Imports: Only modules under the project root and the standard library are available

Use cases:
- Verify that a project application loads (e.g. python -m ai_admin --help) without using the console
- Start or test the project's main module (e.g. python -m ai_admin) in isolation
- Run pytest or other tools as a module in the project context (e.g. python -m pytest tests/)
- Comply with test_data rules: all interaction with test_data projects via server commands only

Important notes:
- Project must have .venv or venv in its root; otherwise VENV_NOT_FOUND is returned
- Project must be registered (use list_projects or create_project)
- module is the module name only (e.g. 'ai_admin'), not a file path
- On timeout, returncode is None and timed_out is True; stdout/stderr contain output before kill
- Process runs in a separate subprocess; it cannot access the server process or other projects

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from projectid file or list_projects). Project must be registered in the database. Root path is resolved from the projects table. |
| `module` | string | **Yes** | Module name to run (e.g. 'ai_admin' for python -m ai_admin). Must be non-empty; leading/trailing whitespace is stripped. |
| `args` | array | No | Optional list of arguments passed to the module as argv[1:]. If omitted, the module receives no additional arguments. |
| `timeout_seconds` | integer | No | Optional timeout in seconds. If the module runs longer, the process is killed and the result has timed_out=True and returncode=None. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `stdout`: Standard output of the process
- `stderr`: Standard error of the process
- `returncode`: Process exit code (None if timed out)
- `timed_out`: True if process was killed due to timeout
- `module`: Module name that was run
- `project_id`: Project UUID used

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** VALIDATION_ERROR, INVALID_MODULE, INVALID_PATH, VENV_NOT_FOUND, INTERNAL_ERROR (and others).

---

## Examples

### Correct usage

**Verify project application loads (e.g. vast_srv)**
```json
{
  "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
  "module": "ai_admin",
  "args": [
    "--help"
  ]
}
```

Runs python -m ai_admin --help in the project sandbox. Use to verify imports and CLI without using the console.

**Run pytest as module with timeout**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "module": "pytest",
  "args": [
    "-v",
    "tests/"
  ],
  "timeout_seconds": 120
}
```

Runs python -m pytest -v tests/ with a 120-second timeout. If tests hang, the process is killed and timed_out is True.

**Run module with no arguments**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "module": "mymodule"
}
```

Runs python -m mymodule with no extra arguments.

### Incorrect usage

- **VALIDATION_ERROR**: project_id not in database or root_path missing on disk. Ensure the project is registered (list_projects) and the root path exists.

- **INVALID_MODULE**: module='' or module='   '. Provide a non-empty module name (e.g. 'ai_admin', 'pytest').

- **INVALID_PATH**: Resolved project root path is not a directory. Ensure the project root exists and is a directory.

- **VENV_NOT_FOUND**: Neither .venv/bin/python nor venv/bin/python exists under project root. Create a venv in the project root: python -m venv .venv (or venv). The command requires project venv to run the module.

- **INTERNAL_ERROR**: Exception in sandbox or subprocess handling. Check server logs for details.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `VALIDATION_ERROR` | Project not found or project root path does not exist | Ensure the project is registered (list_projects) a |
| `INVALID_MODULE` | module is empty or only whitespace | Provide a non-empty module name (e.g. 'ai_admin',  |
| `INVALID_PATH` | Project root is not a directory | Ensure the project root exists and is a directory. |
| `VENV_NOT_FOUND` | Project virtual environment (.venv or venv) not found | Create a venv in the project root: python -m venv  |
| `INTERNAL_ERROR` | Unexpected error during execution | Check server logs for details. |

## Best practices

- Use only for registered projects; ensure project_id is from list_projects or projectid
- Use run_project_module (not console) to verify or run test_data project apps; complies with test_data rules
- Set timeout_seconds for long-running modules (e.g. pytest, server startup) to avoid hanging
- Check returncode and timed_out in the response to detect failures and timeouts
- For running a script file instead of a module, use run_project_script with file_path

---
