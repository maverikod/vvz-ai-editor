# project_pip_install

**Command name:** `project_pip_install`  
**Class:** `ProjectPipInstallCommand`  
**Source:** `code_analysis/commands/project_pip_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Install Python **distribution** packages into the registered project’s virtual environment using `python -m pip install`. Execution uses the same sandbox as `run_project_module` / `run_project_script` (project root as cwd, `PYTHONPATH` = project root, interpreter from `.venv` or `venv` **under that project’s resolved root**).

This is **venv package management**, not AST/import dependency analysis (see `find_dependencies`, `get_imports`, etc.).

## Contract

- **`project_id` is required** for every `project_pip_*` command. It must refer to a **registered** project (`list_projects` / `projectid` file); the server resolves the root from the database and runs pip only in that root’s `.venv` or `venv`—never the code-analysis server venv or an arbitrary path.
- **Queued execution:** this command always runs through the **background job queue** (`use_queue=True`). The RPC/API response returns a **`job_id`**; poll **`queue_get_job_status`** (and optionally `queue_get_job_logs`) until the job completes, then read the pip result from the finished job payload. Do not assume a synchronous inline result for installs.

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | yes | Registered project UUID. Selects exactly one project; pip targets only that project’s `.venv` / `venv`. |
| `packages` | string[] | no | Package specs for pip (e.g. `requests`, `pkg==1.0`). Can be omitted if `requirements_file` is set. |
| `requirements_file` | string \| null | no | Path relative to project root (e.g. `requirements.txt`). Must stay inside the project directory. |
| `upgrade` | boolean | no | If true, adds `--upgrade`. Default false. |
| `timeout_seconds` | integer | no | Optional timeout for the **pip** subprocess. Separate server/queue job limits may still apply. |

At least one of non-empty `packages` or `requirements_file` is required.

## Success data

`stdout`, `stderr`, `returncode`, `timed_out`, `project_id`, `pip_args` (the argument list passed to `python -m pip` after `pip`), plus **session log fields** so you can re-open full pip output later:

- `pip_output_log_path` — absolute path to a UTF-8 log file under `<server log_dir>/project_pip/` (same layout as other server logs; `server.log_dir` in config, default `./logs`). Null if the file could not be written.
- `pip_output_log_relative` — path relative to the server config directory when the log file lives under it (else null).
- `pip_logs_directory` — resolved server log root.
- `pip_log_write_error` — null if logging succeeded; otherwise an error message (stdout/stderr in the JSON response are still present).

These appear on the **completed** queued job result.

## Error codes

`VALIDATION_ERROR`, `INVALID_PARAMS`, `INVALID_PATH`, `VENV_NOT_FOUND`, `INTERNAL_ERROR`.
