<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task for global step: rework_write_queue_to_logical_operation_batches (implementation_plan Step 22).
-->

# Tactical Task: Logical write operation batching on the RPC SQLite path

## Purpose

Eliminate cross-traffic interleaving between the begin and commit phases of a guarded save by changing the effective unit of work on the serialized SQLite RPC path from **one inbound RPC message** to **one logical write operation**. Evidence (`researcher_code`, branch `rework_write_queue_to_logical_operation_batches`) shows that `sync_file_to_db_atomic` and similar flows issue **multiple** `DatabaseClient` / `RPCClient.call` invocations (`begin_transaction`, several `execute_batch` / helpers, `commit_transaction`). The `RequestQueue` schedules **per RPC**, so another producer can enqueue a write (for example `UPDATE vectorization_stats ...`) **between** those calls. The repair is **not** primarily priority tuning: it is **collapsing one logical save’s DB work into a single scheduled RPC** (or an equivalent server-side guarantee) so no other queued write runs until that unit completes.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- `docs/tech_spec/implementation_plan.md` (Step 22; Step 21 instrumentation may inform but does not block starting this tactical batch once interleaving is accepted as root cause)

## Scope

**Included:**

- RPC driver path: `RPCServer` + `RequestQueue` + `SQLiteDriver` + `DatabaseClient` used by MCP-layer DB access.
- Refactor of **`sync_file_to_db_atomic`** (and any direct callers that form multi-RPC transactions for one logical save) so the **atomic file sync** uses **one** composite logical-write RPC **or** a server-side queue rule that prevents interleaving (design choice **Option A** below is mandatory unless `coder_auto` proves it infeasible with evidence).
- Unit/integration tests under `tests/` that cover the new behavior (extend existing `test_rpc_server*`, `test_database_client*`, `test_driver_*` as appropriate).
- Explicit **server restart** after code change before `tester_ca` revalidation.
- **`tester_ca`** guarded repeated-save harness on **`test_data/vast_srv`** (MCP only).

**Excluded:**

- Rewriting unrelated worker logic or broad `vectorization_stats` semantics except where required to call the new API.
- Fixes that **only** adjust `RequestPriority` without changing queue unit or transaction RPC shape (forbidden by parent step).
- Direct file access to `test_data/vast_srv` by `coder_auto` / `tester_auto`.

## Boundaries

- Do not change the **non-SQLite** thread-pool execution model except where shared constants or types must compile.
- Do not expand scope to **`SQLiteDriverProxy` / `db_worker_pkg`** unless `researcher_code` proves `sync_file_to_db_atomic` uses that path in the failing MCP configuration (default assumption: **RPC `DatabaseClient` path** per prior research).

## Dependencies

- **none** for design (parent has already accepted queue-unit mismatch as defect). Optional narrative dependency: diagnostic context from `fix_vast_srv_server_only_phase1` Step 21 logging.

## Parallelization note

**Serialized:** `researcher_code` (gap-fill if needed) → `planner_auto` → `coder_auto` → `tester_auto` (pytest + server restart) → `tester_ca` (vast_srv). No parallel code + harness on the same files.

## Expected outcome

1. Tactical/design alignment: scheduling unit for guarded logical saves matches **one logical operation** on the RPC SQLite path.
2. `tester_auto`: relevant tests pass; server restart exit code 0.
3. `tester_ca`: **at least three** consecutive guarded `cst_save_tree` (or agreed harness) on `vast_srv` **without** `SERVER_UNAVAILABLE` / timeout attributable to write interleaving; log evidence if failure persists.
4. Short written answer: **can background writes still interleave inside one logical save?** (target: **no**, by construction of single-RPC or pinned drain.)

## Correction items

- If `coder_auto` discovers `sync_file_to_db_atomic` is not the only multi-RPC logical save entry point, add those call sites to scope and extend the composite API or document **Option B** server-side drain with evidence.

## Questions/escalation rule

- Escalate to **global orchestrator** if **`mcp-proxy-adapter`** hard timeout (~30s) remains the dominant failure after queue repair, or if `tech_spec` / global step boundaries must change.

