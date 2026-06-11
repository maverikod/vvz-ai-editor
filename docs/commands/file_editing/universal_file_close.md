# universal_file_close

**Command:** `universal_file_close`  
**Class:** `UniversalFileCloseCommand`  
**Source:** `code_analysis/commands/universal_file_edit/close_command.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Release an edit session and reconcile draft artefacts with the on-disk file.

**Workflow step 5.** Call **always** — after commit or on abort (discard uncommitted draft).

---

## Behaviour by format_group

| format_group | On close |
|--------------|----------|
| **sidecar** | If sidecar SHA matches source → keep sidecar; else rebuild sidecar from disk (`draft_rebuilt: true`). Deletes stale lockfile. |
| **tree-temp** | If draft SHA matches source → delete draft; else rebuild draft from disk. Removes in-memory tree. |
| **text** | Deletes draft and lockfile. |

Uncommitted edits are **lost** when closing without commit (by design).

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID |
| `session_id` | string | **Yes** | Session to release |

---

## Returned data

### Success

- Session released
- Optional `draft_rebuilt: true` when artefacts were reconciled from disk

### Error

`SESSION_NOT_FOUND`

---

## Examples

```json
{"project_id": "<uuid>", "session_id": "<session>"}
```

---

## Best practices

- Close even when abandoning edits — avoids orphaned lockfiles.
- After close, a new edit requires `universal_file_open` again.

---

## See also

- [WORKFLOW.md](WORKFLOW.md)
