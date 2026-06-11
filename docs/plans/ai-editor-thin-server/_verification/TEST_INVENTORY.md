# Test Suite Inventory — Import-Grounded Classification

**Repo:** `/home/vasilyvz/projects/tools/ai_editor`  
**Date:** 2026-06-10  
**Method:** Read-only AST/grep import extraction per test file; each `ai_editor.*` import path verified against current `ai_editor/` tree (module file existence + symbol definition). **OBSOLETE (C) only when import would fail AND removed capability is confirmed gone.**  
**Scope:** `tests/unit/` (57 files), `tests/integration/` (8 files), top-level `tests/*.py` (279 files) — **344 total**.

---

## Per-bucket counts

| Bucket | Unit | Integration + top-level | **Total** |
|--------|-----:|------------------------:|----------:|
| **A — KEEP-GREEN** | 23 | 59 | **82** |
| **B — KEEP-REPAIR** | 0 | 4 | **4** |
| **C — OBSOLETE-DELETE** | 33 | 178 | **211** |
| **D — UNCERTAIN** | 1 | 46 | **47** |
| **Total files** | **57** | **287** | **344** |

---

## User-flagged questions (code evidence)

### (i) Is git still used for undo/redo in the editor?

**Yes — in core, via dulwich `SessionRepo` (not subprocess git).**

| Layer | Path | Symbols |
|-------|------|---------|
| Storage | `ai_editor/core/edit_session/session_repo.py` | `SessionRepo`, `checkout_revision()`, `commit_full()`, `commit_degraded()` |
| Timeline | `ai_editor/core/edit_session/session_history.py` | `SessionHistory`, `undo_index()`, `redo_index()`, `record()` |
| Navigation | `ai_editor/core/edit_session/edit_session_mutations.py` | `undo()`, `redo()`, `checkout_history_index()` |
| Facade | `ai_editor/core/edit_session/edit_session_impl.py` | `EditSession.undo()`, `EditSession.redo()` |

**Reachable from thin MCP workflow today:**

- **History recording:** **Yes** — `universal_file_open` → `create_session` → `SessionRepo.init`; `universal_file_edit` → `_post_mutation_*` → `commit_full/degraded` → `history.record`.
- **Undo/redo invocation:** **No on registered surface** — `SessionUndoCommand` / `SessionRedoCommand` exist (`session_undo_command.py`, `session_redo_command.py`) but are **not registered** in `hooks_register_part2.py`. Same for `session_git_*` commands.

**Test classification implication:** Git-backed **core** tests (`test_session_repo.py`, edit-session lifecycle) → **KEEP (A)**. Tests for **unregistered MCP** `session_undo`/`session_redo`/`session_git_*` as positive command tests → **C** if command modules deleted, else **D** (human: re-register vs delete tests). Negative inventory tests (`test_mcp_help_surface.py`, `test_mcp_workflow_surface_help.py`) → **KEEP (A)**.

**Separate:** Project-level git on disk write (`ai_editor/core/git_integration.py`, `commit_after_write`) is **not** session undo/redo; still present for save/replace paths.

### (ii) Do upload/download transfer functions exist and are they used by the 6 commands?

**Yes — all four symbols exist and three commands use them on primary paths.**

| Symbol | File | Exists |
|--------|------|--------|
| `lock_file_and_download` | `ai_editor/core/upstream/code_analysis_client.py:300` | Yes |
| `upload_session_file_content` | `ai_editor/core/upstream/code_analysis_client.py:339` | Yes |
| `download_without_lock` | `ai_editor/core/upstream/code_analysis_client.py:364` | Yes |
| `upload_create_and_lock` | `ai_editor/core/upstream/code_analysis_client.py:368` | Yes |

Implementation delegates to `ai_editor/core/upstream/code_analysis_file_transfer.py` (`download_file_bytes`, `upload_bytes_transfer_id`, `download_bytes_without_lock`, `upload_create_save`).

