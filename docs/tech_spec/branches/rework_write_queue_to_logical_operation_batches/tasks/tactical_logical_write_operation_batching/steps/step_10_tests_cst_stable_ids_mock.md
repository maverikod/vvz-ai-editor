# Atomic step 10: Tests — update `test_cst_stable_ids` DB mock for logical write

## Executor role

`coder_auto`

## Execution directive

Update `tests/test_cst_stable_ids.py` helper **`_make_db_mock_for_sync`** so it mocks **`execute_logical_write_operation`** instead of **`begin_transaction` / `execute_batch` / `commit_transaction` / `rollback_transaction`** to match the refactored `sync_file_to_db_atomic` implementation. Preserve the **external behavior** expected by tests that call `sync_file_to_db_atomic` indirectly: return values must still allow **`sync_file_to_db_atomic`** to conclude **`success: True`** when the test expects success.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_cst_stable_ids.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** step 07.

## Read first

- `tests/test_cst_stable_ids.py` (`_make_db_mock_for_sync`, tests using it)
- `code_analysis/core/database/file_tree_sync.py` (post-step-07 success conditions)

## Mock specification (prescriptive)

1. Remove or stop using mocks for: `begin_transaction`, `commit_transaction`, `rollback_transaction`, and the **old** `execute_batch` **on the sync mock** (`_make_db_mock_for_sync` only).
2. Set `db.execute_logical_write_operation = MagicMock(...)` with `return_value` shaped like a successful client extraction:
   - Return a `dict` that `sync_file_to_db_atomic` can treat as success — mirror what **`DatabaseClient.execute_logical_write_operation`** returns after `_extract_result_data`: **minimum** `{"success": True, "data": {"batch_results": []}}` or non-empty `batch_results` if code checks length (read `file_tree_sync.py` after step 07 and match **exact** keys accessed).
3. **`side_effect` (if needed):** If `sync_file_to_db_atomic` reads `batch_results` to validate snapshot insert, return enough fake `lastrowid` entries in the nested structure to satisfy any logic — **read `file_tree_sync.py`** after step 07: if it **does not** inspect RPC results for snapshot ids (subquery-based), return minimal `{"success": True}`.

## Algorithm for coder

1. Grep `sync_file_to_db_atomic` for `execute_logical_write_operation` result usage.
2. Configure mock return to satisfy those branches only.

## Forbidden alternatives

- Do **not** change assertions in unrelated tests unless they fail for mock shape reasons.

## Mandatory validation

```bash
black tests/test_cst_stable_ids.py
flake8 tests/test_cst_stable_ids.py
pytest tests/test_cst_stable_ids.py -v
pytest -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If any test still calls `begin_transaction` on mock, update test expectations — the mock should **not** expect those calls.

---

## LLAMA-readiness appendix

### Edge cases

- If `save_tree_to_file` path uses `_make_db_mock()` instead of `_make_db_mock_for_sync`, update only the helper used by failing tests.
