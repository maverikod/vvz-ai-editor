<!--
Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
Status: implementation TODO — read this first on session handoff
Project: code_analysis (UUID 8772a086-688d-4198-a0c4-f03817cc0e6c)
Companion: unified_search_target_architecture.md (the "why")
-->

# Unified Search — Implementation TODO (handoff plan)

Read `unified_search_target_architecture.md` for the rationale. This file is the
actionable plan: what to do, in order, with enough detail to resume without
digging through chat history.

## Hard rules (project, non-negotiable)

- All file writes via MCP `universal_file_*` lifecycle. No direct filesystem.
- Edit lifecycle: open -> preview(session_id) -> edit -> write(preview) ->
  write(commit) -> close. Re-preview after every edit (node_ref goes stale).
- `update_indexes` is FORBIDDEN (explicit user rule, overrides CR-006).
- Post-edit Python sequence: `black` -> `flake8` -> `mypy` (CR-007). NOT
  update_indexes.
- CR-008 (module size) — ignore (recorded stale in memory).
- Do not touch sibling projects (mcp_proxy_adapter, vast_srv).
- Queue system: workers are running (3 processes, verified), but queue job
  dispatch is NOT working (search_start returns "Queue system is not running").
  Use terminal_run_host for verification scripts instead.
- Locale: chat ru, code/docs/comments en.
- Verification: always run on real data via terminal_run_host, not sandbox
  (sandbox lacks mcp_proxy_adapter). Script path pattern:
  `cd /home/vasilyvz/projects/tools/code_analysis && .venv/bin/python scripts/verify_*.py`

## Settled design decisions (do not re-litigate)

- **Finding = address-only.** A finding carries `(file_path, stable_id)` +
  metrics (score, mtime). NO materialized preview text inside the finding.
- **Preview is lazy, by address, at output time.**
- **Scoring is a shared layer** via `score_for_source(source, raw) -> float`.
- **grep = enriched node_ref path.** `normalize_ggrep_match` returns `None`
  for unenriched (no node_ref) matches — they are dropped, not written as
  line-only findings. Same pattern as cross: no stable_id -> None.
- **Relevance order:** `score DESC -> mtime ASC -> result_id`.
- **index.json format** already final (temporal_blocks / relevance_blocks /
  completeness / blocks alias); `reordered` already removed.
- **`Finding.from_dict`** restores `source` as `FindingSource` enum (fixed
  this session — was plain str before).

## File map (verified paths)

- Finding entity: `code_analysis/core/search_session/finding.py`
- Assembler: `code_analysis/core/search_session/block_assembler.py` (state machine done)
- Pure packer: `code_analysis/core/search_session/result_block.py`
- Buffer: `code_analysis/core/search_session/raw_finding_buffer.py`
- Index: `code_analysis/core/search_session/result_index.py`
- Layout: `code_analysis/core/search_session/directory.py`
- DB producer: `code_analysis/commands/search_paginated_cross.py`
- Grep producer: `code_analysis/commands/search_paginated_ggrep.py`
- Fulltext producer: `code_analysis/commands/search_paginated_fulltext.py`
- Semantic producer: `code_analysis/commands/search_paginated_semantic.py`
- Tree-query producer: `code_analysis/commands/search_paginated_tree_query.py`
- Search start: `code_analysis/commands/search_start_command.py`
- Page access: `code_analysis/commands/search_get_page_command.py` (ordering param done)
- Grep seam: `code_analysis/commands/grep_block_resolver.py`
- Verification scripts: `scripts/verify_s2_normalize.py` (14/14 PASS),
  `scripts/verify_s4_assembler.py` (pending run)
## TODO

### Stage S0 — project file list + split (DB list / grep list)

- [x] S0.4(core). PURE `split_search_file_sets` implemented + verified on real
      data (2585 files -> 2583 db / 2 grep; disjoint; invariants confirmed).
- [x] S0.6(core). black/flake8/mypy clean + real-data run.
- [ ] S0.1. (command/service layer — built at S2/S3, nothing to wire before)
      Gather `disk_files` + `disk_metadata` via
      `enumerate_project_paths(root, show_venv=False, python_only=False)`
      + `os.stat().st_mtime`.
- [ ] S0.2. Gather `database_files` via
      `DatabaseClient.get_project_file_rows(project_id, include_deleted=False)`
      (RAW Unix-ts). NOT `get_project_files` (Julian parse bug).
- [ ] S0.3. Call `split_search_file_sets(...)`. Snapshot at start.

### Stage S1 — Finding entity (the foundation)

