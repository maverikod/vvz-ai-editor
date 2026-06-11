<!--
Tactical task — parent global step: fix_vast_srv_server_only_phase1
-->

# Tactical Task: vast_srv server-only Phase 1 — first fix batch

## Purpose

Execute the first bounded fix batch on `vast_srv` using only `code-analysis-server` (MCP), prioritizing explicit errors over unfinished code and duplicates, after the repaired analysis workflow is confirmed.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Scope

**Included:** MCP-only reads/writes on `vast_srv`; `comprehensive_analysis` / `lint_code` / `type_check_code` / CST commands for fixes; reporting fixed vs remaining backlog.

**Excluded:** Direct repo tools on `test_data/vast_srv`; `coder_auto` / `tester_auto` touching `vast_srv`; unbounded refactors.

## Boundaries

- All guarded `vast_srv` paths: **tester_ca** only.
- Server defects: stop batch, route repair to **coder_auto** (this repo, not `vast_srv`), then resume MCP checkpoint.

## Dependencies

none (enters from revalidated C2 / summary-counting repair).

## Parallelization note

Serial: backlog pull → fixes → lint verify.

## Expected outcome

At least one concrete backlog item fixed with server commands; remaining backlog and blockers documented; workflow integrity stated.

## Correction items

none

## Questions/escalation rule

If CST replace clobbers parent nodes or compose validation blocks legitimate edits, escalate server-side fix to global orchestrator / **coder_auto**.

---

## Execution record (tester_ca evidence)

- **Entry:** `health` OK; `comprehensive_analysis_98ea9ab6` completed, `success: true`, summary `files_total` 598, trust keys consistent with skip-all incremental pass; no `COMPREHENSIVE_ANALYSIS_ERROR`.
- **Batch scope:** (1) `ai_admin/auth/git_auth_manager.py` — explicit flake8 E128; (2) `add_fallback_logic.py` — explicit F821 / f-string bug — **not completed** (tooling).
- **Fixed:** `git_auth_manager.py` — `format_code` (Black) cleared E128; `lint_code` 0 errors; `type_check_code` still 2 pre-existing mypy issues.
- **Blocked:** `add_fallback_logic.py` — unsafe `cst_modify_tree` replace on `Param`/`Name`; `query_cst` partial replace damaged structure (restored via `restore_backup_file`); `compose_cst_module` failed project validation.
- **Remaining backlog:** `add_fallback_logic.py` lint/mypy still failing; 139 long files in comprehensive snapshot; sample mypy on `git_auth_manager.py`.

## File inventory (vast_srv, via server)

| action | path (project-relative) |
|--------|-------------------------|
| modify | `ai_admin/auth/git_auth_manager.py` |
| restore | `add_fallback_logic.py` (backup after failed edit) |

## Checkpoint

**Next batch:** Unblock `add_fallback_logic.py` via **server CST repair** (`coder_auto`) or a **single safe `query_cst` full-function replace** with preview; then continue explicit-error queue. **Workflow:** MCP-only for `vast_srv` preserved for completed work.

---

## Continuation batch — `add_fallback_logic.py` explicit errors (post-CST repair)

**tester_ca evidence (follow-up):**

- **Scope:** `add_fallback_logic.py` only; explicit **E265**, **E402**, invalid **mypy** directive, **E303** (via format).
- **Fixed:** Removed bogus shebang-as-comment and preamble so imports follow docstring; removed invalid `# mypy: ignore-errors` line; **`lint_code` → 0** after `format_code`. **`cst_save_tree`** backup `076d9957-b093-4dad-9002-f1574a26b4e2`.
- **Remaining:** **`type_check_code`** → **1** × **`no-untyped-def`** on `add_fallback_logic_to_file` (~L18). Blocked under strict MCP-only: **`replace_file_lines`** rejected (**`USE_CST_COMMANDS`**); fragment **`cst_modify_tree`** on signature rejected (**`INVALID_OPERATION`**); full **`FunctionDef` replace** preview showed unsafe escape/brace drift — **not applied**.
- **Next recommended batch:** Either **`coder_auto`** enables one-shot line edit for healthy files / improves literal-preserving replace, **or** orchestrator approves a **narrow server config** exception; else **`# type: ignore[no-untyped-def]`** on that `def` if policy allows (still via CST on **`SimpleStatementLine`** if parseable).

---

## Session — revalidation + retry (latest)

**Server revalidation (tester_ca):** **PASS** — `health` ok (`6.9.116`, process **669731**); `list_projects` includes **vast_srv**; `cst_load_file` **`add_fallback_logic.py`** OK; **`lint_code`** **0** errors.

**Bounded fix batch:** **Not completed** — in-memory CST param tweak did not persist: **`cst_save_tree`** → **`Connection refused`** (DB driver RPC socket).

**Process restart (tester_auto):** **`server_manager_cli restart`** exit **0**, new pid **943415** (no `vast_srv` file edits).

**Retry MCP (tester_ca):** **Blocked** — **`SERVER_NOT_FOUND`** for **`code-analysis-server_1`**; proxy **`list_servers`** lacked **`code-analysis-server`**; **`register_server`** failed with **UUID format** error. **Resume `vast_srv` edits** requires restoring MCP proxy registration/config for **`code-analysis-server`**.

---

## Session — post-commit `9cd2fcd` restart + revalidation

**Server restart (tester_auto):** **`server_manager_cli restart`** exit **0**, pid **993837** (loads running process including RPC retry fix).

