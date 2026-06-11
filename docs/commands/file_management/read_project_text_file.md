# read_project_text_file

> **Obsolete for MCP viewing/editing.** Use [universal_file_preview](../file_editing/universal_file_preview.md) (read) and the [universal edit session](../file_editing/WORKFLOW.md) (write).

**Command name:** `read_project_text_file`  
**Class:** `ReadProjectTextFileCommand`  
**Source:** `code_analysis/commands/read_project_text_file_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Read policy (non-code vs Python vs other source)

**Non-code plain text** — documentation, data-ish configs (`.json`, `.toml`, `.yaml`, `.md`, `.txt`, …): read directly as raw lines (or structured JSON for small `.json` per implementation).

**Python / Python-ecosystem paths** (`.py`, `.pyi`, `.pyw`, `.pyx`, `.pxd`, `.pxi`): **not** rejected. The command **automatically routes** to the same behavior as **`get_file_lines`** (line-based read under the CST category; internal flag `allow_healthy_line_ops` so healthy Python does **not** return `USE_CST_COMMANDS`). You still call **`read_project_text_file`**; the response shape matches **`get_file_lines`** for line reads.

**Other blocked program-source suffixes** (e.g. `.go`, `.rs`, `.java`): rejected with `CODE_FILE_FORBIDDEN` (see `project_text_file_guard.py`).

The suffix check runs **before** line-range validation and filesystem access (except for Python routing, which resolves the project path like **`get_file_lines`**).

---

## Purpose

Return raw text lines from a project file for non-code paths **without LibCST**. For Python paths, behavior matches **`get_file_lines`** (see above).

- Input: `project_id`, `file_path` (relative to project root), `start_line`, `end_line` (1-based, inclusive).
- Range is clamped to the file; returned `start_line` / `end_line` reflect the actual range.
- Empty file: success with `lines: []`, `total_lines: 0`.

**Schema / metadata:** root-level `title`, `description`, and `examples` in `get_schema()`; optional `metadata()` on the command class for discovery (`detailed_description`, `usage_examples`, `error_codes`); `additionalProperties: false` on params.

---

## Arguments

| Parameter     | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `project_id`  | string  | **Yes**  | Project UUID. |
| `file_path`   | string  | **Yes**  | Path relative to project root. Python → routed to `get_file_lines`. Other blocked source suffixes → error. |
| `start_line`  | integer | **Yes**  | Start line (1-based, inclusive), ≥ 1. |
| `end_line`    | integer | **Yes**  | End line (1-based, inclusive), ≥ 1. |

---

## Returned data (success)

- `success`: true  
- `file_path`, `start_line`, `end_line`, `lines` (no embedded newlines), `total_lines`

## Error codes (examples)

- `CODE_FILE_FORBIDDEN` — path is a blocked non-Python program-source type  
- `INVALID_RANGE` — invalid line range  
- `FILE_NOT_FOUND` — path does not exist  
- Validation / resolution errors for bad `project_id`  

See command implementation and `project_text_file_guard.py` for full codes and `details`.
