# project_pip_list

**Command name:** `project_pip_list`  
**Class:** `ProjectPipListCommand`  
**Source:** `code_analysis/commands/project_pip_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

List installed packages in the project’s venv via `python -m pip`, either default `pip list`, `pip list --format=json`, or `pip freeze`. Same sandbox as other `project_pip_*` commands.

Not related to static **import dependency** analysis.

**Contract:** `project_id` is **required** and must identify a **registered** project. Pip runs only in that project’s `.venv` or `venv` under the resolved root (not the server venv). This command is **not** queued (`use_queue=False`).

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | yes | Registered project UUID. Selects the project whose venv is listed. |
| `list_format` | string | no | One of: `columns` (default `pip list`), `json` (`pip list --format=json`), `freeze` (`pip freeze`). |
| `timeout_seconds` | integer | no | Optional subprocess timeout. |

## Success data

`stdout`, `stderr`, `returncode`, `timed_out`, `project_id`, `list_format`, and session log fields `pip_output_log_path`, `pip_output_log_relative`, `pip_logs_directory`, `pip_log_write_error` (pip output is also written under `<server log_dir>/project_pip/`; see `project_pip_install`).

## Error codes

`VALIDATION_ERROR`, `INVALID_PARAMS`, `INVALID_PATH`, `VENV_NOT_FOUND`, `INTERNAL_ERROR`.
