# universal_file_edit — Source Specification

<!-- non-binding -->
Author: Vasiliy Zdanovskiy
Date: 2026-05-16
<!-- /non-binding -->

## 1. Purpose

Replace the existing zoo of file-editing commands with four focused commands
that share a single lifecycle model. The commands are:

- `universal_file_open`
- `universal_file_edit`
- `universal_file_write`
- `universal_file_close`

The existing `universal_file_preview` command is unchanged and remains
registered. All other editing commands are removed from registration.

## 2. Commands removed from registration

The following commands are unregistered (code is not deleted, only
registration is removed from hooks.py):

- `universal_file_save`
- `universal_file_replace`
- `universal_file_read`
- `universal_file_delete`
- `cst_load_file`, `cst_find_node`, `cst_get_node_info`,
  `cst_get_node_by_range`, `cst_modify_tree`, `cst_save_tree`
- `json_load_file`, `json_find_node`, `json_modify_tree`, `json_save_tree`
- `write_project_text_lines`, `replace_file_lines`
- `compose_cst_module`, `query_cst`, `list_cst_blocks`
- `read_project_text_file`

`get_file_lines` remains registered as a fallback for files with syntax
errors that cannot be parsed.

## 3. Draft file model

Three format groups exist, each with different draft lifecycle:

### Group A: sidecar (Python)

- Draft file: `<file>.cst_sidecar`
- Written after every mutation (existing `write_sidecar_atomic` from
  `core/cst_tree/tree_sidecar.py`).
- Sync check: `verify_sidecar_against_source()` — sha256 of source code
  is embedded in sidecar header (`CST_TREE_V1 sha256=...`).
- Persists after `universal_file_close` (stable_id must survive between
  sessions).
- Stable_id are UUID assigned at parse time; they live in the sidecar.

### Group B: tree-temp (JSON, YAML)

- Draft file: `<file>.draft` containing serialised tree (JSON or YAML).
- Created by `universal_file_open`, written after every mutation.
- Sync check: sha256 of draft vs sha256 of original file.
- Deleted by `universal_file_close`.
- Stable_id not needed: address is JSON pointer (`/key/0/value`),
  deterministically computed from document structure.

### Group C: text (MD, txt, rst, adoc)

- Draft file: `<file>.draft` containing a byte-for-byte copy of original.
- Created by `universal_file_open`, written after every mutation
  (entire buffer).
- Sync check: sha256 of draft vs sha256 of original file.
- Deleted by `universal_file_close`.

Lockfile (all groups):

- `<file>.write` — contains current server PID as text.
- Created on first `universal_file_write` call.
- Deleted on successful commit or on `universal_file_open`.

## 4. Existing infrastructure reused

### 4.1 core/file_handlers/ (save/replace logic)

- `core/file_handlers/registry.py` — `resolve_handler(ext)` maps extension
  to handler_id (text/json/yaml/python); `HANDLER_IDS`, `OPERATIONS`.
- `core/file_handlers/base.py` — `BaseFileHandler` ABC with `read`, `save`,
  `replace`, `delete`; `FileHandlerRequest`, `FileHandlerResult`.
- `core/file_handlers/python_handler.py` — `PythonFileHandler.save` and
  `replace` via `run_ops_mode` (CST pipeline).
- `core/file_handlers/text_handler.py` — text read/save/replace.
- `core/file_handlers/json_handler.py` — JSON read/save/replace.
- `core/file_handlers/yaml_handler.py` — YAML read/save/replace.
- `core/file_handlers/diff_support.py` — diff computation.
- `core/file_handlers/text_ranges.py` — text range operations.

### 4.2 core/cst_tree/ (Python sidecar)

- `core/cst_tree/tree_sidecar.py`:
  - `sidecar_path_for_py(file_path)` — returns sidecar path.
  - `write_sidecar_atomic(tree, file_path)` — writes sidecar after mutation.
  - `verify_sidecar_against_source(file_path)` — checks sha256 match.
  - `SIDECAR_HEADER_PREFIX = "CST_TREE_V1 sha256="`
- `core/cst_tree/tree_saver.py` — `save_tree_to_file` (full save pipeline).
- `core/cst_tree/tree_builder.py` — `get_tree(tree_id)`, load/parse.

### 4.3 core/json_tree/ and core/yaml_tree/ (in-memory trees)

- `core/json_tree/tree_builder.py` — `load_file_to_tree`, `get_tree`,
  `remove_tree`. Trees stored in module-level `_trees` dict.
- `core/yaml_tree/tree_builder.py` — same interface.
- No persistent sidecar for JSON/YAML; draft file written by new code.

### 4.4 core/backup_manager.py

- `BackupManager.create_backup(file_path, command)` — creates backup entry.
- `BackupManager.list_versions(file_path)` — returns list; empty = no history.
- `BackupManager.restore_file(file_path, backup_uuid)` — restores from backup.

### 4.5 core/git_integration.py

- `commit_after_write(root_path, file_path, config)` — git commit if
  `git_commit_on_write` is enabled in config.

### 4.6 core/file_lock.py

- `file_lock(path)` — advisory file lock context manager.

### 4.7 universal_file_replace_command.py

- `_sort_text_replacements_bottom_up(ops)` — sorts text operations by
  start_line descending. Reuse directly in `universal_file_edit`.

### 4.8 commands/universal_file_preview/ (read-only, unchanged)