| MCP command | Uses transfer symbols? | Evidence |
|-------------|------------------------|----------|
| `universal_file_open` | **Yes** | `open_command_runtime.py:78–87` → `upload_create_and_lock` / `lock_file_and_download` |
| `universal_file_write` | **Yes** | `write_command.py:144–148` → `upload_session_file_content` |
| `universal_file_preview` | **Yes** (one-shot) | `universal_file_preview_runtime.py:224–227` → `download_without_lock` |
| `universal_file_edit` | No (SessionGuard only) | Local draft apply |
| `universal_file_close` | No (`unlock_session_file`) | Unlock RPC, not byte transfer |
| `health` | No | Diagnostics only |

**Test classification implication:** Tests mocking `lock_file_and_download` / `upload_session_file_content` / `download_without_lock` for open/write/preview workflows → **KEEP (A)** — e.g. `test_universal_file_write_upload.py`, `test_universal_file_preview_oneshot.py`, `test_session_guard_write.py`, integration thin-editor tests.

**Removed MCP transfer commands** (`project_file_transfer_by_id`, `advisory_lock_batch`, `lock_status`): only **C** if their **command modules** are deleted and tests import them directly. Surface tests listing them in FORBIDDEN → **A**.

---

## Master inventory — `tests/unit/` (57 files)

