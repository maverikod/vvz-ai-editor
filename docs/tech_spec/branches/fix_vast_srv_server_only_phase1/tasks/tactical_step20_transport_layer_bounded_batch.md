<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task: implementation_plan Step 20 — bounded adapter/proxy-layer batch.
-->

# Tactical Task: Step 20 — Transport layer continuation (outside-repo primary)

## Purpose

After Step 19, the **narrowest blocker** for intermittent proxy/transport instability lies **primarily outside** this repository (`mcp-proxy-adapter`, MCP proxy process). Step 20 applies the **smallest justified** adapter/proxy-layer **configuration or dependency** batch (e.g. **`requirements.txt`** pin, install, restart), then **revalidates** heavier guarded **`vast_srv`** usage **only** via **`tester_ca`**.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_cst_save_tree_persist_logging_path.md`
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`
- `docs/tech_spec/implementation_plan.md` (Step 20)

## Scope

**Included:** Bounded **`mcp-proxy-adapter`** version / install alignment; proxy-layer **reload** discipline; **`tester_ca`** stress: **`cst_load_file` → repeated `cst_save_tree`** on **`vast_srv`**.

**Excluded:** Broad adapter refactors; direct **`test_data/vast_srv`** edits except through **`tester_ca`**.

## Boundaries

- **`coder_auto` / `tester_auto`** must not touch guarded **`vast_srv`** code.
- After any **`code-analysis-server`** dependency change affecting runtime: **restart** before guarded revalidation.

## Dependencies

- Step 19: blocker outside repo documented.

## Parallelization note

Research → optional requirements/install/restart → **`tester_ca`** — serialized.

## Expected outcome

- Either a **committed** bounded batch + restart/reload + **`tester_ca`** revalidation, or **explicit narrowest blocker** (not practically fixable in-repo).

## Correction items

- From specialist outputs.

## Questions/escalation rule

- Escalate if **Cursor MCP Proxy** host config or **mTLS** must change outside this repo without a version pin path.

## File inventory

- From `researcher_code` / `coder_auto`.

## Specialist routing

- `researcher_code`: PyPI / adapter release delta vs current pin; justification for bump.
- `coder_auto`: edit **`requirements.txt`** (and similar) if justified; commit.
- `tester_auto`: **`pip install`** aligned to requirements + **`server_manager_cli` restart** if runtime changes.
- `tester_ca`: heavier guarded save sequence.

## Branch execution log (Step 20 batch)

- **`researcher_code`:** PyPI **`mcp-proxy-adapter`** latest **6.10.1**; venv had **6.9.117**; no public changelog proving timeout fixes — bump justified as **currency / patch series**, not proven fix.
- **`coder_auto`:** Commit **`c427870b608c92acfa8392a8f3bb71272f70538d`** — `chore(deps): bump mcp-proxy-adapter floor to 6.10.1 (Step 20 transport layer)`; **`requirements.txt`** only.
- **`tester_auto`:** `pip install 'mcp-proxy-adapter>=6.10.1'` → **installed 6.10.1**; **`server_manager_cli` restart** → **PID 1079906**, config **`/home/vasilyvz/projects/tools/code_analysis/config.json`**.
- **`tester_ca`:** `health` **6.10.1** / **1079906**; sequential stress **`add_fallback_logic.py`**: saves **#1–#3 success**, **#4–#6 `SERVER_UNAVAILABLE`** (proxy); first failure **#4**. Later **`health`/`list_projects`** **`SERVER_UNAVAILABLE`** `"All connection attempts failed"`. One transient **`cst_load_file`** socket refused then retry OK. **`reload_config`** not needed (no **`SERVER_NOT_FOUND`**). **`list_servers`** listing omitted **`code-analysis-server`** but **`call_server`** worked until degradation.
