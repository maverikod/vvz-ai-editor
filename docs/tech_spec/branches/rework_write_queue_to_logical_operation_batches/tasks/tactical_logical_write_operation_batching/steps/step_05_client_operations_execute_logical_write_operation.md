# Atomic step 05: `DatabaseClient.execute_logical_write_operation`

## Executor role

`coder_auto`

## Execution directive

Add `execute_logical_write_operation(self, program: LogicalWriteProgramV1) -> dict[str, Any]` to `_ClientOperationsMixin` in `code_analysis/core/database_client/client_operations.py`. It must perform **exactly one** `self.rpc_client.call("execute_logical_write_operation", rpc_params)` where `rpc_params` serializes `program` for the server parser in step 02.

## Parent links

- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`
- Tech spec: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `code_analysis/core/database_client/client_operations.py`
- **action:** `modify`

## Dependency contract

- **Depends on:** steps 01, 04 (types + RPC route exist).
- **Blocks:** steps 06–07.

## Read first

- `code_analysis/core/database_client/client_operations.py` (`execute_batch` method — copy serialization pattern for `operations`)
- `code_analysis/core/database/logical_write_program.py`

## Expected file change

- Add imports: `LogicalWriteProgramV1` from `code_analysis.core.database.logical_write_program`
- Add method on `_ClientOperationsMixin` only.

## Method signature (exact)

```python
def execute_logical_write_operation(
    self, program: LogicalWriteProgramV1
) -> dict[str, Any]:
```

## Algorithm

1. Read `batches = program.get("batches")` — if missing or not a list or empty, raise `ValueError("LogicalWriteProgramV1 requires non-empty batches")` **before** RPC (tactical error table: invalid shape → ValueError on client).
2. Build `rpc_batches: list[list[dict[str, Any]]]`:
   - For each inner batch (list of `(sql, params)` tuples):
     - For each `(sql, params)`:
       - Append `{"sql": sql, "params": list(params) if params is not None else None}` to match **`execute_batch`** wire format per operation.
3. `rpc_params: dict[str, Any] = {"batches": rpc_batches}`.
4. If `program.get("defer_constraints") is True`, set `rpc_params["defer_constraints"] = True`.
5. `logger.info` line: `[CHAIN] client execute_logical_write_operation n_batches=%s` with `len(r_batches)`.
6. `response = self.rpc_client.call("execute_logical_write_operation", rpc_params)`.
7. `return self._extract_result_data(response)` (same as `execute_batch` return handling — caller receives inner result dict).

## Error handling

- Propagate `RPCClientError` / `RPCResponseError` from `rpc_client.call` (do not catch).
- Client-side `ValueError` only for step 1 validation.

## Return value

- Same shape as other operations using `_extract_result_data` — typically `dict` with `success` and nested `data` containing `batch_results` from server.

## Forbidden alternatives

- Do **not** call `begin_transaction` / `execute_batch` / `commit_transaction` from this method.
- Do **not** split into multiple RPC calls.

## Mandatory validation

```bash
black code_analysis/core/database_client/client_operations.py
flake8 code_analysis/core/database_client/client_operations.py
mypy code_analysis/core/database_client/client_operations.py
pytest tests/test_database_client.py -q
```

**Completion:** `pytest -q` passes.

## Blackstops

- If `TypedDict` import causes circular imports, import `LogicalWriteProgramV1` under `TYPE_CHECKING` **only if** mypy requires — prefer direct import first.

## Handoff package

- Method name `execute_logical_write_operation` and RPC string `execute_logical_write_operation`.

---

## LLAMA-readiness appendix

### Complete import list (delta)

```text
from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1
```

(Keep `from __future__ import annotations` and existing imports unchanged except additions.)

### Constants

- RPC method literal: `"execute_logical_write_operation"`

### Edge cases

- `defer_constraints` omitted → do not add key to `rpc_params` (server treats as false).
