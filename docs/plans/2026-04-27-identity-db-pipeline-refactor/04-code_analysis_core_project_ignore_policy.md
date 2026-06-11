# Step 04 — `code_analysis/core/project_ignore_policy.py`

## Goal
Keep ignore/allowlist behavior explicit and shared across watcher, list commands, status aggregates, indexing, and chunking.

## Why this step exists
The project intentionally has both ignore rules and exceptions. `.venv` is normally ignored, but selected distributions under `.venv/site-packages` are allowlisted by config. A weak model must not "fix" bugs by banning `.venv` globally.

## Existing file to inspect
`code_analysis/core/project_ignore_policy.py`

## Current code checked before this step
`project_ignore_policy.py` currently contains pure path filtering primitives such as:
- `path_is_under_project_local_venv`
- `is_ignored_project_relative_path`
- `sql_and_absolute_path_eligible_for_default_status_aggregates`
- `filter_paths_for_default_project_listing`
- `filter_ignore_exception_py_paths_for_watcher`

It does **not** own the full config-to-allowlist expansion. For watcher allowlisted venv files it accepts `allowed_venv_py_files` from the caller. Do not move all config parsing into this file unless the existing architecture already does that.

## Related config fields
In runtime config:
- `code_analysis.ignore_exceptions`
- `code_analysis.venv_site_packages_index_allowlisted_distributions`
- `code_analysis.worker.watch_dirs[].ignore_patterns`
- `code_analysis.file_watcher.ignore_patterns`

## Required investigation
1. List all functions exported by `project_ignore_policy.py`.
2. Identify which callers use each function:
   - file watcher traversal;
   - indexing candidate selection;
   - list_project_files;
   - get_database_status aggregates;
   - chunking candidate selection.
3. Verify the policy distinguishes:
   - ignored non-allowlisted `.venv` files;
   - allowlisted dependency packages passed in by caller;
   - normal project source files.
4. Verify that allowlisted dependency files are scoped by project identity elsewhere. Do not solve DB/file identity inside ignore policy.

## Required changes
Do not change behavior until callers are mapped. If gaps exist, make small patches only:
1. Add a helper for status/query filtering if one is missing.
2. Add a helper for chunking selection if chunking still has duplicated ignore logic.
3. Keep debug logging low-volume. No per-file INFO spam.
4. Keep config expansion outside this module unless there is already a project-level config helper here.

## Must not do
- Do not remove `ignore_exceptions` support.
- Do not globally skip all `.venv` paths.
- Do not make ignore policy responsible for DB identity or conflict cleanup.
- Do not mix this with schema migration.
- Do not implement cross-project relative path conflict handling here; that belongs to Steps 01 and 03.

## Tests to add/update
`tests/test_project_ignore_policy.py`

Required cases:
1. `.venv/lib/python3.12/site-packages/random_pkg/x.py` ignored by default.
2. `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/core/client.py` can be included only when caller passes it as an allowlisted path.
3. Same allowlisted relative path in two different project roots remains project-local; identity behavior is asserted by Step 03 tests, not implemented here.
4. `node_modules`, `.git`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `dist`, `build` ignored by default.

## Runtime verification
After restart:

```text
list_project_files(project_id=<code_analysis>, show_venv=false, limit=100)
get_database_status
view_worker_logs(worker_type="file_watcher", tail=200)
```

Expected:
- default listing is not flooded by `.venv`;
- allowlisted dependencies can still be indexed when explicitly configured;
- no false ownership transfer between projects.

## References
- Identity helper step: `03-code_analysis_core_file_identity.md`
- Watcher traversal step: `07-code_analysis_core_file_watcher_pkg_scanner.md`
- Status consistency step: `14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md`