| File | Bucket | Subject | Imports resolve? | Recommended action |
|------|--------|---------|------------------|-------------------|
| `tests/unit/test_ca_session_bundle.py` | A | CA session bundle / multi-file registry | Yes | Keep |
| `tests/unit/test_code_analysis_client_session.py` | A | CA client session validation | Yes | Keep |
| `tests/unit/test_edit_session_lifecycle.py` | A | EditSession open/mutate/close | Yes | Keep |
| `tests/unit/test_edit_session_sidecar_workspace.py` | A | Sidecar path confinement | Yes | Keep |
| `tests/unit/test_edit_session_tree_operations.py` | A | Tree ops via EditSession | Yes | Keep |
| `tests/unit/test_editor_workspace_paths.py` | A | Workspace layout paths | Yes | Keep |
| `tests/unit/test_main_queue_init.py` | A | Queue bootstrap | Yes | Keep |
| `tests/unit/test_marker_cycle.py` | A | Marker denude/restore | Yes | Keep |
| `tests/unit/test_mcp_help_surface.py` | A | Registered command surface (6 + health) | Yes | Keep |
| `tests/unit/test_node_id_map.py` | A | Node-id map | Yes | Keep |
| `tests/unit/test_session_guard.py` | A | SessionGuard matrix | Yes | Keep |
| `tests/unit/test_session_guard_cleanup.py` | A | Guard + zombie cleanup | Yes | Keep |
| `tests/unit/test_session_guard_close.py` | A | Close + guard | Yes | Keep |
| `tests/unit/test_session_guard_edit.py` | A | Edit + guard | Yes | Keep |
| `tests/unit/test_session_guard_write.py` | A | Write upload + guard | Yes | Keep |
| `tests/unit/test_session_repo.py` | A | SessionRepo commit model (git history core) | Yes | Keep |
| `tests/unit/test_tree_temp_workspace_paths.py` | A | Tree-temp workspace paths | Yes | Keep |
| `tests/unit/test_universal_file_preview_oneshot.py` | A | Preview one-shot download | Yes | Keep |
| `tests/unit/test_universal_file_write_noop.py` | A | Write no-op branches | Yes | Keep |
| `tests/unit/test_universal_file_write_upload.py` | A | Write commit upload | Yes | Keep |
| `tests/unit/test_workspace_layout.py` | A | Edit subdir allocation | Yes | Keep |
| `tests/unit/test_workspace_session_cleanup.py` | A | Zombie CA session cleanup | Yes | Keep |
| `tests/unit/test_write_compare.py` | A | Write compare logic | Yes | Keep |
| `tests/unit/test_atomic_publication.py` | C | Paginated search atomic I/O | **No** — `core/search_session/atomic_publication.py` | Delete |
| `tests/unit/test_block_assembler.py` | C | Paginated result assembly | **No** — `block_assembler`, `directory`, `raw_finding_buffer` | Delete |
| `tests/unit/test_dead_session_detection.py` | C | Search session liveness | **No** — `dead_detection`, `manifest` | Delete |
| `tests/unit/test_dynamic_file_set.py` | C | Dynamic file sets | **No** — `file_sets/` package | Delete |
| `tests/unit/test_fs_ggrep_pagination_schema.py` | C | fs_ggrep pagination schema | **No** — `fs_ggrep_pagination_schema` | Delete |
| `tests/unit/test_fs_ggrep_structural_mode.py` | C | fs_ggrep structural mode | **No** — `fs_ggrep_structural_integration` | Delete |
| `tests/unit/test_grep_mode_params.py` | C | Grep mode bridge | **No** — `fs_ggrep_structural_integration`, `grep_mode_params` | Delete |
| `tests/unit/test_indexed_file_set.py` | C | Indexed file set | **No** — `file_sets/` | Delete |
| `tests/unit/test_preview_reference.py` | C | Structural preview refs | **No** — `preview_reference` | Delete |
| `tests/unit/test_project_cross_search_pagination_schema.py` | C | Cross-search schema | **No** — `project_cross_search_pagination_schema` | Delete |
| `tests/unit/test_raw_finding_buffer.py` | C | Finding buffer | **No** — `raw_finding_buffer` | Delete |
| `tests/unit/test_result_block.py` | C | Result block assembly | **No** — `result_block` | Delete |
| `tests/unit/test_result_index.py` | C | Result index | **No** — `directory`, `result_index` | Delete |
| `tests/unit/test_search_cancel_command.py` | C | `search_cancel` MCP | **No** — `search_cancel_command`, `directory`, `manifest` | Delete |
| `tests/unit/test_search_close_command.py` | C | `search_close` MCP | **No** — `search_close_command`, `directory`, `manifest` | Delete |
| `tests/unit/test_search_compatibility.py` | C | Legacy→paginated bridge | **No** — `compatibility`, `session` (search) | Delete |
| `tests/unit/test_search_freshness_validation.py` | C | Search freshness | **No** — `file_sets.freshness` | Delete |
| `tests/unit/test_search_get_page_command.py` | C | `search_get_page` MCP | **No** — `search_get_page_command`, core search_session | Delete |
| `tests/unit/test_search_get_status_command.py` | C | `search_get_status` MCP | **No** — `search_get_status_command`, core search_session | Delete |
| `tests/unit/test_search_http_access.py` | C | Search HTTP handlers | **No** — `http_access`, `directory`, `manifest`, `result_*`, `service_metadata` | Delete |
| `tests/unit/test_search_paginated_cross.py` | C | Cross-search pagination | **No** — `search_paginated_cross`, core search_session | Delete |
| `tests/unit/test_search_paginated_fulltext.py` | C | Fulltext pagination | **No** — `search_paginated_fulltext`, core search_session | Delete |
| `tests/unit/test_search_paginated_ggrep.py` | C | fs_ggrep pagination | **No** — `search_paginated_ggrep`, core search_session | Delete |
| `tests/unit/test_search_paginated_semantic.py` | C | Semantic pagination | **No** — `search_paginated_semantic`, core search_session | Delete |
| `tests/unit/test_search_paginated_tree_query.py` | C | Tree-query pagination | **No** — `search_paginated_tree_query`, core search_session | Delete |
| `tests/unit/test_search_session_directory.py` | C | Search session FS layout | **No** — `directory` (search_session) | Delete |
| `tests/unit/test_search_session_schema.py` | C | Pagination schema merge | **No** — `search_session_schema` | Delete |
| `tests/unit/test_search_start_command.py` | C | `search_start` MCP | **No** — `search_start_command`, core search_session | Delete |
| `tests/unit/test_semantic_search_pagination_schema.py` | C | Semantic pagination schema | **No** — `semantic_search_pagination_schema` | Delete |
| `tests/unit/test_session_cleaner.py` | C | Search session cleaner | **No** — `cleaner`, `dead_detection`, `manifest`, `service_metadata` | Delete |
| `tests/unit/test_session_heartbeat.py` | C | Search session heartbeat | **No** — `heartbeat`, `directory`, `manifest` | Delete |
| `tests/unit/test_structural_evidence.py` | C | Structural evidence | **No** — `preview_reference`, `structural_evidence` | Delete |
| `tests/unit/test_xpath_filter.py` | C | XPath filter | **No** — `xpath_filter` | Delete |
| `tests/unit/test_existing_behavior_inventory.py` | D | Plan YAML for removed paginated-search commands | N/A (no `ai_editor` imports) | Human: delete with plan or relocate |

