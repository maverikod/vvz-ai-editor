# Testing Workflow for test_data Projects

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## When This Workflow Applies

This workflow applies **only when** the user has given an explicit **testing command** for projects under `test_data` (e.g. “test the server on test_data”, “run a dev workflow in test_data”, “produce a test scenario in test_data”). If the task is not framed as testing work on test_data, follow normal project rules instead.

---

## Behaviour When the Testing Command Is in Effect

### Role

Act as a developer using **server tools only** (MCP → code-analysis-server). All read/write of code under `test_data` is done via server commands (e.g. `cst_load_file`, `cst_modify_tree`, `cst_save_tree`, `compose_cst_module`, `list_cst_blocks`, `query_cst`). Do not use `read_file`, `write`, or `search_replace` on paths under `test_data/`.

### Goal

Run a real development flow (load file → edit via CST → save → format/lint) to verify server behaviour end-to-end.

### On Any Error

1. Stop at the failing step.
2. Fix the cause in **this project’s code** (the code_analysis codebase), not in `test_data`.
3. Return to the breakpoint (same project/file/step).
4. Repeat the same action that caused the error.
5. Continue the scenario in developer mode.

### Test Data

Use projects under `test_data/`; each has its own `projectid` and venv. Resolve `project_id` from the `projectid` file in the project root or from `list_projects`.

### After Fixing a Bug

Resume from the breakpoint, retry the failing operation, then proceed; do not silently switch to direct file access in `test_data`.