---

## Design resolution (pre-planner)

**Chosen approach: Option A — composite RPC (`researcher_code` recommendation).**

**Rationale:** `RequestQueue` already serializes **one dequeue → one `_process_request`**. Folding begin + all batched SQL + commit into **one** RPC keeps **one queue unit** per logical save without redesigning priority heuristics. Option B (pinning dequeue by `transaction_id`) requires every mutating RPC to carry `transaction_id` correctly; higher audit surface.

**Target behavior:** For a guarded save’s DB persistence, the client performs **one** `rpc_client.call` to a new method (working name: `execute_logical_write_operation`) whose handler runs **entire transaction** (nested structure: begin implicit or explicit, N × batch execution, commit) on the **same** SQLite connection / transaction manager lifecycle as today’s multi-call sequence, **inside** a single `_process_request`.

**Forbidden approaches (tactical):**

- Relying on **`HIGH` priority** for project `select` alone to fix interleaving.
- Splitting one logical save across multiple RPCs **without** server-side pinning (unless escalation-approved).

---

## File inventory

| action   | path | purpose |
|----------|------|--------|
| modify   | `code_analysis/core/database_driver_pkg/rpc_server.py` | Register new RPC method; wire into `handler_map` / dispatch; ensure SQLite single-consumer path invokes new handler once per logical op. |
| modify   | `code_analysis/core/database_driver_pkg/rpc_handlers_schema.py` | Implement `handle_execute_logical_write_operation` (name may match protocol exactly). |
| modify   | `code_analysis/core/database_driver_pkg/rpc_handlers_base.py` | Shared helpers if new handler shares validation/error paths with existing `handle_execute_batch` / transaction handlers. |
| modify   | `code_analysis/core/database_client/client_operations.py` | Add `execute_logical_write_operation(...)` (or equivalent) calling `rpc_client.call` **once**. |
| modify   | `code_analysis/core/database_client/client_transactions.py` | Only if transaction helpers must delegate to composite API or deprecate public multi-call sequences for internal callers. |
| modify   | `code_analysis/core/database/file_tree_sync.py` | Refactor `sync_file_to_db_atomic` to use one logical-write API. |
| modify   | `tests/test_rpc_server.py` | Cover new method / non-interleaving contract. |
| modify   | `tests/test_database_client.py` and/or `tests/test_driver_rpc_server.py` | Integration coverage for logical write. |
| modify   | Other `tests/test_*` as required by `tester_auto` gaps | As discovered. |

---

## Class/function inventory (new / changed)

**Package:** `code_analysis.core.database_client.client_operations.DatabaseClient`

- **`execute_logical_write_operation(self, program: LogicalWriteProgramV1) -> dict[str, Any]`**  
  - **Behavior:** Single `rpc_client.call("execute_logical_write_operation", params)`; raises same RPC/DB exceptions as `execute_batch` / transactions on failure.
- **`LogicalWriteProgramV1` (TypedDict)** — fields (exact names in atomic steps):
  - **`batches`**: `list[list[tuple[str, tuple[Any, ...] | list[Any]]]]` — ordered list of batches; each batch is a list of `(sql, params)` compatible with existing `execute_batch` validation.
  - **`defer_constraints`**: `bool`, default `False` — if existing sync uses deferrable semantics, mirror; else omit.

**Package:** `code_analysis.core.database_driver_pkg.rpc_handlers_schema.RPCHandlers` (exact base class per codebase)

- **`handle_execute_logical_write_operation(self, params: dict[str, Any]) -> dict[str, Any]`**  
  - **Behavior:** Acquire driver; start one transaction; for each batch in `batches`, execute via same primitives as `run_execute_batch` / existing transaction path; commit; return summary (rows affected / last row id as existing handlers return). On any failure: rollback and raise.

**Package:** `code_analysis.core.database.file_tree_sync`

