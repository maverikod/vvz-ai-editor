# project_pip_uninstall

**Command name:** `project_pip_uninstall`  
**Class:** `ProjectPipUninstallCommand`  
**Source:** `code_analysis/commands/project_pip_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Remove Python packages from the project venv using `python -m pip uninstall -y` (non-interactive). Same sandbox as other `project_pip_*` commands.

**Contract:** `project_id` is **required** and must identify a **registered** project. Pip modifies only that project’s `.venv` or `venv`. Not queued (`use_queue=False`).

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | yes | Registered project UUID. Selects the project whose venv is modified. |
| `packages` | string[] | yes | At least one distribution name to remove. |
| `timeout_seconds` | integer | no | Optional subprocess timeout. |

## Success data

`stdout`, `stderr`, `returncode`, `timed_out`, `project_id`, `packages`, plus `pip_output_log_path`, `pip_output_log_relative`, `pip_logs_directory`, `pip_log_write_error` (session log under `<server log_dir>/project_pip/`; see `project_pip_install`).

## Error codes

`VALIDATION_ERROR`, `INVALID_PARAMS`, `INVALID_PATH`, `VENV_NOT_FOUND`, `INTERNAL_ERROR`.
