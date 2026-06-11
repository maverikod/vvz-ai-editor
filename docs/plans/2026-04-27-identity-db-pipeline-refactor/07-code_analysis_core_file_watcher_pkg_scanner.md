# Step 07 — `code_analysis/core/file_watcher_pkg/scanner.py`

## Goal
Ensure file watcher traversal applies ignore policy early, but still respects explicit allowlisted dependency exceptions from config.

## Why this step exists
Earlier watcher behavior descended into `.venv/site-packages` too broadly and caused CPU spikes and polluted DB state. A later fix introduced shared ignore policy and allowlist handling. This step makes that behavior explicit and testable.

## File to inspect first
`code_analysis/core/file_watcher_pkg/scanner.py`

## Important scope note
`scanner.py` is the primary file, but do **not** assume all allowlist merge logic lives there. Trace the call chain before changing code. Allowlist expansion, project discovery, pre-scan purge, or worker orchestration may live in related modules.

## Related files
- `code_analysis/core/project_ignore_policy.py`
- `code_analysis/core/file_watcher_pkg/project_discovery.py`
- `code_analysis/core/file_watcher_pkg/multi_project_worker_scan.py`
- `code_analysis/core/file_watcher_pkg/ignore_pre_scan_purge.py`
- `tests/test_scanner_with_discovery.py`
- `tests/test_project_ignore_policy.py`

## Required code search before edits
Use MCP source search/read tools before editing:

```text
fulltext_search(query="os.walk should_skip_dir should_prune_ignored_dir ignore_exceptions allowed_venv_py_files")
fulltext_search(query="filter_ignore_exception_py_paths_for_watcher allowed_venv_py_files")
file_structure(file_path="code_analysis/core/file_watcher_pkg/scanner.py")
read_project_text_file(file_path="code_analysis/core/file_watcher_pkg/scanner.py", ...)
```

If `fulltext_search` returns no results for an exact query, read the candidate files directly.

## Required checks
1. Identify the traversal function using `os.walk` or equivalent.
2. Confirm ignored directories are pruned before recursion.
3. Confirm `.venv`, `venv`, `.git`, `node_modules`, caches, `dist`, `build` are not traversed broadly.
4. Confirm allowlisted `.venv/site-packages` files are discovered by explicit merge logic, not by walking the whole `.venv` tree.
5. Confirm watcher does not enqueue non-allowlisted venv files for indexing.
6. Confirm log level for skipped directories is DEBUG, not INFO spam.
7. Confirm watcher discovery finds only intended projects.

## Required changes
Only if checks fail:
1. Use shared helpers from `project_ignore_policy.py`.
2. Do not duplicate ignore pattern logic in scanner.
3. Ensure explicit allowlist merge is bounded and does not recursively scan all site-packages.
4. Add counters rather than per-file logs.

## Must not do
- Do not globally ban configured allowlisted dependencies.
- Do not index all `.venv` again.
- Do not use project-relative path as global identity.
- Do not make destructive DB changes from scanner.
- Do not move DB identity/conflict logic into ignore policy.

## Tests
Update or create tests covering:
1. Project with `.venv/lib/python3.12/site-packages/random_pkg/x.py` → ignored.
2. Project with allowlisted `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/core/client.py` → included only if config allowlist says so.
3. Three-project watch dir regression → no full `.venv` descent.
4. `Ignoring projectid below project root` is not treated as error when expected.
5. Non-allowlisted venv files are not enqueued for indexing.

Suggested command:

```text
python -m pytest tests/test_scanner_with_discovery.py tests/test_project_ignore_policy.py -v
```

## Runtime verification
After restart:

```text
get_worker_status(worker_type="file_watcher")
view_worker_logs(worker_type="file_watcher", tail=200)
get_database_status
```

Expected:
- watcher reaches idle;
- CPU drops after scan;
- no full `.venv` traversal;
- no false cross-project ownership transfer.

## References
- Ignore policy step: `04-code_analysis_core_project_ignore_policy.md`
- File identity step: `03-code_analysis_core_file_identity.md`
