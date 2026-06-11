# Parallelization Map — eliminate-direct-codedatabase

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

---

## Dependency Graph

```
Phase 1 (no deps, parallel):

  [step-01]  [step-02]  [step-04]  [step-05]
      |          |
      +----+----+
           |
       [step-03]          [step-07] (STOP: Approach A/B)

Phase 3 (sequential after decision on 07):

           [step-09]  (NEW file)
           /       \
      [step-08]  [step-10]
                    |
                [step-06]

Phase 4 (only after 01-10 complete + reindex passes):

           [step-11]  (STOP: Approach A/B)
```

Detailed arrows:
- 01 → 03
- 02 → 03
- 09 → 08
- 09 → 10
- 10 → 06
- 01..10 all done + reindex → 11

---

## Phase 1 — no dependencies, can start immediately

All four steps touch different files and share no state.
**Run in parallel.**

| Step | Target file | Risk |
|------|-------------|------|
| 01 | `core/faiss_manager_sync.py` | LOW |
| 02 | `core/faiss_manager_rebuild.py` | LOW |
| 04 | `cli/config_cli_commands.py` | LOW |
| 05 | `main_workers.py` | LOW |

**Barrier:** start step 03 only after both 01 AND 02 complete and pass lint/typecheck.

---

## Phase 1b — depends on 01 + 02

| Step | Target file | Risk | Depends on |
|------|-------------|------|------------|
| 03 | `core/faiss_manager.py` | LOW | 01, 02 |

**Rule:** start after both 01 and 02 are validated. Touches type signatures only.

**Gate after Phase 1 + 1b:** run `comprehensive_analysis` on all five changed files.

---

## Phase 2 — architecture decision gate

| Step | Target file | Risk | Condition |
|------|-------------|------|-----------|
| 07 | `core/database_driver_pkg/rpc_handlers_file_trash.py` | MEDIUM | **STOP: choose A or B** |

**STOP before implementing.** Present user with:

- **Approach A:** extract trash logic to `trash_standalone.py` (~200+ lines).
  Read `core/database/files/trash.py` (438 lines, 4 functions) in full before writing.
  Map every `self._execute`, `self._fetchone`, `self._commit`, `self.get_project`,
  `self.get_file_by_path`, `self.clear_file_data` call. Never guess SQL.
- **Approach B:** document `_get_code_db()` as an accepted architectural exception
  with a comment. No code change beyond the comment.
  Safe: `from_existing_driver` reuses the existing connection, does not call
  `sync_schema()`, does not open a second connection.

Can start implementation in parallel with Phase 1 once user decision is received.

---

## Phase 3 — core indexing pipeline (strictly sequential)

| Step | Target file(s) | Risk | Depends on |
|------|----------------|------|------------|
| 09 | NEW `core/database/files/update_standalone.py` | HIGH | — |
| 08 | `core/database_driver_pkg/rpc_handlers_index_file.py` | HIGH | 09 |
| 10 | extend `update_standalone.py` + fix `vectorize_after_index.py` | MEDIUM | 09 |
| 06 | `core/indexing_worker_pkg/vectorize_after_index.py` | MEDIUM | 10 |

**Execution order: 09 → 08 → 10 → 06.**

Note: steps 08 and 10 both depend only on 09 and touch different files,
so they CAN technically run in parallel after 09. Recommended: sequential
for easier debugging (one conceptual domain).

**Gate after step 09:** lint + typecheck `update_standalone.py`, no stubs.
**Gate after step 08:** full reindex `update_indexes(project_id=...)`,
  verify `functions > 0` and `cst_node_id != ''`.
**Gate after step 10:** trigger file change, verify `embedding_vector`
  non-NULL in `code_chunks` for the indexed file.
**Gate after step 06:** trigger full indexing cycle, verify vectorization
  completes without `AttributeError`.

---

## Phase 4 — legacy cleanup (STOP + user decision)

| Step | Target | Risk | Depends on |
|------|--------|------|------------|
| 11 | `core/db_driver/` (delete) + `CodeDatabase.__init__` rewrite | MEDIUM | 01–10 all complete |

**STOP before starting.** Consult user: choose Approach A or B.
See `step-11-delete-db-driver.md` for full details.

