<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task: implementation_plan Step 18 — post-`cst_modify_tree` first `cst_save_tree` fail → socket refusal.
-->

# Tactical Task: Step 18 — `cst_modify_tree` success → first `cst_save_tree` fail → socket refused

## Purpose

Guarded workflow reaches a healthy state; full `FunctionDef` replacement via `cst_modify_tree` succeeds in memory; the **very next** `cst_save_tree` is the first failing command; the path then degrades into **socket refusal** (not primarily `SERVER_NOT_FOUND`). This task **investigates and repairs** that **exact transition** as a dedicated server-side failure path: narrow cause using save-path diagnostics and lower-role investigation, apply the **smallest** bounded server repair if justified, **git commit**, and **revalidate** the exact transition on the guarded `vast_srv` harness via **`tester_ca` only**.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_cst_save_tree_persist_logging_path.md`
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`
- `docs/tech_spec/implementation_plan.md` (Step 18)

## Scope

**Included:** Server-side code path from successful in-tree `cst_modify_tree` through **first** `cst_save_tree` (persist, atomic write, backup, DB sync, logging); any crash/OOM/exception that closes the listen socket or worker DB socket; minimal repair; one git commit after the repair batch; **`tester_ca`** sequence: healthy harness → `cst_load_file` → `cst_modify_tree` (full `FunctionDef` replacement as in reproduction) → **first** `cst_save_tree` → confirm stability (no immediate socket refusal).

**Excluded:** Broad proxy/mTLS refactors; treating `SERVER_NOT_FOUND` as primary; broad `vast_srv` backlog fixes; **Step 17** repeat-save-only scope unless research proves overlap; direct access to `test_data/vast_srv` except via **`tester_ca`**.

## Boundaries

- `vast_srv` is **verification harness only**.
- **`coder_auto`** / **`tester_auto`** must **not** touch guarded `vast_srv` code.
- Guarded `vast_srv` access **only** through **`tester_ca`** (MCP → `code-analysis-server`).
- Narrower than general save-path or proxy work: **immediate** transition after successful in-memory modify to failing save and follow-on refusal.

## Dependencies

- Step 17 narrative satisfied where applicable; entry condition matches user description (healthy → modify OK → first save fails → refusal).

## Parallelization note

**Serialized:** `researcher_code` → `coder_auto` (if repair justified) → **`tester_ca`** revalidation. No parallel code + harness verification.

## Expected outcome

- Narrowest root cause or blocker classification for this transition (with file/symbol evidence from `researcher_code`).
- If repaired: commit hash + message; substantive production change beyond comments verified by specialist evidence.
- **`tester_ca`** verdict: whether post-`cst_modify_tree` save transition is **stable** after repair.

## Correction items

- None until `researcher_code` / `tester_ca` report gaps.

## Questions/escalation rule

- Escalate to global orchestrator if MCP proxy adapter hard timeout, OS resource limits, or **tech_spec** / global-step boundary change is required; or if root cause is **outside** `code_analysis` server process.

## File inventory

- To be filled from `researcher_code` / `coder_auto` delivery for this batch (expect handlers for `cst_modify_tree`, `cst_save_tree`, tree saver / atomic persist / DB client).

## Specialist routing

- **`researcher_code`:** Trace call chain after in-memory modify success through first save; correlate with unified logging / diagnostics from save path; identify exception types, worker exit, or resource exhaustion that could yield socket refusal.
- **`coder_auto`:** Smallest server-side repair + commit if research justifies; **no** `test_data/vast_srv` direct edits.
- **`tester_ca`:** MCP-only `vast_srv` reproduction sequence and post-repair revalidation.

## Branch execution log (Step 18 batch)

- **`researcher_code`:** Traced `cst_modify_tree` → in-memory `CSTTree` → `cst_save_tree` → `save_tree_to_file` → `sync_file_to_db_atomic` → `DatabaseClient`/`RPCClient` Unix socket. Step 16 diagnostics: grep `cst_save_stage`, `error_before_restore`, `[CHAIN] rpc_client`. Classification: first save can return `success: False` without crashing; **socket refusal** aligns with **DB RPC peer down / connect refused**, not `SERVER_NOT_FOUND`.
- **`coder_auto`:** Commit **`b412d71`** — `fix(cst_save_tree): retry RPC connect-refused embedded in save result`. Added `is_rpc_connect_refused_message` / `_connection_refused_in_text` in `transient.py`; in `CSTSaveTreeCommand.execute`, retry when save **result** embeds connection-refused text (same budget as other transient paths). Tests: `tests/test_cst_save_tree_command.py` (8 passed per coder). Files: `code_analysis/core/database_client/transient.py`, `code_analysis/commands/cst_save_tree_command.py`, `tests/test_cst_save_tree_command.py`.
- **`tester_ca` (`vast_srv`):** `project_id` `c86dded6-6f93-4fb0-be54-b6d7b739eeb9`, file `add_full_queue_support/queue_helpers.py`. `cst_modify_tree` full `FunctionDef` replace **OK**; **first** `cst_save_tree` → **`SERVER_UNAVAILABLE`**; retry → **`Connection refused`** on socket; subsequent `cst_load_file` **failed** same; **`health`** still **OK** (PID unchanged). **Verdict: transition not stable** in this session — CST/socket path broken while health reports up; **restart** to load new code + recover IPC recommended before another harness pass.
- **Post-restart revalidation (HEAD `b412d71`, PID `1065239`):** **`tester_auto`** `server_manager_cli restart` → PID **`1065239`**; `git rev-parse HEAD` matches **`b412d718be1f921e3881d5bd61ed4f86eea4dd57`**. **`tester_ca`:** `health` **`pid` `1065239`** (matches restarted process). **`cst_modify_tree`** (full `FunctionDef` replace) **OK**; **first** `cst_save_tree` **`success: true`** (backup + `tree_reloaded`). **Exact transition modify → first save: PASS.** **First failing command in extended trace:** **second** `cst_save_tree` → **`SERVER_UNAVAILABLE`**; then `cst_load_file` / `list_projects` → **`Connection refused`**; **`health`** still OK / same PID. (Repeat-save / post-save degradation remains outside the original “first save fails” boundary.)
