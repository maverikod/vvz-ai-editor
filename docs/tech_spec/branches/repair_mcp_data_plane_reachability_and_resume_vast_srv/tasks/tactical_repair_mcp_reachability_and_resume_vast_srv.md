<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task for global step: repair_mcp_data_plane_reachability_and_resume_vast_srv.
-->

# Tactical Task: Repair MCP data-plane reachability + resume vast_srv

## Purpose

Identify why **`mcp-proxy`** registers **`code-analysis-server`** but TCP/TLS to **`server_url`** fails, apply the **minimal** alignment (bind address, port, advertised URL, or proxy registration), restart the server if needed, prove **`health`** via **proxy-mediated** MCP, then resume **`vast_srv`** remediation with **`tester_ca`** only.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_mcp_data_plane_reachability_and_resume_vast_srv.md`
- Prior context: `docs/tech_spec/branches/confirm_logical_write_live_path_and_resume_vast_srv_all_errors/tasks/tactical_confirm_logical_write_live_and_vast_srv_remediation.md`

## Running execution log

- **Initialized:** awaiting specialist evidence.
- **`researcher_code`:** Bind uses **`SettingsManager`** defaults **`0.0.0.0:15000`** when env unset — **`config.json` `server.host`** may not drive bind (`main_config` vs `settings.get`). Proxy registration URL is **external** (`register_server`). Hypotheses: network namespace mismatch, **`127.0.0.1` vs bridge IP**, or stale process.
- **`tester_auto`:** **`config.json`** `server.host` **`172.28.0.1`**, port **`15000`**, **`mtls`**. **`ss`:** **`0.0.0.0:15000`** LISTEN (**pid 1224601**). **`curl -vk`:** **`https://127.0.0.1:15000/health`** and **`https://172.28.0.1:15000/health`** both **HTTP 200** from host. **`server_manager_cli status`:** **running** (same PID).
- **`tester_ca` (data plane + remediation):**
  - **`test_client_connection`:** **`https://172.28.0.1:15000`** → **available**; **`https://127.0.0.1:15000`** → **unavailable** (`SERVER_UNAVAILABLE`) — proxy’s **loopback ≠ server host**.
  - **`call_server` `health`:** **`success: true`**, **`version` 6.10.1**, **`server_url`** **`https://172.28.0.1:15000`** — **no** `unregister`/`register` (repair condition not met).
  - **Root cause:** **Not** a dead server — server listens on **`0.0.0.0:15000`**. Proxy must use **bridge/host reachable URL** (**`172.28.0.1`**) — **`127.0.0.1`** from proxy process targets **wrong** namespace. Earlier **`SERVER_UNAVAILABLE`** likely **transient disconnect** or **wrong** test URL from proxy side, not bad `172.28` registration.
  - **`vast_srv`:** **`add_full_queue_support/queue_helpers.py`** — **`cst_modify_tree`** + **`cst_save_tree`** + **`format_code`** (Black) → **`lint_code`** **0** errors, **`type_check_code`** **0** errors. **Not** edited: **`ai_admin/__init__.py`**, **`git_auth_manager.py`** (out of scope for this batch).
- **Server restart this batch:** **none** (no repo code change; reachability verified without config edits).
- **Continuation — `tester_ca` (ai_admin batch):**
  - **`ai_admin/__init__.py`:** Invalid import removed, duplicate imports cleaned, **`# type: ignore[import-untyped]`** on **`mcp_proxy_adapter`** imports, docstring/module layout; **`lint_code` 0**, **`type_check_code`** clean (rely on `errors` list; note possible `success: false` with “0 mypy errors” quirk).
  - **`ai_admin/auth/git_auth_manager.py`:** Return/variable annotations for **`discover_ssh_keys`**, **`_is_key_in_agent`** typing fix; **`lint_code` 0**, **`type_check_code`** clean.
  - **`comprehensive_analysis`** job **`comprehensive_analysis_c535df2f`** → **`completed`:** **`total_flake8_errors: 0`**, **`total_mypy_errors: 0`**; **2** placeholders (**STUB** in **`queue_helpers.py`** — intentional harness text); **140** long-file reports; **0** stubs/empty methods/duplicates per summary. **`lint_code`** on **`queue_helpers.py`** still **0**.
  - **Server restart:** **none** (no server-side repo defect).
  - **Blocker:** **none**. Non-blocking: **`compose_cst_module`** once **`VALIDATION_ERROR`** on **`__init__.py`** — worked around with **`cst_modify_tree` `replace_range`**.
- **Placeholder continuation — `tester_ca`:** **`add_full_queue_support/queue_helpers.py`** — two analyzer rows for **same** docstring text *"Get list of all Docker command files (harness stub)."* (**lines ~13–14**, `docstring` + `string` duplicate). **CST proof:** function **`get_docker_commands`** body is **`return []`** — no **`NotImplementedError`**; substring **STUB** was **documentation-only** (“harness stub”). **Classification:** inert doc artifact; **minimal docstring reword** to remove false-positive **STUB** match: *"test harness; returns empty list"* via **`cst_modify_tree`** → **`cst_save_tree`** → **`format_code`** / **`lint_code`** / **`type_check_code`** (clean). **`comprehensive_analysis`** before: job **`comprehensive_analysis_fdf1c736`**, **2** placeholders; **after:** job **`comprehensive_analysis_e54adad1`**, **`total_placeholders: 0`**, **0** flake8/mypy. **Backlog exhausted** for confirmed placeholders in this slice. **Blocker:** **none**. Note: **`cst_get_node_info`** on **`FunctionDef`** with **`include_children: true`** hit **`CST_GET_NODE_ERROR`** — worked with **`include_children: false`**.

## Subordinate Agents State

| agent | status | scope | blocker |
|-------|--------|-------|---------|
| `researcher_code` | done | settings/bind vs JSON | none |
| `tester_auto` | done | listeners, curl, status | none |
| `coder_auto` | idle | — | not needed for reachability |
| `tester_ca` | done | vast_srv backlog slice | none |
