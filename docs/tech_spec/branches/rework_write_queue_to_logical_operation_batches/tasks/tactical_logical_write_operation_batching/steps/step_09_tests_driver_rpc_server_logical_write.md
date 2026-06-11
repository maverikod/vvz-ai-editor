# Atomic step 09: Tests — RPC server routes `execute_logical_write_operation`

## Executor role

`coder_auto`

## Execution directive

Add or extend tests in **`tests/test_driver_rpc_server.py`** (prefer this file if it already starts `RPCServer` with `RequestQueue`) to verify that an RPC request with **`method`: `"execute_logical_write_operation"`** reaches the handler and returns **`batch_results`** with length equal to the number of inner batches. If **`tests/test_driver_rpc_server.py`** has no suitable harness, use **`tests/test_rpc_server.py`** instead — **pick exactly one target file** based on which file already imports `RPCServer` and sends raw RPC requests.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_driver_rpc_server.py` **or** `tests/test_rpc_server.py` (choose one — **must be stated in the commit**; default preference: `tests/test_driver_rpc_server.py` if it contains driver-level integration tests)
- **action:** `modify`

## Dependency contract

- **Depends on:** steps 03–04.

## Read first

- Chosen test file (first 120 lines + any `RPCServer` test)
- `code_analysis/core/database_driver_pkg/rpc_server.py` (request envelope shape)

## New test name (pattern)

`test_execute_logical_write_operation_handler_batch_results_length`

### Algorithm

1. Start server + driver + queue using same fixture pattern as existing tests in the chosen file.
2. Send a request invoking `execute_logical_write_operation` with `params={"batches": [[{sql, params}, ...], ...]}` matching wire format from step 05.
3. Assert HTTP/socket response has **success** and `batch_results` list length **2** when two inner batches provided.
4. Use trivial SQL against a temp table created in fixture (same approach as other tests).

## Forbidden alternatives

- Do **not** add a second target file.

## Mandatory validation

```bash
black <chosen test file>
flake8 <chosen test file>
pytest tests/test_driver_rpc_server.py -q
# OR
pytest tests/test_rpc_server.py -q
pytest -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If raw RPC envelope is hard to construct, use `DatabaseClient` from step 08 only as **secondary** assertion — **prefer** direct server test without DatabaseClient if existing patterns exist.

---

## LLAMA-readiness appendix

### Decision rule (fixed)

- Open `tests/test_driver_rpc_server.py`; if it contains **zero** `RPCServer` usages, use `tests/test_rpc_server.py` instead.
