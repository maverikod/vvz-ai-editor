<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task: implementation_plan Step 19 — proxy/transport availability.
-->

# Tactical Task: Step 19 — Proxy / transport availability (`mcp-proxy-adapter`, registration, reload)

## Purpose

After Steps 16–18 and repeat-save repairs, **intermittent proxy/transport** symptoms remain (`SERVER_NOT_FOUND`, **`SERVER_UNAVAILABLE`**, need for **`reload_config`**, socket refusal while **`health`** still OK). This task narrows and repairs the **proxy/transport registration path** as far as justified in-repo or in **`mcp-proxy-adapter`**, without reopening broad **`vast_srv`** work; guarded verification only via **`tester_ca`**.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_cst_save_tree_persist_logging_path.md`
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`
- `docs/tech_spec/implementation_plan.md` (Step 19)

## Scope

**Included:** MCP proxy registration, **`reload_config`** semantics, **`mcp-proxy-adapter`** integration (requirements, config), HTTP/client timeouts toward **`code-analysis-server`**, any in-repo glue that causes stale registration or short deadlines.

**Excluded:** Broad **`vast_srv`** backlog; direct guarded-path edits except through **`tester_ca`**.

## Boundaries

- Distinguish **proxy visibility loss** vs **adapter timeout** vs **transport/socket refusal** vs **manual reload recovery**.
- **`coder_auto` / `tester_auto`** must not touch **`test_data/vast_srv`** code.
- After any **`code-analysis-server`** code change: **restart** before guarded revalidation (parent rule).

## Dependencies

- Step 17/18 narrative: repeat-save / transition work advanced; residual instability attributed to proxy/transport.

## Parallelization note

Research → optional code → restart/reload → **`tester_ca`** — serialized.

## Expected outcome

- Root cause classification with paths/symbols or external dependency identification.
- If repair: commit + restart/reload evidence + **`tester_ca`** revalidation.
- Else: narrowest exact blocker for global orchestrator.

## Correction items

- Populated from specialist findings.

## Questions/escalation rule

- Escalate when **`tech_spec.md`** or cross-repo **`mcp-proxy-adapter`** release process must change.

## File inventory

- To be filled from `researcher_code` / `coder_auto`.

## Specialist routing

- `researcher_code`: proxy adapter, registration, `reload_config`, timeouts in this repo.
- `coder_auto`: bounded in-repo repair only.
- `tester_auto`: server restart if server code changes.
- `tester_ca`: guarded `vast_srv` or proxy health/list_servers after reload.

## Branch execution log (Step 19 batch)

- **`researcher_code`:** **`mcp-proxy-adapter`** is **PyPI-only** (`requirements.txt`); **`reload_config`/`list_servers`** are **MCP Proxy** tools, not `code_analysis` Python. Registration/heartbeat URLs live in **`config.json` `registration`**; **~30s MCP** client cap is **outside** this tree; **`health` OK + RPC refused** = main process up, **DB driver socket** separate.
- **`coder_auto`:** **NO_COMMIT / NO_IN_REPO_FIX** — no in-repo HTTP timeout knob for outbound proxy registration/heartbeat; behavior is **adapter-internal** (`main_config.py` only pushes config into `get_config()`).
- **`tester_ca` (observation):** `list_servers` shows **`code-analysis-server`**; proxy **`health_check`** OK; **`call_server` → `health`** OK (**pid `1071599`**, **`proxy_registration.registered: true`**); **`reload_config` not needed** this session; **`list_projects`** includes **`vast_srv`**. No **`SERVER_NOT_FOUND`** in this run.
