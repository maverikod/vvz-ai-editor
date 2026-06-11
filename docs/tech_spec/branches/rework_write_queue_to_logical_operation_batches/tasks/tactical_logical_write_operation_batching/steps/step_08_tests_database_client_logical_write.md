# Atomic step 08: Tests — `DatabaseClient.execute_logical_write_operation`

## Executor role

`coder_auto`

## Execution directive

Extend `tests/test_database_client.py` with a test that starts the existing **in-process `RPCServer` + sqlite driver** fixture (same pattern as `test_execute_batch` or nearest equivalent), calls **`DatabaseClient.execute_logical_write_operation`** with a **minimal** valid program of **two** inner batches (each inner batch has **one** `INSERT`), then asserts the database file contains both inserted rows after the call. Assert **`rpc_client.call` count** for the logical op path: use **one** client method invocation only (implicitly one RPC for the logical op — do not mock unless needed).

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_database_client.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** steps 01–05.

## Read first

- `tests/test_database_client.py` (fixtures `rpc_server`, any `execute_batch` test)
- `code_analysis/core/database_client/client_operations.py` (`execute_logical_write_operation`)

## New test function (exact name)

```python
def test_execute_logical_write_operation_two_batches_inserts_two_rows(self, rpc_server):
```

### Test algorithm

1. Use existing `rpc_server` fixture to get `socket_path` and `db_path`.
2. `client = DatabaseClient(socket_path); client.connect()`.
3. Build `program = {"batches": [[("INSERT INTO test_table ...", (...))], [("INSERT INTO test_table ...", (...))]]}` using the **same** `test_table` schema as other tests in this file (reuse table from fixture).
4. `result = client.execute_logical_write_operation(program)` — unwrap success the same way as other tests assert on `execute_batch`.
5. Query via `client.select("test_table", ...)` or `execute` to verify **row count == 2** with expected values.
6. `client.disconnect()`.

### Assertions

- No exception from `execute_logical_write_operation`.
- DB reflects two rows.

## Forbidden alternatives

- Do **not** call `begin_transaction` in the test for this scenario.

## Mandatory validation

```bash
black tests/test_database_client.py
flake8 tests/test_database_client.py
pytest tests/test_database_client.py::TestDatabaseClient::test_execute_logical_write_operation_two_batches_inserts_two_rows -v
pytest -q
```

**Completion:** full `pytest -q` passes.

## Blackstops

- If `test_table` is not visible in fixture scope, create rows in an isolated temp DB using the same fixture pattern as `test_execute_batch` — read that test for copy-paste baseline.

---

## LLAMA-readiness appendix

### Imports

- Reuse existing imports from `tests/test_database_client.py`; add none unless pytest or client imports missing.

### Edge cases

- If `TestDatabaseClient` class has no slot for new test, append method inside the class.
