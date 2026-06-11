# project_pip_search

**Command name:** `project_pip_search`  
**Class:** `ProjectPipSearchCommand`  
**Source:** `code_analysis/commands/project_pip_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

List or **search only among installed packages** in the project venv: runs `python -m pip list --format=json` once, then filters rows in memory. **Does not** query PyPI or any package index (unlike legacy `pip search`).

Not related to static **import dependency** analysis.

**Contract:** `project_id` is **required**. Pip uses only that project’s `.venv` or `venv`. **Not** queued (`use_queue=False`). Optional `query` + `match_mode` restrict results; omit `query` to return every installed package as structured rows.

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | yes | Registered project UUID. |
| `query` | string or null | no | Filter; omit, `null`, or empty string returns all installed packages. |
| `match_mode` | string | no | `substring` (default), `prefix`, or `exact` — applied to installed names (substring also matches `version` case-insensitively). |
| `timeout_seconds` | integer | no | Optional subprocess timeout. |

## Success data

Subprocess fields, `pip_args`, `query` (null when listing all), `match_mode`, `matches` (list of objects from pip JSON), `match_count`, `parse_error` if JSON could not be parsed, plus session log fields (`pip_output_log_path`, etc.; see `project_pip_install`).

## Error codes

`VALIDATION_ERROR`, `INVALID_PARAMS`, `INVALID_PATH`, `VENV_NOT_FOUND`, `INTERNAL_ERROR`.
