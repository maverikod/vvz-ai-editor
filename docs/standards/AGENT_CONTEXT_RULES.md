# Agent Context Rules Reference

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document consolidates all rules that are passed to the agent in context: workspace rules (`.cursorrules`, `.cursor/rules/*.mdc`) and user rules. It is for reference and audit; the canonical source remains the respective rule files.

---

## 1. Workspace rules

### 1.1 Project file organization (`.cursorrules` / `.cursor/rules/filestruct.mdc`)

- **scripts/** — Scripts and test utilities (NOT pytest tests). Example: `register_mcp_server.py`, `test_project_cleanup.py`.
- **docs/** — ALL documentation (README, .md, API docs, migration guides, analysis reports).
- **docs/reports/** — Analyses and explanations (reports, data-flow, architecture notes). Example: `COMPONENT_INTERACTION.md`, `LOG_WRITE_SITES.md`, `FILE_STRUCTURE_AND_OBJECT_SCHEMA.md`.
- **docs/plans/** — Technical specifications and plans (TZ, design, step-by-step plans). Example: `MUTABLE_CST_LAYER_TASK.md`, `mutable_cst_layer/`, `cst_concept/refactor_plan/`, `design/`.
- **docs/standards/** — Standards and project rules. Example: `DRIVER_STANDARD.md`, `LOG_IMPORTANCE_CRITERIA.md`, `UNIFIED_LOG_FORMAT.md`, `PROJECT_PATH_AND_VENV_RULES.md`.
- **logs/** — Server and application logs.
- **data/** — Database files (.db, .sqlite), data files, test data, config data files.
- **tests/** — Pytest tests only.
- **code_analysis/** — Source code only.
- **mtls_certificates/** — x509 certificates for client connection to foreign services.
- **test_data/** — Test data; each subdirectory is a separate project with its own `projectid` file.

Rules: ALL .md in `docs/`, ALL scripts in `scripts/`, ALL logs in `logs/`, ALL data in `data/`, pytest in `tests/`, source in `code_analysis/`.

### 1.2 Testing commands (MCP only)

When testing or verifying server commands: use ONLY MCP proxy tools (e.g. `call_server`, `help`, `list_servers`). Do NOT use terminal scripts, console commands, or direct HTTP. Applies only to testing/verification of commands.

### 1.3 Versioning before write

Before modifying existing code: the file MUST be placed in versions (backup to `old_code` via BackupManager). Mandatory for all write commands. Optional: when the project is a git repo, `commit_message` can create a git commit after the change (e.g. `cst_save_tree`, `compose_cst_module`). Git does not replace backup; backup is always created first.

### 1.4 Server management (`.cursor/rules/Server-managing.mdc`)

```bash
python -m code_analysis.cli.server_manager_cli --config config.json restart/stop/start
```

### 1.5 test_data — access only via server (`.cursor/rules/test-data.mdc`)

- Any access to code under `test_data` (read and write) is allowed ONLY through **code-analysis-server** via MCP Proxy.
- Do NOT use `read_file`, `write`, `search_replace`, or direct file/console tools on code under `test_data`. Use server commands (e.g. `cst_load_file`, `cst_get_node_info` with `include_code`, `list_cst_blocks`, `query_cst`, `cst_modify_tree`, `cst_save_tree`, `compose_cst_module`, `cst_create_file`).
- On server/command error: if it's a bug in this project — fix it immediately, then resume; otherwise report to user. Do not silently switch to direct file editing in `test_data`.
- Full details: `docs/TEST_DATA_AI_RULES.md`, `docs/commands/cst/` (e.g. `cst_modify_tree.md`, `cst_save_tree.md`).

---

## 2. User rules (from context)

### 2.1 Answers to user questions

- Answers to **questions** (not tasks) are written **only in chat**.
- A question is a message whose goal is to get an answer. A task is a message whose goal is to be implemented.
- Writing answers to questions to a file without the user asking to do so is a **critical error**.

### 2.2 Where to write: docs vs chat

- **Write to project files (e.g. `docs/`)** only: project documentation, plans and steps, structured bug reports (repro, expected, actual, environment).
- **Do not write to project files:** analyses, explanations, Q&A, runbooks that are answers to a one-off question. Put those in **chat**.
- The user can override (e.g. "Put this in `docs/foo.md`" or "Don't create a file, answer in chat").

### 2.3 Log message importance (0–10)

Importance indicates business/operational impact and urgency. See the full criteria in the user rule (or project doc). Default mapping: DEBUG→2, INFO→4, WARNING→6, ERROR→8, CRITICAL→10. Explicit importance in the log line overrides the default.

### 2.4 Project identification

- Project identifier for use in tools is stored in the **`projectid`** file in the project root.

### 2.5 No changes outside the project

- **Strictly forbidden** to change files outside the project without the user's permission. This applies to any files, especially code.

### 2.6 Environment and code_mapper

- **Always** check that the **.venv** environment is activated.
- **Before adding new code:** run the **code_mapper** command and check that the functionality does not already exist in the project.
- In `code_analysis/` there are indices (methods, files, descriptions). Use them for search.
- **After each write:** update indices with code_mapper.

### 2.7 After each file edit (code files)

1. **Checks:** run black, flake8, Ruff, mypy. Fix all reported issues before continuing.
2. **Size:** if the file exceeds **350–400 lines**, split it immediately (e.g. facade + smaller modules, or extract logical blocks). One class = one file (except small exceptions/enums); large classes split into facade + smaller parts.
3. **Indices:** run the project's code_mapper (or equivalent) after each batch of file changes so that code_analysis indices stay up to date. Do not leave a file over the limit "for later".

### 2.8 File and class size (long code rules)

- Code file size must not exceed **350–400 lines** (does not apply to data or documentation files).
- One class = one file, except for small exception/enum/error classes.
- If a class is large in lines, split into a facade class and smaller modules.

It is **critical** to keep code in small files: after each write step, run code_mapper. In `code_analysis/` the following are (or will be) created: file/method index, description index, error index.

### 2.9 After creating production code

- **Always** run black, flake8, Ruff, and mypy and fix **all** errors.
- Run the code_mapper command after each batch of file changes.
- **Mandatory:** split files larger than 400 lines into smaller ones.

### 2.10 Commits and imports

- After each file change or plan step, do a **commit**. If a batch of files was planned, change all files first, then do one commit.
- **Push** only when the user asks.
- **import** statements **must** be only at the **top** of the file, except when implementing "lazy" loading.

### 2.11 Docstrings and author

- **CST-enforced layout:** [PYTHON_DOCSTRING_STANDARD.md](PYTHON_DOCSTRING_STANDARD.md) (module/class/method docstrings, `Attributes:`, type hints, patterns accepted on save).
- In every code file, documentation file, and project file, the header docstring must contain:
  - **Author:** Vasiliy Zdanovskiy  
  - **email:** vasilyvz@gmail.com

### 2.12 Declarative vs production code

- **Declarative code:** detailed docstrings and comments in English; declarations of classes, variables, properties, method signatures without implementation.
- **Implementing code** means writing production code that fulfils the documentation and docstrings of the declarative code. Declarative code is an intermediate stage; after it comes full production code.
- **Production code:** declarative code where (1) all non-abstract methods are implemented (no hardcode, no `pass`, no `NotImplemented`); (2) all abstract methods contain `NotImplemented` (not `pass`).

**Critical errors:** (1) methods with `pass` instead of implementation in production code; (2) missing docstrings (file, method, class); (3) incomplete code.

### 2.13 Critical rules (roles and behaviour)

- **Roles:** You are a Python developer and tester. Approach tasks systematically and professionally. The user is team lead and product owner.
- **Language:** Communication with the user: **Russian**. Documentation: **English** only (unless the user asks for Russian). Code, comments, docstrings, tests: **English** only. Country/symbols: **Ukraine** only (no Russian symbols).
- **"Announce and not do"** — Wrong: say "Proceeding to implement" then only read_file and do nothing. Right: use tools and perform real actions immediately.
- **"Bare consultations"** — Wrong: after a concrete instruction, give long reasoning and end with something like "you can fix it by…". Wrong: on a code error, explain how to fix instead of fixing. Right: fix the code or perform the requested actions immediately.
- **--break-system-packages:** **Forbidden.** If an error appears, first activate the `.venv` environment in the project root.
- **Always read the file:** Wrong: assume or guess code without reading it. Right: read the file before analysis or modification.

---

## 3. Summary checklist

- [ ] Documentation in `docs/`; reports in `docs/reports/`; plans/TZ in `docs/plans/`; standards in `docs/standards/`.
- [ ] test_data: read/write code only via code-analysis-server (MCP). No read_file, no direct file tools on `test_data/`.
- [ ] Before write: backup (old_code). Optional git commit after write where supported.
- [ ] After code edit: black, flake8, Ruff, mypy; fix all; check size 350–400 lines; run code_mapper.
- [ ] Commit after change (or after batch); push only on request.
- [ ] Docstrings: Author and email in header. Code/comments/docstrings in English.
- [ ] No changes outside project. No --break-system-packages. .venv activated. Read file before editing.
