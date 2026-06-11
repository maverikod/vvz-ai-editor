<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task: implementation_plan Step 17 + parent repair_cst_save_tree_persist_logging_path (repeat-save scope).
-->

# Tactical Task: Step 17 — Repeat guarded save timeout / availability

## Purpose

After Step 16, the first guarded `cst_save_tree` can succeed, but repeated guarded saves degrade into MCP timeout / `SERVER_UNAVAILABLE`. This task treats **repeat-save degradation** as the primary server-side issue: narrow the cause using existing save-path diagnostics, apply the smallest bounded repair if justified, commit, and revalidate **multiple** guarded saves on `vast_srv` via `tester_ca` only.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_cst_save_tree_persist_logging_path.md`
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`
- `docs/tech_spec/implementation_plan.md` (Step 17)

## Scope

**Included:** Server-side factors for `cst_save_tree` repeat invocations — command scheduling, worker/RPC timeouts, DB sync duration, adapter-side limits that surface as timeout/unavailable; minimal repair; git commit; `tester_ca` **repeated** `cst_load_file` → `cst_save_tree` (or equivalent) on `vast_srv`.

**Excluded:** Broad `vast_srv` backlog fixes; treating `SERVER_NOT_FOUND` as primary; direct `test_data/vast_srv` access except via `tester_ca`.

## Boundaries

- Narrow: repeat-save timeout / availability after the original LogRecord/instrumentation work.
- `coder_auto` / `tester_auto` must not touch guarded `vast_srv` code.

## Dependencies

- Step 16 repair + instrumentation complete (narrative).

## Parallelization note

Research → code (if any) → `tester_ca` multi-save revalidation — serialized.

## Expected outcome

- Concrete root cause or narrowest blocker for repeat-save degradation.
- If repaired: commit hash + message; `tester_ca` reports whether repeated saves are stable.

## Correction items

- None until `researcher_code` reports gaps vs intent.

## Questions/escalation rule

- Escalate to global orchestrator if MCP proxy / mTLS / client timeout policy must change outside this repo, or if `tech_spec` must change.

## File inventory

- To be filled from `researcher_code` / `coder_auto` for this batch.

## Specialist routing

- `researcher_code`: trace timeout/unavailability chain (MCP adapter, server command executor, `cst_save_tree` duration, DB worker).
- `coder_auto`: bounded server-side repair only if research justifies.
- `tester_ca`: MCP-only repeated save sequence on `vast_srv`.

## Branch execution log (Step 17 batch)

- **`researcher_code`:** Classified repeat-save failure as **adapter 30s** (`mcp-proxy-adapter`, not vendored here) **plus** in-repo **`DatabaseClient`/`RPCClient` 30s** and **sqlite_proxy `command_timeout` 30s**; serialized RPC queue can extend wall time; `sync_file_to_db_atomic` full rewrite each save.
- **`coder_auto`:** Commit **`9c8c046`** — `DatabaseClient(..., timeout=DEFAULT_REQUEST_TIMEOUT)` (300s) in `base_mcp_command_open_db.py`; `config.json` `worker_config.command_timeout` → **300.0**.
- **`tester_ca`:** After deploy attempt, **only first** `cst_save_tree` succeeded; second → **`SERVER_UNAVAILABLE`**; then **`Connection refused`** on DB/worker socket — **≥3 sequential successes not achieved**. Orchestrator note: restart server to load `config.json`; **`mcp-proxy-adapter`** may still cap MCP calls at ~30s if that layer unchanged.

### Post-restart revalidation (follow-up batch)

- **`tester_auto`:** `server_manager_cli --config config.json restart` → exit **0**, **`started pid=1043785`**; `status` → **`running pid=1043785`**; config **`/home/vasilyvz/projects/tools/code_analysis/config.json`** (cwd-relative `config.json`).
- **`tester_ca`:** `health` **PID 1043785** (matches), version **6.9.116**. **`vast_srv`** `cst_load_file` → **three sequential** `cst_save_tree` (**same `tree_id`**) — **all success**; early stop at 3/3 consecutive successes. **No** timeout, socket refusal, or proxy visibility loss in this session.

### Transient retry batch + mandatory restart + revalidation (`86fad0d`)

- **`coder_auto`:** `code_analysis/core/database_client/transient.py` — **`MAX_TOTAL_ELAPSED_SECONDS` 5.0 → 120.0**; commit **`86fad0d2d8eb2bfa2e9155a9ca3c4312ecf9210d`** (`fix(db): raise transient retry budget to 120s for cst_save_tree`).
- **`tester_auto`:** `server_manager_cli restart` → **PID 1071599**, config **`/home/vasilyvz/projects/tools/code_analysis/config.json`**.
- **`tester_ca`:** Proxy needed **`reload_config`** once (`SERVER_NOT_FOUND` before reload). **Run A:** save1 OK → attempt2 **`SERVER_UNAVAILABLE`** → attempt3 **socket refusal** → attempt4 OK. **Run B:** attempt1 **`SERVER_UNAVAILABLE`** → after **~120s** wait → **four** consecutive **`cst_save_tree`** successes (same `tree_id`). **Intermittent** proxy/transport flakiness remains; not a clean 4/4 cold streak without backoff.
