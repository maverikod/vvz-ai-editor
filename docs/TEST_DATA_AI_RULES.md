# AI Rules for Code in test_data (Project-Specific)

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Scope

These rules apply whenever the AI **accesses** (reads, creates, edits, or deletes) **code under the `test_data/` directory** of this repository. They do not apply to the rest of the codebase or to other projects.

**Relationship to general rules**: The general tool usage and CST workflows are defined in [AI_TOOL_USAGE_RULES.md](AI_TOOL_USAGE_RULES.md). This document adds **obligations and constraints that apply only to paths under `test_data/`**.

---

## 1. test_data as Separate Projects

- **Each subdirectory of `test_data/` is a separate project** from the server’s point of view.
- Each such project:
  - Has its own **project root** (e.g. `test_data/vast_srv`, `test_data/particles`).
  - Has its own **virtual environment** (e.g. `.venv` in that project root). Use that venv when **running that project’s code** (e.g. tests, scripts).
  - Is visible in the project list returned by **`list_projects`** (when registered).
  - Has a **`projectid`** file in its root with the project UUID (or gets one on **`create_project`**).
- All paths used in server commands for code under `test_data/` are **relative to that project root** (e.g. `ai_admin/__main__.py` for a file under `test_data/vast_srv/`).

---

## 2. Mandatory: Server Only for Any Access to test_data Code

**Any access to code under `test_data/`** — including **reading** — must go **only** through **code-analysis-server** via MCP Proxy. No direct file or terminal tools for code there.

- **To read/inspect code**: use server commands only — e.g. `cst_load_file` then `cst_get_node_info` with `include_code`, or `list_cst_blocks`, `query_cst` with `include_code`. Get content from the server response.
- **To create, edit, or delete code**: use only server commands (see command groups below).
- **Do not** use:
  - **read_file**, **cat**, or any direct file read on paths under `test_data/` to see code (even “just to look”).
  - **write**, **search_replace**, or other direct file tools on code under `test_data/`.
  - Terminal/console commands or scripts to read, create, edit, or delete code under `test_data/`.
  - Other MCP servers for any code access under `test_data/`.

**Check before every file/tool use:** if the path is under `test_data/` and the target is code → use a server command, not read_file or write.

**Allowed outside this restriction:**

- Using server tools to **delete** files or directories under `test_data/` (e.g. cleanup).
- Editing **this project’s own code** (outside `test_data/`) with any appropriate tools.

**Rationale**: Code under `test_data/` is used to test and demonstrate the server (CST, backups, validation, DB). Editing it only via the server ensures that server behaviour is actually exercised and that project/project_id semantics are respected.

---

## 3. Resolving project_id for test_data Projects

- **Existing project**: Get `project_id` from:
  - The **`projectid`** file in the root of the relevant `test_data/<subdir>` (e.g. `test_data/vast_srv/projectid`), or
  - **`list_projects`** (optionally filtered by path or name) for the test project.
- **New project**: Use **`list_watch_dirs`** to get `watch_dir_id`, then **`create_project`** with `root_dir` (path to the new subdirectory), `watch_dir_id`, `project_name`, and `description`. The returned or stored **`project_id`** must be used for all subsequent commands for that project.
- All CST, analysis, search, and code-quality commands that require a project use **`project_id`**; paths are **relative to that project’s root**.

---

## 4. Command Groups to Use for test_data Code

Same workflows as in [AI_TOOL_USAGE_RULES.md](AI_TOOL_USAGE_RULES.md), but **always** with the appropriate **`project_id`** for the target `test_data` project:

- **CST (tree-based)**: `cst_load_file` → `cst_find_node` / `cst_get_node_by_range` → `cst_modify_tree` (use **`code_lines`** for multi-line code) → `cst_save_tree`. For **insert** in `cst_modify_tree`: `parent_node_id` must be a **container** (Module, FunctionDef, or ClassDef), not IndentedBlock; use **`__root__`** for module-level; for a function body use the **function's node_id** (FunctionDef), not its body node. See [cst_modify_tree.md](commands/cst/cst_modify_tree.md).
- **CST (file-based)**: `list_cst_blocks`, `query_cst`, then `cst_apply_buffer` with `apply=true` and `create_backup=true` as needed.
- **New file**: `cst_create_file` (or `cst_apply_buffer` for new path) with `project_id` and path relative to project root.
- **Quality**: `format_code`, `lint_code`, `type_check_code` (with `project_id` where required).
- **Analysis**: `comprehensive_analysis`, `get_code_entity_info`, etc., with `project_id`.
- **Discovery**: `list_projects`, `list_project_files`, `fulltext_search`, `semantic_search`, etc., with `project_id`.

Exact parameters: see [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md) and [COMMANDS_INDEX.md](COMMANDS_INDEX.md) or the command’s `get_schema` (e.g. via MCP `help`).

---

## 5. Error Handling and Server Unavailable

**Critical — on error in this project's server:** If an error is discovered while using this project's server commands (bug, crash, wrong response), **immediately proceed to fix it** (fix the code of this project, not under `test_data/`). After the fix, **return to the breakpoint** and resume the original task from where it stopped. Do not only report and wait: fix first, then continue.

- If a server command fails and the cause is unclear, **report the error to the user** and do **not** silently fall back to direct file editing under `test_data/`.
- The user decides whether to retry, fix the server/config, or allow an exception (e.g. temporary use of another method) outside these rules.

**If the server is not found or unreachable:** start it from the **project root** (this repository root) with the project’s virtual environment activated:

```bash
cd /path/to/code_analysis && . .venv/bin/activate && python -m code_analysis.cli.server_manager_cli --config config.json start
```

Use `restart` instead of `start` to restart an already running server. After the server is up, retry the MCP call.

---

## 6. Summary Checklist

- [ ] Target path is under `test_data/` → **any** access (read + write) **only** via code-analysis-server (MCP). No read_file, no direct writes.
- [ ] To see file content: use `cst_load_file` / `cst_get_node_info` or `list_cst_blocks` / `query_cst` with `include_code` — never read_file on test_data paths.
- [ ] Resolve **project_id** from `projectid` or `list_projects` (or create project with `create_project`).
- [ ] Use **project_id** and paths **relative to project root** in all server commands.
- [ ] Prefer **`code_lines`** for multi-line code in `cst_modify_tree` / compose ops.
- [ ] For **insert** in `cst_modify_tree`: `parent_node_id` must be Module, FunctionDef, or ClassDef (not IndentedBlock); use **`__root__`** for module-level; use the function's node_id for function body. See [cst_modify_tree.md](commands/cst/cst_modify_tree.md).
- [ ] On server error in this project: fix the bug immediately, then resume from breakpoint; otherwise report to user; do not silently switch to direct reads or edits under `test_data/`.