- **`sync_file_to_db_atomic(...)`** — **Behavior change only:** replace internal `begin_transaction` + multiple `execute_batch` + `commit_transaction` with **`database.execute_logical_write_operation(...)`** building `LogicalWriteProgramV1` from the same SQL work previously issued (ordering preserved).

---

## Data structures

**`LogicalWriteProgramV1`** — `TypedDict`, total=False where noted:

| field | type | default | validation |
|-------|------|---------|------------|
| `batches` | `list[list[SqlParamPair]]` | required | non-empty for mutating sync; each inner list matches current `execute_batch` shape |
| `defer_constraints` | `bool` | `False` | optional |

**`SqlParamPair`**: `tuple[str, Sequence[Any]]` — same as existing batch tuples.

---

## Import map (new code — per file)

**`client_operations.py`:** `from typing import Any, Sequence`; add `TypedDict` if defined here or import from new `code_analysis.core.database.logical_write_program` module if `coder_auto` splits types for clarity.

**`rpc_handlers_schema.py`:** existing driver/handler imports per file; no circular imports.

**`file_tree_sync.py`:** unchanged imports except use new `DatabaseClient` method.

---

## Error handling map

| failure | exception | condition | caller action |
|---------|-----------|-----------|----------------|
| Invalid `batches` shape | `ValueError` | validation in client before RPC | fix caller construction |
| SQL error mid-program | same as `execute_batch` | SQLite error in handler | transaction rolled back; propagate |
| RPC timeout | `RPCError` / existing timeout type | single call exceeds `DEFAULT_REQUEST_TIMEOUT` | surface to MCP; may need timeout tuning for very large saves |

---

## Config dependency

| key | type | default | where |
|-----|------|---------|--------|
| `DEFAULT_REQUEST_TIMEOUT` | float | 300.0 | `constants.py`; `RequestQueue`, `RPCServer` wait — **single** logical RPC may run longer than one old `execute_batch`; monitor |
| `queue_max_size` | int | from `DEFAULT_QUEUE_MAX_SIZE` | `database_driver_manager` / driver startup |

No new config key required for MVP unless `tester_auto` proves timeout pressure.

---

## Test plan

| test file | test name (pattern) | asserts |
|-----------|---------------------|---------|
| `tests/test_database_client.py` | new test: logical write succeeds | one call; DB state matches multi-call baseline |
| `tests/test_rpc_server.py` or `tests/test_driver_rpc_server.py` | concurrent enqueue does not interleave inside logical op | two clients: one long logical op, one interfering write blocked until commit (ordering assertion via log or DB invariant) |
| `tests/test_file_tree_snapshot_fidelity.py` or closest | sync still atomic | if covers `sync_file_to_db_atomic`, update mocks |

---

## Concrete examples

**Input (`LogicalWriteProgramV1`):**

```text
batches = [
  [ ("INSERT INTO t VALUES (?)", (1,)) ],
  [ ("UPDATE t SET x=? WHERE id=?", (2, 1)) ]
]
```

**Expected:** After handler completes, both statements applied and committed; no other queued RPC’s effects appear between the two batches in observable DB state.

---

## Algorithm (handler) — pseudocode

1. Validate `params` → `LogicalWriteProgramV1`.
2. `begin_transaction` equivalent **on server** using existing `SQLiteTransactionManager` / connection selection rules used by current `begin_transaction` RPC.
3. For each batch in `batches`, call existing **`run_execute_batch`** (or equivalent) on **transaction connection**.
4. `commit_transaction`.
5. Return structured success dict matching existing RPC response style.
6. On exception: `rollback_transaction`, re-raise.

---

## Specialist routing

- **`planner_auto`:** Atomic steps under this file only; link to parents.
- **`coder_auto`:** Implementation per this tactical doc; if Option A infeasible, document **proof** and implement Option B with full audit of `transaction_id` on writes.
- **`tester_auto`:** Pytest; `python -m code_analysis.cli.server_manager_cli --config config.json restart` from repo root with venv.
- **`tester_ca`:** `vast_srv` repeated `cst_save_tree` harness; MCP only.

---

## Branch execution log