- **Approach A:** Rewrite `CodeDatabase.__init__` to use
  `database_driver_pkg.driver_factory.create_driver`. Rewrite `_invoke_driver_execute`,
  `_execute`, `_fetchone`, `_fetchall`, `_commit` to use new driver interface.
  Tests continue to use `CodeDatabase(driver_config)` — no test migration needed.
- **Approach B:** Delete `CodeDatabase` entirely and migrate ~30 test fixtures
  to use `DatabaseClient` or raw driver. Architecturally cleaner, larger scope.

Run only after:
1. All steps 01–10 complete and validated.
2. Full reindex test passes (`functions > 0`, `cst_node_id` populated).
3. Post-refactoring cleanup grep returns 0 matches (see README).

---

## Recommended execution timeline (single executor)

```
T0  Start steps 01, 02, 04, 05 in parallel.
    STOP: ask user for step 07 Approach A/B decision.

T1  Steps 01, 02, 04, 05 done. Lint/typecheck each.
    Start step 03.
    Start step 09 (independent).
    (Start step 07 implementation if user decision received.)

T2  Step 03 done. Lint/typecheck.
    comprehensive_analysis on files from steps 01–05.
    Step 09 done. Lint/typecheck update_standalone.py.
    Start steps 08 and 10.

T3  Step 08 done. Full reindex test. Check functions > 0.
    Step 10 done. Trigger file change. Check embedding_vector.
    Start step 06.

T4  Step 07 done (if Approach A: trash_standalone.py).
    Test trash ops end-to-end: delete/restore/list.
    Step 06 done. Full indexing cycle. No AttributeError.

T5  All steps 01–10 done.
    Run comprehensive_analysis on all changed files.
    Run cleanup grep: must return 0 production CodeDatabase matches.
    Full reindex test (final gate).
    STOP: ask user for step 11 Approach A/B decision.

T6  User decision received.
    Run pre-deletion checklist (see step-11).
    Execute step 11: rewrite CodeDatabase.__init__ (Approach A)
    or delete CodeDatabase (Approach B), then delete db_driver/.
    pytest tests/ -x.
    Server restart + full reindex.

T7  All tests pass. Done.
```

---

## Validation gates summary

| After | Gate |
|-------|------|
| Each individual step | `lint_code` → `format_code` → `type_check_code`. Stop on any error. |
| Steps 01–05 complete | `comprehensive_analysis` on all 5 changed files |
| Step 07 complete | End-to-end trash test: delete / restore / list |
| Step 09 complete | `comprehensive_analysis(check_stubs=True)` on `update_standalone.py` |
| Step 08 complete | `update_indexes(project_id=...)`, check `functions > 0`, `cst_node_id != ''` |
| Step 10 complete | Trigger file change; verify `code_chunks.embedding_vector IS NOT NULL` |
| Step 06 complete | Full indexing cycle; no `AttributeError` on vectorization |
| All 01–10 complete | Cleanup grep: 0 production `CodeDatabase` matches (see README) |
| Step 11 complete | `pytest tests/ -x`; server restart; full reindex |

---

## Execution rules for executor

### General rules (apply to every step)

1. **Fresh node_id before every edit.**
   Node IDs in step files are stale (captured at write time).
   Before every `cst_modify_tree`:
   ```
   tree_id = cst_load_file(file_path=..., project_id=...)
   node = cst_find_node(tree_id=tree_id, ...)  # or cst_get_node_by_range
   # use node["node_id"], not the ID from the step file
   ```

2. **Preview before apply (CL-02).**
   For every `cst_save_tree` or `compose_cst_module`:
   first inspect the diff with `preview=true`, then apply.
   Never skip the preview step.

3. **Post-edit sequence (CL-06).**
   After every Python file change:
   `lint_code` → `format_code` → `type_check_code`.
   Stop on any error. Do not proceed to the next step until clean.

4. **No silent fallback.**
   If a CST command fails, STOP and report the exact error message and command.
   Wait for user decision. Do not automatically switch to `search_replace` or `write`.

5. **Read before writing SQL.**
   Steps 04, 05, 09 involve SQL. Never guess SQL.
   Always read the source file to verify exact SQL before writing any replacement.
   Step 10 has no SQL — do not write any.

