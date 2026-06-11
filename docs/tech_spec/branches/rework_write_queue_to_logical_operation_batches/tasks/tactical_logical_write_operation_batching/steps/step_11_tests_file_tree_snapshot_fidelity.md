# Atomic step 11: Tests — update `test_file_tree_snapshot_fidelity` patches

## Executor role

`coder_auto`

## Execution directive

Update `tests/test_file_tree_snapshot_fidelity.py` so all `patch` targets and mock objects for `sync_file_to_db_atomic` remain valid after step 07. Specifically, if any test mocks **`begin_transaction`**, **`execute_batch`**, or **`commit_transaction`** on the database object passed into `sync_file_to_db_atomic`, replace those expectations with **`execute_logical_write_operation`** (or remove obsolete assertions on call counts for removed methods).

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_file_tree_snapshot_fidelity.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** step 07.

## Read first

- Full `tests/test_file_tree_snapshot_fidelity.py`
- `code_analysis/core/database/file_tree_sync.py` (current sync implementation)

## Atomic operations

1. `rg "begin_transaction|execute_batch|commit_transaction" tests/test_file_tree_snapshot_fidelity.py` — for each hit, update to logical-write mock or remove.
2. Ensure patched `sync_file_to_db_atomic` tests still validate snapshot fidelity (node IDs / structure) — **do not** weaken assertions unless behavior is genuinely unchanged.

## Forbidden alternatives

- Do **not** skip entire test modules.

## Mandatory validation

```bash
black tests/test_file_tree_snapshot_fidelity.py
flake8 tests/test_file_tree_snapshot_fidelity.py
pytest tests/test_file_tree_snapshot_fidelity.py -v
pytest -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If fidelity tests require real DB RPC, follow existing fixture patterns; do not convert to integration tests without noting in handoff.

---

## LLAMA-readiness appendix

### Test expectations

- All tests in `test_file_tree_snapshot_fidelity.py` pass with same semantic coverage as before refactor.