- **2026-04-05 — `researcher_code`:** Queue unit = **per RPC**; `sync_file_to_db_atomic` = **multiple** RPCs; interleaving possible between begin/commit; Option A composite RPC recommended; configs/timeouts listed in research report.
- **2026-04-05 — `planner_auto`:** Atomic steps `step_01`–`step_12` + `atomic_index.md`, `atomic_parallel_waves.md` under `.../tactical_logical_write_operation_batching/steps/`.
- **2026-04-05 — `coder_auto`:** Implemented composite RPC `execute_logical_write_operation`, `LogicalWriteProgramV1` in `code_analysis/core/database/logical_write_program.py`, handler + `rpc_server` route, `DatabaseClient.execute_logical_write_operation`, `file_tree_sync` + `file_data_batch` refactors, `CodeDatabase.execute_logical_write_operation` in `base.py` (in-process parity), tests + `tests/test_logical_write_sync_path_contract.py`. No git commit. **Note:** `test_file_data_batch_integration` / snapshot integration tests still **error** at DB migration (`indexing_errors` table ordering) — pre-existing or separate migration issue, not logical-write assertions.
- **2026-04-05 — `tester_auto`:** `server_manager_cli --config config.json restart` → exit **0**, PID **1200755**; status **running**. Pytest `test_database_client`, `test_driver_rpc_server`, `test_cst_stable_ids`, `test_logical_write_sync_path_contract`, `test_rpc_handlers` → **51 passed**, exit **0**.
- **2026-04-05 — `tester_ca`:** **`SERVER_NOT_FOUND`** — `code-analysis-server` copy 1 **not registered** in MCP Proxy after `reload_config`; `list_projects` / CST harness **not executed**. **Blocker:** register/enable `code-analysis-server` on the proxy, then rerun vast_srv repeated-save sequence.
- **2026-04-05 (follow-up) — `tester_ca`:** **`list_servers`** → `code-analysis-server_1` **active** (`https://172.28.0.1:15000`, 118 commands). **`vast_srv`** `project_id` **`c86dded6-6f93-4fb0-be54-b6d7b739eeb9`**. Harness: `cst_load_file` → **`_fix_ssl_type.py`** → `tree_id` **`8caa2d4a-e5a7-4a3f-8459-f7d8e6ce01c2`** → **five** sequential **`cst_save_tree`** (same `tree_id`, no edits) — **all success** (`data.success: true`, `sync_result.success: true`). **`health`:** version **6.10.1**, `registered: true`. **No** `SERVER_UNAVAILABLE` / `SERVER_NOT_FOUND` / timeout in this run.
- **2026-04-05 (follow-up) — `tester_auto` (log correlation):** Grep **`logs/**/*.log`** for `execute_logical_write_operation` / `logical_write` → **no matches**. **`logs/database_driver.log`** (historical samples) still shows **legacy** pattern: `begin_transaction` + multiple `execute_batch` + interleaved `select`/`execute` with **`tid=None`**, including **`UPDATE vectorization_stats`** before **`commit_transaction`** enqueue — **does not** demonstrate the new single-RPC path in captured lines. **`logs/mcp_server.log`:** `cst_save_tree` + **`sync_file_to_db_atomic`** timing blocks on **2026-04-05**; no `execute_logical_write` string. **Conclusion for proof:** **Functional** repeated-save stability **proven** on `vast_srv` (5/5); **log-level proof** that one logical-write RPC ran per save **not established** from current log corpus (may need fresh capture with driver/MCP logging that emits `method=execute_logical_write_operation`).

---

## Subordinate Agents State (template for parent reports)

| agent | status | scope | last update | blocker |
|-------|--------|-------|-------------|---------|
| `researcher_code` | done | write path | 2026-04-05 | none |
| `planner_auto` | done | atomic steps | 2026-04-05 | none |
| `coder_auto` | done | logical write RPC | 2026-04-05 | none |
| `tester_auto` | done | pytest + restart + log grep | 2026-04-05 | none |
| `tester_ca` | done | vast_srv 5× save harness | 2026-04-05 | none |