**Server revalidation (tester_ca, MCP only):** **FAIL** — every **`call_server(..., server_id="code-analysis-server", copy_number=1)`** → **`SERVER_NOT_FOUND`** / **`Server code-analysis-server_1 not found`**. **`list_servers`** showed only **`embedding-service`** and **`svo-chunker-prod`**.

**Bounded `vast_srv` fix batch:** **Not run** (blocked before **`health`**).

**Exact blocker:** MCP Proxy in this runtime must **register** or **reload config** so **`code-analysis-server_1`** is visible; until then no guarded **`vast_srv`** work via **`tester_ca`**.

---

## Session — command trace + bounded batch (implementation_plan step 15)

**tester_ca:** **`list_servers`** showed **`code-analysis-server`**; **`health`** / **`list_projects`** / **`cst_load_file`** / **`lint_code`** / **`type_check_code`** OK — **no `SERVER_NOT_FOUND`**. **First failure:** **`compose_cst_module`** → **`CST_REPLACE_ERROR`** (single-line def snippet). **Fallback:** **`cst_modify_tree`** applied **`file_path: str`**. **`cst_save_tree`** first attempt **`SERVER_UNAVAILABLE`**; **retry** OK, backup **`48137022-8176-4128-af6d-aa0581262bbc`**. **`lint_code`** **0**; **`type_check_code`** still **1 × `no-untyped-def`** (missing **return** type). **`SERVER_NOT_FOUND`:** **not observed** this run.

---

## Session — return-type batch + save boundary (latest)

**Trace (tester_ca):** **`compose_cst_module`** full replace → **`VALIDATION_ERROR`** (project validation). **`cst_modify_tree`** full function with **`-> bool`** → apply **OK** in-memory; **`cst_save_tree`** → **`SERVER_UNAVAILABLE`** then logging-related error **`Attempt to overwrite 'importance' in LogRecord`**; **disk not updated** for return type. **`SERVER_NOT_FOUND`** → **yes** on later MCP calls (proxy lost **`code-analysis-server`**). **Remaining:** **`no-untyped-def`** (return type) until a **successful save** in a session where proxy lists **`code-analysis-server`**.

---

## Session — continuation: `no-untyped-def` batch (numbered trace, no `SERVER_NOT_FOUND`)

**tester_ca (numbered):** (1) **`list_servers`** OK — **`code-analysis-server`** present. (2) **`health`** OK (**6.9.116**). (3) **`list_projects`** OK — **vast_srv** `project_id` **`c86dded6-6f93-4fb0-be54-b6d7b739eeb9`**. (4) **`cst_load_file`** `add_fallback_logic.py` OK (`tree_id` **`261e757e-764b-4d41-9880-f0bde4ec7c4f`**). (5–8) **`cst_find_node`**, **`cst_get_node_info`**, **`query_cst`**, **`list_cst_blocks`** OK. (9) **`cst_get_node_by_range`** OK. (10) **`replace_file_lines`** → **FAIL** **`USE_CST_COMMANDS`**. (11) **`query_cst`** one-line signature → **FAIL** **`CST_REPLACE_ERROR`**. (12) **`cst_modify_tree`** **`preview=true`** stub FunctionDef → **OK** (not applied — would drop real body). (13) **`type_check_code`** command OK; mypy still **1 × `no-untyped-def`** L18.

**First failure:** step **10** — **`replace_file_lines`**. **Last successful command:** step **13** **`type_check_code`** (RPC OK; diagnostic still failing). **`SERVER_NOT_FOUND`:** **none** this session. **Disk:** **no** **`cst_save_tree`** — **no** substantive edit applied.

**Next:** Apply **`cst_modify_tree`** **`replace`** with **full** function **`code_lines`** from server-returned function `code` + signature **`-> bool`**, then **`cst_save_tree`** → **`format_code`** → **`lint_code`** → **`type_check_code`** (or parent-approved config/script if payload size warrants).

---

## Session — full FunctionDef replace + save (latest)

**tester_ca (numbered):** (1) **`list_servers`** OK. (2) **`health`** OK. (3) **`list_projects`** OK — **vast_srv** **`c86dded6-6f93-4fb0-be54-b6d7b739eeb9`**. (4) **`list_project_files`** OK → **`add_fallback_logic.py`**. (5) **`cst_load_file`** OK → `tree_id` **`fb60cb5e-ef20-402e-850d-3b61679210b5`**. (6) **`cst_find_node`** OK → FunctionDef **`10addf4e-f3bb-43bc-8123-44c679d138b7`**. (7) **`cst_get_node_info`** OK (full body). (8) **`cst_modify_tree`** **`preview=false`** full **`code_lines`** (signature **`-> bool`**, body preserved) — **OK** (`operations_applied: 1`). (9) **`cst_save_tree`** **`backup=true`** — **FAIL** **`SERVER_UNAVAILABLE`**. (10) **`health`** OK. (11) **`cst_save_tree`** retry — **FAIL** connection **`[Errno 111] Connection refused`**. (12) **`cst_load_file`** — **FAIL** same **-32603**. (13) **`list_servers`** OK — **`code-analysis-server`** still listed.

**First failure:** step **9** — **`cst_save_tree`**. **`SERVER_NOT_FOUND`:** **none**. **Disk:** **no** successful save — **`format_code` / `lint_code` / `type_check_code`** **not** run on updated file. **`no-untyped-def`:** **not** cleared (save blocked).

**Blocker:** worker/socket **`Connection refused`** after in-memory CST apply — **restart/repair** server per **`server_manager_cli`**, then **re-run** load → modify (if disk unchanged) → save → QA.
