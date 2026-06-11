<!--
Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
Plan: 2026-05-20-universal-editor-package
-->

# HRS — Universal Editor Package

**Plan slug:** `2026-05-20-universal-editor-package`  
**Status:** draft  
**Author:** Vasiliy Zdanovskiy  
**Date:** 2026-05-20  

---

## 1. Problem statement

The `universal_file_*` commands implement a complete file-editor abstraction:
sessions, format detection, draft management, diff/preview, atomic commit,
backup, and git integration. This logic is currently split across three
locations inside the `code_analysis` package:

| Location | What lives there |
|----------|------------------|
| `code_analysis/commands/universal_file_edit/` | New 4-command lifecycle (open/edit/write/close) |
| `code_analysis/commands/universal_file_save_command.py` + `save_command/` | Legacy save — monolith ~450 lines (CR-008 violation) |
| `code_analysis/commands/universal_file_read_command.py` | Legacy read |
| `code_analysis/commands/universal_file_delete_command.py` | Legacy delete |
| `code_analysis/commands/universal_file_replace_command.py` | Legacy replace |
| `code_analysis/core/file_handlers/` | Format handlers (python/json/yaml/text), registry, diff support |
| `code_analysis/core/backup_manager.py` | Backup/version history |
| `code_analysis/core/file_lock.py` | Advisory file lock |
| `code_analysis/core/git_integration.py` | Post-commit git hook |
| `code_analysis/core/path_normalization.py` | Path helpers |

**Consequences of the current structure:**

1. **Coupling to `code_analysis`** — the editor is not reusable outside this project.
2. **Legacy/new command duplication** — save/read/delete/replace duplicate
   handler calls already present in the new edit-workflow commands.
3. **CR-008 violation** — `universal_file_save_command.py` is ~450 lines
   (open issue).
4. **No clear boundary** — `core/file_handlers/` is editor infrastructure
   mixed with analysis infrastructure.
5. **`project_text_file_guard`** is referenced by legacy commands only — its
   placement is unclear.

---

## 2. Goal

Extract the universal editor into a **standalone, project-agnostic Python
package** (`universal_editor`) that:

- Has no import dependency on `code_analysis.*` in its core.
- Exposes a stable public API consumed by `code_analysis` command classes.
- Can be published independently or reused by other MCP servers.
- Eliminates all legacy command duplication.
- Resolves the CR-008 violation for `universal_file_save_command`.

---

## 3. Scope

### 3.1 In scope

- Create new top-level package `universal_editor/` at repo root (sibling of `code_analysis/`).
- Migrate the following modules into `universal_editor/`:
  - `core/file_handlers/` → `universal_editor/file_handlers/`
  - `core/backup_manager.py` → `universal_editor/backup_manager.py`
  - `core/file_lock.py` → `universal_editor/file_lock.py`
  - `core/git_integration.py` → `universal_editor/git_integration.py`
  - `core/path_normalization.py` → `universal_editor/path_normalization.py`
  - `commands/universal_file_edit/session.py` → `universal_editor/session.py`
  - `commands/universal_file_edit/format_group.py` → `universal_editor/format_group.py`
  - All other modules from `commands/universal_file_edit/` that contain no MCP command class.
- Rewrite command classes in `code_analysis/commands/universal_file_edit/`
  to import from `universal_editor.*`.
- Delete legacy commands: `universal_file_save_command.py`,
  `universal_file_read_command.py`, `universal_file_delete_command.py`,
  `universal_file_replace_command.py` (after confirming they are unregistered).
- Add `universal_editor` to `pyproject.toml` / `setup.cfg` as an installable package.
- Update all internal imports in `code_analysis/` that currently point to
  the migrated modules.
- Full test suite green after migration (existing + new smoke tests).

### 3.2 Out of scope

- Publishing `universal_editor` to PyPI (separate future task).
- Changing the MCP command interface (names, params, return shapes) — zero breaking changes.
- Migrating `code_analysis/core/` modules unrelated to the editor
  (DB, workers, AST, vector, etc.).
- Changes to sibling projects `mcp_proxy_adapter`, `vast_srv`.

---

## 4. Key constraints