---

## Master inventory — `tests/integration/` (8 files)

| File | Bucket | Subject | Imports resolve? | Recommended action |
|------|--------|---------|------------------|-------------------|
| `tests/integration/test_edit_subdir_edit_stage.py` | A | Edit subdir + transfer mocks | Yes | Keep |
| `tests/integration/test_mcp_workflow_surface_help.py` | A | Negative MCP surface inventory | Yes | Keep |
| `tests/integration/test_multi_file_ca_session.py` | A | Multi-file CA session + transfer | Yes | Keep |
| `tests/integration/test_session_policy.py` | A | Session policy + transfer | Yes | Keep |
| `tests/integration/test_thin_editor_workflow.py` | A | Thin editor E2E | Yes | Keep |
| `tests/integration/__init__.py` | D | Fixture | N/A | Human review |
| `tests/integration/test_commands.py` | C | Fat-server MCP + DB | **No** — `commands/ast/*`, `database_client`, `database_driver_pkg`, `project_management_mcp_commands` | Delete |
| `tests/integration/test_database_driver.py` | C | DB driver stack | **No** — `database_client`, `database_driver_pkg` | Delete |
| `tests/integration/test_workers.py` | C | Workers + DB | **No** — `database_client`, `database_driver_pkg` | Delete |

---

## Master inventory — top-level `tests/*.py` (279 files)

**Full pipe-delimited table (279 rows):** [`docs/reports/test_inventory_integration_toplevel_imports.md`](../../../reports/test_inventory_integration_toplevel_imports.md) (lines 81–358).

**Summary by removed stack (bucket C, 175 top-level + 3 integration = 178 C in integration scope):**

| Removed capability | ~files | Primary missing import proof |
|--------------------|--------|------------------------------|
| DB driver / RPC | ~80 | `ai_editor.core.database_client.client.DatabaseClient` |
| Search MCP | ~15 | `ai_editor.commands.semantic_search_mcp.SemanticSearchMCPCommand` |
| AST/CST MCP commands | ~25 | `ai_editor.commands.cst_load_file_command.CSTLoadFileCommand` |
| Workers / indexing / vectorization | ~25 | `ai_editor.core.indexing_worker_pkg.IndexingWorker` |
| Analysis / quality MCP | ~15 | `ai_editor.commands.comprehensive_analysis_mcp.*` |
| Project / file mgmt MCP | ~18 | `ai_editor.commands.project_management_mcp_commands.*` |

**Bucket A highlights (59 total in integration+top-level scope):** thin-editor workflow tests, `test_universal_file_edit_command.py`, tree-temp session tests, CST core (`cst_query`, `cst_module`, `tree_save_verification`), `test_server_manager_cli.py`, `test_server_manager_daemon_pids.py`, `test_client_server_api_sync.py`, `test_compose_cst_module_ops.py`, `test_batch_insert_replace_stable_id.py`, etc.

---

## B — KEEP-REPAIR list (exact fixes)

| File | Missing symbol (proof) | Exact fix |
|------|------------------------|-----------|
| `tests/test_cst_modify_tree_preview_guard.py` | `ai_editor.commands.cst_modify_tree_preview_guard.{diff_span_exceeds_guard, original_changed_line_span}` — module deleted | Drop test or re-home guard helpers next to `cst_modify_tree_ops_build` if still needed |
| `tests/test_cst_stable_ids.py` | `ai_editor.core.database.file_tree_sync.sync_file_to_db_atomic` — DB sync removed | Remove DB sync assertions; keep CST stable-id tests only |
| `tests/test_markdown_node_ref_edit.py` | `ai_editor.commands.universal_file_read_command.UniversalFileReadCommand` — command removed | Remove read-command setup; use preview/open paths only |
| `tests/test_qa_sleep_health_validate.py` | `ai_editor.commands.qa_sleep_command.QASleepCommand` — module deleted | Split file: keep `HealthCommand` tests; drop QA sleep half |

