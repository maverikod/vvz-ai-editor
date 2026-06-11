# list_project_files

**Command name:** `list_project_files`  
**Class:** `ListProjectFilesMCPCommand`  
**Source:** `code_analysis/commands/ast/list_files.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The `list_project_files` command enumerates **project files on disk** (by default ordinary non-binary files under the root; use `python_only: true` for legacy **`.py`-only** indexing-aligned walks), then **joins database rows** when a non-deleted indexed file matches the same normalized relative path. Dot-prefixed directories, tool cache dirs, and project-local `.venv` / `venv` are **excluded by default** (like `ls` without `-a`); opt in with `show_hidden` (hidden + caches, `ls -a`-style), `show_venv`, or `include_venv_ignore_exceptions` (see below).

Operation flow:

1. Resolves project root from `project_id` (via the database).
2. Opens the database connection.
3. Loads non-deleted `files` rows for the project (for metadata lookup).
4. Enumerates files on disk:
   - By default, project tree **excluding** dot-prefixed directories (except what appears via other flags), project-local `.venv` / `venv`, **cache dirs** (`__pycache__`, `.mypy_cache`, …), and other shared ignore rules (`node_modules`, `dist`, …). With `show_hidden: true`, listing follows **`ls -a`**: dotdirs (except `.venv`/`venv` roots) and cache basenames are descended; bytecode/binary suffixes still skipped; bulky dirs like `node_modules` remain excluded.
   - With `show_venv: true`, **additionally** includes only **config-allowlisted** virtualenv `site-packages` `.py` files resolved from pip **RECORD** entries (see `venv_site_packages_index_allowlisted_distributions` in server config). The **entire** virtualenv is never listed.
   - With `include_venv_ignore_exceptions: true`, `code_analysis.ignore_exceptions` matches under `.venv` / `venv` are included (default: excluded).
5. If `file_pattern` is set, filters relative paths with `fnmatch`.
6. Sorts paths stably (by relative path string), then applies `offset` / `limit`.
7. For each filesystem path, if a DB row matches, returns the usual DB-backed fields; otherwise returns a minimal row (`project_id`, `path`, `relative_path`, `deleted: false`).

Important notes:

- **Filesystem-first:** Rows that exist only in the database but not on disk are **omitted**.
- By default, **no** files under project-local `.venv` / `venv` are enumerated (except what `show_venv` adds as allowlisted RECORD paths).
- Response shape is unchanged: `success`, `files`, `count`, `total`, `offset`.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from `create_project` or `list_projects`). |
| `file_pattern` | string | No | Optional `fnmatch` pattern on the **full** path relative to project root (see command metadata). |
| `glob` | string | No | Same as `file_pattern` if the client uses this name; non-empty `file_pattern` wins when both are set. |
| `limit` | integer | No | Max number of results after sort (pagination). |
| `offset` | integer | No | Skip N results after sort. Default: `0`. |
| `show_venv` | boolean | No | Default `false`. When `true`, add allowlisted venv `site-packages` `.py` files (RECORD-based). Does not expose arbitrary paths under `.venv`/`venv` without `include_venv_ignore_exceptions`. |
| `python_only` | boolean | No | Default `false`. When `true`, enumerate only `.py` files (legacy indexing-aligned walk). |
| `include_venv_ignore_exceptions` | boolean | No | Default `false`. When `true`, include `ignore_exceptions` matches under `.venv` / `venv`. |
| `show_hidden` | boolean | No | Default `false`. When `true`, **`ls -a`‑style**: descend into dot-prefixed directories (except project `.venv`/`venv`) and into cache basenames (`__pycache__`, `.mypy_cache`, …). `node_modules` / `dist` / … stay excluded. |

**Schema:** `additionalProperties: false` — only the parameters listed in `get_schema()` for this command are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success.
- `files`: List of dicts. Indexed files include fields from the database (e.g. `id`, `path`, `relative_path`, `lines`, timestamps). Files present on disk but not indexed include at least `project_id`, `path`, `relative_path`, and `deleted`.
- `count`: Number of files in the current page (after pagination).
- `total`: Total matching files before pagination.
- `offset`: Offset used.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** `PROJECT_NOT_FOUND`, `LIST_FILES_ERROR` (and others).

---

## Examples

### Correct usage

**List all project `.py` files on disk (default — venv trees skipped)**

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Filter by pattern**

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_pattern": "src/*.py"
}
```

**Include allowlisted venv site-packages files**

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "show_venv": true
}
```

**Pagination**

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "limit": 100,
  "offset": 0
}
```

### Incorrect usage

- **`PROJECT_NOT_FOUND`:** Unknown or invalid `project_id` — use `list_projects` or the `projectid` file in the project root.

- **`LIST_FILES_ERROR`:** Database or filesystem error — check project root exists and configuration.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not in database | Register project; verify `project_id`. |
| `LIST_FILES_ERROR` | General listing error | Check logs, DB, and project root path. |

## Best practices

- Use `file_pattern` to narrow large trees.
- Use `limit` / `offset` after checking `total`.
- Use `show_venv` only when specific distributions are allowlisted in config and you need those RECORD-listed `.py` paths.
- Compare results with `update_indexes` / indexing expectations: unindexed files appear with minimal metadata only.

---
