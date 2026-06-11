# Atomic step 04: Register `execute_logical_write_operation` in `RPCServer` handler map

## Executor role

`coder_auto`

## Execution directive

Add the RPC method name **`execute_logical_write_operation`** to the `handler_map` in `code_analysis/core/database_driver_pkg/rpc_server.py` so `_process_request` routes it to `self.handlers.handle_execute_logical_write_operation` alongside existing `execute_batch`, `begin_transaction`, etc.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `code_analysis/core/database_driver_pkg/rpc_server.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** step 03 (handler exists on `RPCHandlers`).
- **Blocks:** step 05.

## Read first

- `code_analysis/core/database_driver_pkg/rpc_server.py` (handler_map region, ~lines 500–525)

## Expected file change

- Exactly **one** new entry in `handler_map` dict inside `_process_request` (or equivalent dispatch):

```python
"execute_logical_write_operation": self.handlers.handle_execute_logical_write_operation,
```

## Forbidden alternatives

- Do **not** change routing for `execute_batch`, `begin_transaction`, or `commit_transaction`.
- Do **not** rename the RPC string to something other than `execute_logical_write_operation` without updating parent tactical doc (out of scope — **use exact name**).

## Atomic operations

1. Locate `handler_map = {` in `rpc_server.py`.
2. Insert the key-value pair above in alphabetical order **if** the dict is sorted; **if** not sorted, place immediately after `"execute_batch"` for readability.

## Mandatory validation

```bash
black code_analysis/core/database_driver_pkg/rpc_server.py
flake8 code_analysis/core/database_driver_pkg/rpc_server.py
mypy code_analysis/core/database_driver_pkg/rpc_server.py
pytest tests/test_rpc_server.py tests/test_driver_rpc_server.py -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If tests assert exhaustive method lists, update those tests in step 09 — report failure if unexpected.

## Handoff package

- RPC method string: `execute_logical_write_operation`