---

## C — OBSOLETE-DELETE flat list (211 files)

Each entry: **file → first missing module/symbol proof**.

### `tests/unit/` (33 files)

| File | Missing proof |
|------|---------------|
| `tests/unit/test_atomic_publication.py` | `ai_editor.core.search_session.atomic_publication` |
| `tests/unit/test_block_assembler.py` | `ai_editor.core.search_session.block_assembler` |
| `tests/unit/test_dead_session_detection.py` | `ai_editor.core.search_session.dead_detection` |
| `tests/unit/test_dynamic_file_set.py` | `ai_editor.core.search_session.file_sets` |
| `tests/unit/test_fs_ggrep_pagination_schema.py` | `ai_editor.commands.fs_ggrep_pagination_schema` |
| `tests/unit/test_fs_ggrep_structural_mode.py` | `ai_editor.commands.fs_ggrep_structural_integration` |
| `tests/unit/test_grep_mode_params.py` | `ai_editor.commands.fs_ggrep_structural_integration` |
| `tests/unit/test_indexed_file_set.py` | `ai_editor.core.search_session.file_sets.indexed` |
| `tests/unit/test_preview_reference.py` | `ai_editor.core.search_session.preview_reference` |
| `tests/unit/test_project_cross_search_pagination_schema.py` | `ai_editor.commands.project_cross_search_pagination_schema` |
| `tests/unit/test_raw_finding_buffer.py` | `ai_editor.core.search_session.raw_finding_buffer` |
| `tests/unit/test_result_block.py` | `ai_editor.core.search_session.result_block` |
| `tests/unit/test_result_index.py` | `ai_editor.core.search_session.result_index` |
| `tests/unit/test_search_cancel_command.py` | `ai_editor.commands.search_cancel_command` |
| `tests/unit/test_search_close_command.py` | `ai_editor.commands.search_close_command` |
| `tests/unit/test_search_compatibility.py` | `ai_editor.core.search_session.compatibility` |
| `tests/unit/test_search_freshness_validation.py` | `ai_editor.core.search_session.file_sets.freshness` |
| `tests/unit/test_search_get_page_command.py` | `ai_editor.commands.search_get_page_command` |
| `tests/unit/test_search_get_status_command.py` | `ai_editor.commands.search_get_status_command` |
| `tests/unit/test_search_http_access.py` | `ai_editor.core.search_session.http_access` |
| `tests/unit/test_search_paginated_cross.py` | `ai_editor.commands.search_paginated_cross` |
| `tests/unit/test_search_paginated_fulltext.py` | `ai_editor.commands.search_paginated_fulltext` |
| `tests/unit/test_search_paginated_ggrep.py` | `ai_editor.commands.search_paginated_ggrep` |
| `tests/unit/test_search_paginated_semantic.py` | `ai_editor.commands.search_paginated_semantic` |
| `tests/unit/test_search_paginated_tree_query.py` | `ai_editor.commands.search_paginated_tree_query` |
| `tests/unit/test_search_session_directory.py` | `ai_editor.core.search_session.directory` |
| `tests/unit/test_search_session_schema.py` | `ai_editor.core.search_session.search_session_schema` |
| `tests/unit/test_search_start_command.py` | `ai_editor.commands.search_start_command` |
| `tests/unit/test_semantic_search_pagination_schema.py` | `ai_editor.commands.semantic_search_pagination_schema` |
| `tests/unit/test_session_cleaner.py` | `ai_editor.core.search_session.cleaner` |
| `tests/unit/test_session_heartbeat.py` | `ai_editor.core.search_session.heartbeat` |
| `tests/unit/test_structural_evidence.py` | `ai_editor.core.search_session.structural_evidence` |
| `tests/unit/test_xpath_filter.py` | `ai_editor.core.search_session.xpath_filter` |

### `tests/integration/` (3 files)