6. **New Python files: use `cst_create_file`.**
   Step 09 creates `update_standalone.py`. Use `cst_create_file`, not `write`.

7. **Markdown plan files: use `universal_file_save` or `universal_file_replace`.**
   Not CST tools.

8. **One step at a time within a sequential phase.**
   Complete and validate a step before starting the next in the same chain.
   Exception: Phase 1 steps 01, 02, 04, 05 are explicitly parallel-safe.

9. **Batch reads: use `read_only_batch`.**
   When researching multiple files before a step, combine reads into one call
   to minimize round-trips (CL-05).

### Step 09 rules (HIGH risk)

- Read `core/database/files/update.py` (401 lines) in full before implementing.
- Read `commands/update_indexes_analyzer.py` to verify `analyze_file` signature
  and confirm it accepts `DatabaseClient`.
- Check `core/database/files/atomic.py` — may contain a driver-based shortcut
  that simplifies step 09 significantly.
- `analyze_file` is a plain `def` (not `async def`) — call without `await`.
- Use `cst_create_file` for the new `update_standalone.py`.
- After creating: `comprehensive_analysis(check_stubs=True)` to confirm no stubs.

### Step 08 rules (HIGH risk, depends on 09)

- Apply ONLY after step 09 is validated.
- Three operations in one `cst_modify_tree` session (load once, modify, save once):
  1. Delete `logger.debug` at lines 105–107 (NOT inside try-block — separate delete).
  2. Delete local `CodeDatabase` import at line 103.
  3. Replace try-block (lines 108–125) with the new `update_file_data_via_driver` call.
- Re-verify all node_ids via `cst_load_file` + `cst_find_node` before editing.
- After applying: full reindex test. Verify `functions > 0` and `cst_node_id != ''`.

### Step 10 rules (MEDIUM risk, depends on 09)

- Apply ONLY after step 09 is validated.
- No SQL involved. `DocstringChunker` already supports `DatabaseClient` natively
  via its dual-path in `_file_still_exists_and_not_deleted` and
  `_persist_code_chunk_param_rows`. Do not rewrite any SQL.
- Two files to change:
  1. `update_standalone.py`: add `_vectorize_via_client` and
     `update_and_vectorize_via_driver` (see step-10 for full verified code).
  2. `vectorize_after_index.py`: replace `_vectorize_file_immediately` body
     to call `_vectorize_via_client` instead of `db.vectorize_file_immediately()`.
- Use `cst_load_file` → `cst_modify_tree` → `cst_save_tree` for both files.

### Step 06 rules (MEDIUM risk, depends on 10)

- Apply ONLY after step 10 is validated.
- Replace `_create_database` (no `_in_process_driver` attribute — see step-06).
- Replace `_close_driver` (simplified: only `rpc_client.disconnect()`).
- Update docstring of `vectorize_file_after_index`.
- After applying: trigger a file change, verify full vectorization cycle completes.

### Step 11 rules (MEDIUM risk, last)

- STOP. Present user with Approach A/B. Wait for decision.
- Run pre-deletion checklist from step-11 file before touching anything.
- Approach A minimum: rewrite `CodeDatabase.__init__` to use
  `database_driver_pkg.driver_factory.create_driver`; rewrite internal
  `_execute`/`_fetchone`/`_fetchall`/`_commit` methods for new driver interface.
- After deletion: `pytest tests/ -x` must pass cleanly before declaring done.

---

## When to STOP and wait for user

| Situation | Action |
|-----------|---------|
| Any step fails with an error | STOP. Report exact error + command + file. Wait for decision. |
| Starting step 07 | STOP. Present Approach A/B. Wait for user choice. |
| Starting step 11 | STOP. Present Approach A/B. Wait for user choice. |
| `comprehensive_analysis` finds new errors | STOP. Report all issues. Fix before proceeding. |
| Reindex test: `functions = 0` or `cst_node_id = ''` | STOP. Report. Do not start step 11. |
| `pytest tests/ -x` fails after step 11 | STOP. Restore backup. Report. |
| lint/typecheck fails on any file | STOP. Fix. Rerun before the next step. |
| Cleanup grep returns production matches | STOP. Investigate. Fix before step 11. |
