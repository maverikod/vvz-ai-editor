# Project path resolution and virtual environment

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Path resolution

**Rule:** For any command that accepts a project (`project_id`) and a path (e.g. `file_path`, `script_path`):

- **Non-absolute paths** MUST be resolved **relative to that project’s root** (the directory that contains the project’s code, e.g. `test_data/vast_srv` for project vast_srv).
- The “current directory” for path resolution is **always the project root** for that project, not the repository root or the process cwd.
- When a command has `project_id`, the project root MUST be taken from the **projects table** in the database (e.g. `get_project(project_id)["root_path"]`). The driver and MCP use the same database, so path resolution is consistent.

**Examples:**

- `file_path = "ai_admin/commands/foo.py"` with `project_id` for vast_srv → resolve to `{project_root}/ai_admin/commands/foo.py` where `project_root` is vast_srv’s root.
- Run script/module commands use project root as `cwd` and resolve script/module paths relative to it.

Implementation notes:

- **MCP commands:** use `BaseMCPCommand._resolve_project_root(project_id)`, which reads from the projects table via `db.get_project(project_id)` and returns `Path(project.root_path)`.
- **Database/driver (e.g. `mark_file_deleted`):** use `self.get_project(project_id)` and then `Path(db_project["root_path"])` so that relative paths are resolved against the project root from the projects table.

## Virtual environment

**Rule:** For running code **inside a project** (e.g. `run_project_script`, `run_project_module`):

- The virtual environment MUST be looked for **under the project root**.
- **Lookup order:** `{project_root}/.venv` then `{project_root}/venv` (i.e. prefer **`.venv`** so that for a project like vast_srv the venv is `vast_srv/.venv`).
- Execution MUST use: **cwd = project root**, **PYTHONPATH = project root**, and the project’s venv interpreter (and env) so that only project code and its dependencies are used.

Implementation: `code_analysis/core/project_sandbox.py` implements this (`.venv` then `venv` under `root_path`, cwd and PYTHONPATH set to project root).
