# universal_file_write

**Command:** `universal_file_write`  
**Class:** `UniversalFileWriteCommand`  
**Source:** `code_analysis/commands/universal_file_edit/write_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Generate code from the session draft, show a diff against the on-disk file, and optionally **commit** with backup.

**Workflow step 4.** Always inspect preview before commit ([FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)).

---

## Write modes

### tree-temp (JSON/YAML)

Every call requires explicit mode:

| write_mode | Effect |
|------------|--------|
| `preview` | Unified diff only; no disk write |
| `commit` | Backup + atomic write + index update path |

**Forbidden:** `commit` without a preceding `preview` in the same session.

### sidecar (Python) / text

Two-phase **PID lockfile** on the canonical file:

1. First call (no valid lock) → diff preview, `<file>.write` lock created
2. Second call (lock PID matches, lock newer than draft) → backup + commit

`write_mode` may also be accepted where implemented — check `help(universal_file_write)`.

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID |
| `session_id` | string | **Yes** | Active edit session |
| `write_mode` | string | tree-temp: **Yes** | `preview` or `commit` |
| `commit_message` | string | No | Optional git commit after write (when enabled in config) |

---

## Returned data

### Success (preview)

- Unified diff text (committed → draft)
- Lockfile state / `preview_only: true` where applicable

### Success (commit)

- Diff of applied change
- Backup UUID when created
- Index update triggers for Python

### Error

`SESSION_NOT_FOUND`, `WRITE_FAILED` (backup restored on failure), `DRAFT_NOT_FOUND`, validation errors on Python commit.

---

## Examples

**tree-temp**

```json
{"project_id": "<uuid>", "session_id": "<session>", "write_mode": "preview"}
```

```json
{"project_id": "<uuid>", "session_id": "<session>", "write_mode": "commit"}
```

**sidecar / text (two calls)**

```json
{"project_id": "<uuid>", "session_id": "<session>"}
```

```json
{"project_id": "<uuid>", "session_id": "<session>"}
```

---

## Best practices

- Read the full diff before the commit call.
- On Python validation failure, fix `code_lines` in edit and retry write — do not bypass with direct file tools.
- Run `format_code`, `lint_code`, `type_check_code` after successful commit.

---

## See also

- [universal_file_close.md](universal_file_close.md)
- [WORKFLOW.md](WORKFLOW.md)