- `dispatcher.py` — `HandlerDispatcher` (ext → FileHandler).
- `base_handler.py` — `FileHandler` ABC: `open_root`, `resolve_node_ref`.
- `session.py` — `resolve_session`.
- `models.py` — `Node`, `NodeKind`, `Block`.
- `handlers/` — python, json, yaml, text, md, jsonl handlers.

## 5. universal_file_open

Inputs: `project_id`, `file_path`.

1. Delete `<file>.write` if exists (stale lockfile).
2. Delete `<file>.draft` if exists (stale tree-temp or text draft).
   For Python: do NOT delete `<file>.cst_sidecar`.
3. Resolve handler group via `registry.resolve_handler(ext)`.
4. Parse file and write initial draft:
   - Python: `cst_load_file` → `write_sidecar_atomic`. Sidecar already
     exists from prior session — reload and rewrite to ensure sync.
   - JSON: `load_file_to_tree` → serialise → write `<file>.draft`.
   - YAML: `load_file_to_tree` → serialise → write `<file>.draft`.
   - Text: copy `<file>` → `<file>.draft`.
5. If `BackupManager.list_versions(file_path)` is empty: create initial
   backup via `BackupManager.create_backup`.
6. Return `session_id` (UUID) and list of available operations for the
   format group.

## 6. universal_file_edit

Inputs: `project_id`, `session_id`, `operations` (list).

Operation fields:
- `type`: one of `insert`, `delete`, `replace`.
- Tree address: `parent_node_id` (StableIdentifier), `position` (int).
- Text address: `start_line`, `end_line` (1-based inclusive).
- `content`: new content string; required for insert and replace.

### 6.1 Python (sidecar group)

1. Validate batch: no ancestor-descendant pairs. Error: `NESTED_BATCH_FORBIDDEN`.
   Batch rejected atomically on violation.
2. Apply operations sequentially in received order via CST pipeline
   (`run_ops_mode` from `core/file_handlers/python_handler.py`).
3. After each operation: `write_sidecar_atomic` writes updated sidecar.
4. Return updated node list.

### 6.2 JSON / YAML (tree-temp group)

1. No ancestor-descendant validation needed (pointer-based addressing).
2. Apply operations sequentially to in-memory tree.
3. After each operation: serialise tree → write `<file>.draft`.
4. Return updated node list.

### 6.3 Text (text group)

1. Sort operations by `start_line` descending
   (reuse `_sort_text_replacements_bottom_up`).
2. Apply to in-memory buffer.
3. Write buffer → `<file>.draft` once after all operations.
4. Return updated line count.

## 7. universal_file_write

Inputs: `project_id`, `session_id`.

### 7.1 First call (lockfile absent or PID mismatch)

1. Generate code from draft:
   - Python: `save_tree_to_file` to temp → read temp as code.
   - JSON/YAML: serialise in-memory tree to temp.
   - Text: read `<file>.draft`.
2. Compute diff(`<file>`, generated code) via `diff_support`.
3. Write `<file>.write` with current server PID (`os.getpid()`).
4. Return diff. Nothing written to `<file>`.

### 7.2 Second call (lockfile present, PID matches,
     lockfile mtime > draft mtime)

1. `BackupManager.create_backup(<file>)` and
   `BackupManager.create_backup(draft)` atomically — one history entry.
2. Generate code from draft → temp file.
3. If generation fails: `BackupManager.restore_file(<file>)`. Return error.
4. Rename temp → `<file>`.
5. Delete `<file>.write`.
6. `commit_after_write` if git enabled.
7. Return success with diff.

## 8. universal_file_close

Inputs: `project_id`, `session_id`.

### 8.1 Python (sidecar group)

1. `verify_sidecar_against_source(file_path)`:
   - Match: leave sidecar as-is. Delete `<file>.write` if present.
   - Mismatch: rebuild sidecar from source (`cst_load_file` →
     `write_sidecar_atomic`). No backup. Delete `<file>.write`.
     Return `draft_rebuilt: true`.
2. Release session.

### 8.2 JSON / YAML (tree-temp group)

1. Compare sha256(`<file>.draft`) vs sha256(`<file>`):
   - Match: delete `<file>.draft`. Delete `<file>.write` if present.
   - Mismatch: rebuild `<file>.draft` from `<file>` (re-parse →
     serialise). No backup. Delete `<file>.write`.
     Return `draft_rebuilt: true`.
2. `remove_tree(tree_id)` to free in-memory tree.
3. Release session.

### 8.3 Text (text group)

1. Delete `<file>.draft` if present.
2. Delete `<file>.write` if present.
3. Release session.

## 9. Session storage

Module-level dict in the server process:

```python
_sessions: dict[str, EditSession]

@dataclass
class EditSession:
    session_id: str       # UUID
    file_path: str        # project-relative
    abs_path: Path        # absolute path to <file>
    draft_path: Path      # absolute path to draft
    format_group: str     # 'sidecar' | 'tree-temp' | 'text'
    handler_id: str       # 'python' | 'json' | 'yaml' | 'text'
    tree_id: str | None   # in-memory tree UUID (tree-temp group only)
```

Not persisted across server restarts. Client must call
`universal_file_open` again after restart.

## 10. Error codes

- `SESSION_NOT_FOUND` — session_id unknown.
- `DRAFT_NOT_FOUND` — draft missing when expected.
- `NESTED_BATCH_FORBIDDEN` — ancestor-descendant pair in batch (Python only).
- `WRITE_FAILED` — code generation or file write failed; backup restored.
- `UNKNOWN_FORMAT` — file extension not supported.
- `PARSE_ERROR` — file could not be parsed on open.