- [x] S1.1. `Finding` frozen dataclass: `result_id, source, file_path,
      stable_id, score, mtime`. `.address` property. `to_dict`/`from_dict`.
      `from_dict` now restores `source` as `FindingSource` enum (fixed).
- [x] S1.2. `score_for_source(source, raw) -> float`. Verified 14/14 PASS
      on real-shaped dicts.

### Stage S2 — DB producer writes Findings

- [x] S2.1. `normalize_cross_finding` returns `Optional[Finding]`.
      `stable_id` from `evidence.node_ref` -> `raw.node_ref` ->
      `evidence.block_id` -> `raw.block_id`; no stable_id -> `None`.
      `_write_findings` calls `finding.to_dict()`. black/flake8/mypy clean.
- [x] S2.2. Real-data verification: 14/14 PASS on
      `scripts/verify_s2_normalize.py` (terminal_run_host).

### Stage S3 — grep producer writes Findings

- [x] S3.1-S3.3. `normalize_ggrep_match` returns `Optional[Finding]`.
      `stable_id` from `raw.node_ref` -> `evidence.node_ref` ->
      `raw.block_id` -> `evidence.block_id`; no stable_id or file_path ->
      `None`. `run_paginated_ggrep` guards on `None`, calls `finding.to_dict()`.
      black/flake8/mypy clean.
- [ ] S3.4. VERIFY seam details (studied, not formally verified by run):
      `_LineBlockIndex.lookup` in `grep_block_resolver.py` returns
      `(stable_id, node_type)` — smallest covering node from
      `_PREFERRED_SIDECAR_KINDS = {method, function, class, stmt, smallstmt,
      module}`. Current selection rule = smallest covering node (not nearest
      named ancestor — design decision deferred). `_build_index(abs_path)`
      is the factory: Python -> sidecar; JSON/YAML -> in-memory tree;
      MD -> markdown-it.
- [ ] S3.5. Verification script for grep producer (mirror of verify_s2).
      NOTE: queue dispatch broken, so can't test end-to-end via search_start;
      test normalize_ggrep_match in isolation with enriched raw dicts.

### Stage S4 — assembler (collect + sort), written against Finding

- [x] S4.1-S4.9. `BlockAssembler` state machine DONE. black/flake8/mypy clean.
      Changes: added idempotent guard (`read_index` check at entry), removed
      `finalize_index` callback from constructor and all 6 callers (cross, ggrep,
      fulltext, semantic, tree_query, search_start), removed `remove_findings`
      from drain loop, added `_finalize()` with `_build_relevance_blocks()`
      (sort `score DESC -> mtime ASC -> result_id`, write `blocks_relevance/`).
- [x] S4.10. All 6 `_make_block_assembler` / `_create_block_assembler` callers
      updated — `finalize_index` closure and kwarg removed everywhere.
- [x] S4.11. `search_get_page_command.py`: `ordering` param (temporal|relevance)
      added. Reads `blocks/` or `blocks_relevance/` accordingly. `has_more`
      logic differs per ordering.
- [ ] S4.12. Verification: `scripts/verify_s4_assembler.py` created but
      `terminal_run_host` queue blocked (pending/timeout). Run manually:
      `cd /home/vasilyvz/projects/tools/code_analysis && .venv/bin/python scripts/verify_s4_assembler.py`
### Stage S5 — remove legacy wrappers

- [ ] S5.1. Remove five `search_paginated_*` legacy commands once unified
      pipeline carries their behavior. Wire three producers (DB / grep /
      AST+XPath). AST/XPath already emits `node_ref=stable_id` (score 1.0) —
      confirm maps onto Finding contract. Update command registry.
- [ ] S5.2. Full test pass. Commit.

## Resume checklist (every session)

1. `list_projects` -> confirm UUID `8772a086-688d-4198-a0c4-f03817cc0e6c`.
2. `get_worker_status` -> note if queue running (affects search_start).
3. Check for orphaned `.write` files and live edit sessions in
   `core/search_session/` and `commands/`; close orphans before editing.
4. Re-preview any target file before editing (never trust prior node_ref).
5. MCP index is DESYNCED — use `universal_file_preview` (reads disk directly)
   for all files; terminal_run_host for verification scripts.
6. Terminal writer session: `5756ba01-0c64-46ab-bf23-ff6ef51c1342`.
   Use `terminal_run_host` for host execution (not sandbox — lacks
   mcp_proxy_adapter). Pattern:
   `cd /home/vasilyvz/projects/tools/code_analysis && .venv/bin/python scripts/X.py`
7. Mandatory reads before any code task: FILE_EDIT_WORKFLOW.yaml,
   FILE_VIEW_WORKFLOW.yaml, PROJECT_RULES.md, target files.
