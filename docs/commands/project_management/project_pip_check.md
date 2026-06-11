# project_pip_check

**Command name:** `project_pip_check`  
**Class:** `ProjectPipCheckCommand`  
**Source:** `code_analysis/commands/project_pip_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Check whether given **distribution names** are installed in the project’s venv by running `python -m pip list --format=json` once, then matching **normalized** names (PEP 503 style: case-insensitive; `_` vs `-`). No PyPI or index access.

Not related to static **import dependency** analysis.

**Contract:** `project_id` and `packages` are **required**. `project_id` must identify a **registered** project; pip uses only that project’s `.venv` or `venv`. This command is **not** queued (`use_queue=False`). Session logs mirror other `project_pip_*` commands.

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | yes | Registered project UUID. |
| `packages` | array of string | yes | One or more names or requirement-like strings; only the **project name** is used (e.g. `numpy>=1.0` → `numpy`). |
| `timeout_seconds` | integer | no | Optional subprocess timeout. |

## Success data

Raw `stdout` / `stderr` / `returncode` / `timed_out` from `pip list --format=json`, plus:

- `pip_args`: `["list", "--format=json"]`
- `results`: list of `{ requested, normalized, installed, name, version }` per input string
- `all_requested_installed`: `true` if every result has `installed: true`
- `parse_error`: `null`, or a message if JSON parsing failed

Also `pip_output_log_path`, `pip_output_log_relative`, `pip_logs_directory`, `pip_log_write_error` (under `<server log_dir>/project_pip/`; see `project_pip_install`).

## Error codes

`VALIDATION_ERROR`, `INVALID_PARAMS`, `INVALID_PATH`, `VENV_NOT_FOUND`, `INTERNAL_ERROR`.