| ID | Constraint |
|----|------------|
| KC-01 | `universal_editor` must have zero runtime imports from `code_analysis.*`. |
| KC-02 | MCP command interface (name, version, params, return) must not change. |
| KC-03 | All existing tests must pass after each G-step. No test regressions. |
| KC-04 | CR-008: no file in `universal_editor/` or remaining `commands/universal_file_edit/` may exceed 400 lines. |
| KC-05 | Backup/sidecar/lock protocols must be fully preserved — no behaviour change. |
| KC-06 | Migration is done file-by-file with `fs_copy` + import rewrite; no mass rename in one step. |
| KC-07 | Each G-step ends with `lint_code → format_code → type_check_code → update_indexes`. |
| KC-08 | `docs/plans/2026-05-20-universal-editor-package/` is the canonical plan directory. |

---

## 5. Success criteria

1. `universal_editor/` package exists at repo root, installable, importable standalone.
2. `import universal_editor` does not transitively import `code_analysis`.
3. All 4 lifecycle commands (`open/edit/write/close`) import exclusively from `universal_editor.*`.
4. Legacy commands (`save/read/delete/replace`) are deleted and unregistered.
5. `pytest tests/` — 100% pass, no new failures.
6. `mypy code_analysis/ universal_editor/` — zero new errors.
7. `flake8 code_analysis/ universal_editor/` — zero new warnings.
8. No file in either package exceeds 400 lines (CR-008).

---

## 6. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Circular import during incremental migration | Medium | High | Migrate leaf modules first (no internal deps); verify with mypy after each file |
| Legacy commands still registered at delete time | Low | High | Audit registration list before deletion; run MCP `help` to confirm absence |
| Sidecar/backup path logic breaks on path change | Medium | High | Keep `path_normalization` interface identical; add smoke tests before migrate |
| CR-008 split creates unexpected public API surface | Low | Medium | Keep all non-command submodules private (`_` prefix or `__all__` restriction) |
| Test isolation — tests that patch `code_analysis.core.*` paths | Medium | Medium | Update patch targets in tests as part of each G-step |

---

## 7. Proposed G-step structure (high level)

```
G-001  Audit & inventory
         T-001  List all files to migrate with line counts and dependency graph
         T-002  Identify all internal import sites that reference migrated modules
         T-003  Identify all test patch targets referencing migrated modules
         T-004  Produce migration order (leaf-first topological sort)

G-002  Package scaffold
         T-001  Create universal_editor/__init__.py and package metadata
         T-002  Register in pyproject.toml / setup.cfg
         T-003  Verify import isolation (no code_analysis import leaks)

G-003  Migrate leaf modules (no intra-editor deps)
         T-001  path_normalization
         T-002  file_lock
         T-003  git_integration
         T-004  backup_manager

G-004  Migrate file_handlers
         T-001  base, diff_support
         T-002  text_handler, json_handler, yaml_handler, python_handler
         T-003  registry, handler_factory
         T-004  Update all import sites in code_analysis/

G-005  Migrate session infrastructure
         T-001  format_group, errors, session
         T-002  tree_temp_write_commit, invalid_write_support
         T-003  Update import sites in command classes

G-006  Rewrite command classes to use universal_editor.*
         T-001  open_command, edit_command
         T-002  write_command
         T-003  close_command
         T-004  Verify: `import universal_editor` has no code_analysis dep

G-007  Delete legacy commands
         T-001  Confirm unregistered (help audit)
         T-002  Delete save/read/delete/replace command files
         T-003  Remove references from registration.py

G-008  Quality gate
         T-001  Full pytest run
         T-002  mypy universal_editor/ code_analysis/
         T-003  flake8 universal_editor/ code_analysis/
         T-004  Line-count audit (CR-008)
         T-005  Smoke test: MCP help lists exactly the 4 lifecycle commands
```

---

## 8. Open questions (to resolve before T-step writing)

| # | Question | Owner |
|---|----------|-------|
| OQ-01 | Should `universal_editor` live at repo root or under a `packages/` directory? | Vasiliy |
| OQ-02 | Does `project_text_file_guard` go into `universal_editor` or stay in `code_analysis/commands/`? | Vasiliy |
| OQ-03 | Should `universal_file_save_command/save_helpers.py` be migrated or deleted along with the legacy save command? | Vasiliy |
| OQ-04 | Is `session_create/delete/list/open_file/close_file/list_file_locks` (session management commands) in scope? They use the same session layer. | Vasiliy |
| OQ-05 | Target Python version / packaging tool for `universal_editor` (`pyproject.toml` only, or also `setup.cfg`)? | Vasiliy |
