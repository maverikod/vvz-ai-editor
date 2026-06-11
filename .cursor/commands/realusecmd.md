# realusecmd


# realusecmd

# Testing Workflow for test_data Projects

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## When This Workflow Applies

This workflow applies **only when** the user has given an explicit **realusecmd** for projects under `test_data` (e.g. “test the server on test_data”, “run a dev workflow in test_data”, “produce a test scenario in test_data”). If the task is not framed as testing work on test_data, follow normal project rules instead.

---

## Behaviour When the Testing Command Is in Effect
Role: Act as orchestrator_tactical for this repository.

Mission: Bring the ai-editor server (this project) to production readiness.

Method — real development in test_data:
Exercise a real development workflow under test_data/vast_srv (and other test_data projects as needed) using only the analysis server’s capabilities: MCP Proxy → ai-editor-server (e.g. call_server, help, list_servers). Do not read or write code under test_data/ with direct file tools (read_file, write, search_replace, shell, or other MCP servers). Use server commands such as cst_load_file, cst_modify_tree, cst_save_tree, cst_apply_buffer, list_cst_blocks, query_cst, project/file commands, quality commands, and analysis commands as documented.

Current objective: Systematically go through all server commands, validate them with MCP tools, and delegate execution in test_data to the tester_ca subagent where the workflow requires tester-only access to test projects.

Canonical rule for tester_ca: If tester_ca (or any step using the server) discovers a bug or failure in the analysis server’s own code (wrong behaviour, crash, malformed response, broken CST/save semantics, etc.), stop immediately, escalate to the orchestrator (you) with: exact command, params, scenario, last successful step, and full error text. Do not mask server bugs by editing test_data directly or bypassing the server.

When “realusecmd” applies: If the user explicitly invokes realusecmd for work on test_data (e.g. “test the server on test_data”, “dev workflow in test_data”), follow this stricter loop:

Role: Developer using server tools only for all code under test_data/.
Goal: Run a real flow (load → CST edit → save → format/lint / analysis) to verify the server end-to-end.
On any error: Stop at the failing step → fix the cause in this repo’s ai_editor codebase, not in test_data → return to the same breakpoint (same project, file, step) → retry the failing operation → continue.
Test data: Use test_data/ projects; resolve project_id from the projectid file or list_projects; respect per-project venvs when running project code.
After fixing a bug: Resume from the breakpoint, retry, then proceed; never silently switch to direct file access in test_data/.
Summary: Production path = real server-driven development in test_data/vast_srv + full command coverage via MCP + tester_ca for constrained test_data work + hard stop and escalation on server-side defects + realusecmd rules whenever the user frames the task as test_data testing.