| File | Missing proof |
|------|---------------|
| `tests/integration/test_commands.py` | `ai_editor.commands.ast.list_files.ListProjectFilesMCPCommand` |
| `tests/integration/test_database_driver.py` | `ai_editor.core.database_client.client.DatabaseClient` |
| `tests/integration/test_workers.py` | `ai_editor.core.database_client.client.DatabaseClient` |

### Top-level `tests/*.py` (175 files)

See complete per-file missing-symbol proofs in [`docs/reports/test_inventory_integration_toplevel_imports.md`](../../../reports/test_inventory_integration_toplevel_imports.md) — filter rows where bucket = `C` (178 rows total in that file includes 3 integration files above).

**Orphan survivors in `core/search_session/` (no standalone green tests):** only `policy.py`, `tree_representation.py` remain; all paginated-search command modules deleted.

**Verified still exist but unregistered (NOT obsolete by import rule):** `move_nodes_command.py`, `queue_health_command.py` — covered by negative surface tests, not direct import failures.

---

## D — UNCERTAIN list (47 files)

| File | Question |
|------|----------|
| `tests/unit/test_existing_behavior_inventory.py` | Plan meta-test for removed paginated-search YAML — delete with plan? |
| `tests/integration/__init__.py` | Empty fixture — keep? |
| `tests/__init__.py`, `tests/conftest.py`, `tests/_preview_diff_probe.py`, `tests/test_config_driver_helpers.py` | Fixtures / no imports — keep as harness? |
| `tests/test_add_file_cross_project_path.py` | Partial DB stub (`database.files.crud`) — delete with DB stack or salvage? |
| `tests/test_code_analysis_client.py` | Imports `ai_editor_client.*` (outside `ai_editor/`) — client package scope vs server thin editor |
| `tests/test_command_execution_job_reconcile.py` | Imports resolve; scope unclear for thin editor |
| `tests/test_constants.py` | Imports `ai_editor.core.constants` — thin-editor relevance? |
| `tests/test_database_driver_config_validator_retry.py` | `config_validator` missing — obsolete or relocated? |
| `tests/test_dependency_compatibility_rejects_old_versions.py` | Imports resolve — keep for packaging? |
| `tests/test_exceptions.py`, `tests/test_project_discovery.py`, `tests/test_path_normalization.py` | Imports resolve — thin vs fat scope |
| `tests/test_fresh_db_startup_schema.py` | No clear thin-editor tie |
| `tests/test_logical_write_submit.py`, `tests/test_watch_dirs_server_instance_partition.py` | Partial DB references — ambiguous |
| *(+ 33 more D files in integration report)* | See [`docs/reports/test_inventory_integration_toplevel_imports.md`](../../../reports/test_inventory_integration_toplevel_imports.md) bucket `D` rows |

---

## Subordinate agents state

| Agent | Objective (one task) | Status | Evidence |
|-------|----------------------|--------|----------|
| `researcher_code` | Git undo/redo usage + MCP reachability | **done** | `SessionRepo`/`EditSession.undo` exist; undo/redo MCP unregistered |
| `researcher_code` | Upload/download symbols + 6-command usage | **done** | All 4 symbols exist; open/write/preview use them |
| `researcher_code` | Import inventory `tests/unit/` (57 files) | **done** | A:23, B:0, C:33, D:1 |
| `researcher_code` | Import inventory `tests/integration/` + top-level (287 files) | **done** | A:59, B:4, C:178, D:46; detail report written |
| `planner_auto` | — | idle | Not invoked |
| `coder_auto` | — | idle | Not invoked (read-only task) |
| `tester_auto` | — | idle | Not invoked (no test runs) |
| `tester_ca` | — | idle | Not invoked |
| `researcher_doc` | — | idle | Not invoked |
| `doc_writer` | — | idle | Not invoked |

**One-task-per-subagent:** confirmed — 4 parallel `researcher_code` runs, each single objective, no bundling.

---

## Verification

**`TEST_INVENTORY.md` verified on disk:** YES  
**Path:** `docs/plans/ai-editor-thin-server/_verification/TEST_INVENTORY.md`

**Supporting detail report (287 integration+top-level rows):** `docs/reports/test_inventory_integration_toplevel_imports.md`
