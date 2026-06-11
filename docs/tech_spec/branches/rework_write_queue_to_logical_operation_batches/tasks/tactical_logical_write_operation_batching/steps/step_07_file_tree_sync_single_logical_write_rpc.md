# Atomic step 07: `sync_file_to_db_atomic` — one `execute_logical_write_operation`

## Executor role

`coder_auto`

## Execution directive

Refactor `code_analysis/core/database/file_tree_sync.py` so `sync_file_to_db_atomic` **never** calls `database.begin_transaction`, `database.execute_batch`, `database.commit_transaction`, or `database.rollback_transaction` for the SQLite RPC path. Instead, after CST tree construction, build **one** `LogicalWriteProgramV1` and call **`database.execute_logical_write_operation`** **once**. Use **`build_file_data_atomic_batches`** from step 06 for the file-data portion (import from `..database_client.file_data_batch`).

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `code_analysis/core/database/file_tree_sync.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** steps 05–06 (`execute_logical_write_operation`, `build_file_data_atomic_batches`).
- **Blocks:** tests steps 08–12.

## Read first

- Current `file_tree_sync.py` (full file)
- `code_analysis/core/database/logical_write_program.py`

## Forbidden alternatives

- Do **not** call `update_file_data_atomic_batch` from this file (would double-RPC file-data portion).
- Do **not** reintroduce `begin_transaction` / `execute_batch` / `commit_transaction` for this sync.

## Snapshot / tree batch construction (prescriptive SQL)

Replace Python-held `snapshot_id` with SQLite subqueries tied to `file_id` and insert order:

1. **Batch S0 — delete old snapshot row(s) for file:**  
   `DELETE FROM file_tree_snapshots WHERE file_id = ?` with `(file_id,)`.

2. **Batch S1 — insert new snapshot:**  
   Same `INSERT INTO file_tree_snapshots (file_id, project_id, source_payload, file_mtime) VALUES (?, ?, ?, ?)` with `(file_id, project_id, source_code, file_mtime)`.

3. **Batch S2 — insert root:**  
   `INSERT INTO file_tree_snapshot_roots (snapshot_id, root_node_id) VALUES ((SELECT id FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1), ?)`  
   Params: `(file_id, root_node_id)` where `root_node_id = tree.root_node_id`.

4. **Batch S3 — node rows:** If `node_rows` non-empty, **one** batch listing all `INSERT INTO file_tree_snapshot_nodes (snapshot_id, node_id, parent_node_id, child_index) VALUES ((SELECT id FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1), ?, ?, ?)` for each node, with params `(file_id, nid, pid, cidx)` per row (four placeholders including the repeated `file_id` for the subquery).

5. **Concatenate** batches from `build_file_data_atomic_batches(file_id, project_id, source_code, absolute_path, file_mtime)[0]` **in order** after S3.

6. **Program:** `{"batches": s_batches + fd_batches}` — **flatten** so the outer list is strictly concatenation; **do not** nest file-data batches inside a single outer element.

## RPC execution

- `raw = database.execute_logical_write_operation({"batches": all_batches})`
- Map success/failure into existing `result` dict:
  - On success: `result["success"] = True`, fill `snapshot`, `roots`, `nodes`, `ast_updated`, `cst_updated`, `entities_updated` from `meta` returned by `build_file_data_atomic_batches` and from known counts (`snapshot` = 1, `roots` = 1, `nodes` = len(node_rows)).
  - On failure: set `result["error"]` from exception or RPC error message; **no** rollback calls (server rolled back).

## Error paths

- **Syntax / AST errors** before DB: unchanged (return early with `error` set).
- If `build_file_data_atomic_batches` returns `success: False` (syntax error in source): return that meta as today without RPC.
- **Exception** around `execute_logical_write_operation`: `logger.exception`, set `result["error"]`, return `result`.

## Docstring update

- Update `sync_file_to_db_atomic` docstring **Args** section: replace bullet claiming `begin_transaction` / `execute_batch` / `commit_transaction` with **`execute_logical_write_operation`** (one composite RPC on SQLite client).

## Mandatory validation

```bash
black code_analysis/core/database/file_tree_sync.py
flake8 code_analysis/core/database/file_tree_sync.py
mypy code_analysis/core/database/file_tree_sync.py
pytest tests/test_cst_stable_ids.py tests/test_file_tree_snapshot_fidelity.py tests/test_file_data_batch_integration.py -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If `database` object does not have `execute_logical_write_operation` in tests (mocks), update tests in steps 10–11 — do **not** bypass by using `CodeDatabase` path in production code.

---

## LLAMA-readiness appendix

### Imports to add

```text
from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1
from ..database_client.file_data_batch import build_file_data_atomic_batches
```

(Adjust relative import depth if incorrect — `file_tree_sync` is `code_analysis.core.database`, `file_data_batch` is `code_analysis.core.database_client`.)

**Exact import path from `file_tree_sync.py`:**

```text
from ..database_client.file_data_batch import build_file_data_atomic_batches
```

### Constants

- SQL strings as listed in Snapshot section; no magic numbers.

### Edge cases

- Empty `fd_batches` from builder (syntax error path) already handled before RPC.
- If `node_rows` empty, omit batch S3 entirely.
