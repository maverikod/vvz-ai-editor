# G-003 Remediation: {h008} Six-Operation Unification via apply_edit_operation

## Purpose

Unify EditSession valid-mode structural edits with the G-004 six-operation dispatch (`code_analysis/tree/edit_operations.apply_edit_operation`) so that while `tree_validity` is VALID, all edits use integer short_id addressing and operations {h001}-{h007}, preserving the {d003} per-mutation cycle (denude → op on marked TREE → restore → unmark export → CHECKSUMS → SessionRepo commit).

## Parent links

- HRS: `docs/plans/marked_tree_unification/source_spec.md` — `{h008}`, `{h001}`-`{h007}`, `{a007}`, `{d003}`, `{n003}`
- MRS: `docs/plans/marked_tree_unification/spec.yaml` — C-012 EditSession, C-024 EditOperation dispatch
- Global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`

## Research verdict (2026-05-31)

**INCOHERENT** — `apply_edit_operation` has zero production callers. Valid-mode paths use whole-source denude/restore with UUID/json_pointer/line addressing. Python sidecar bypasses EditSession and {d003}. Must unify at command boundary; G-004 must NOT modify EditSession entity internals.

## Scope

**Included:**
1. New adapter `code_analysis/core/edit_session/edit_operations_adapter.py`:
   - `apply_edit_on_session_tree(session: EditSession, operation: EditOperation) -> None`
   - Algorithm: read session `.tree` → parse TREE section + `next_free` from MAP → `apply_edit_operation(registry, source_path, marked_text, operation, tree_is_valid=True, next_free=...)` → splice updated TREE into full tree file → write session tree → call existing post-mutation (`_post_mutation_full` via public wrapper e.g. `EditSession.apply_tree_operation(operation)`)

2. `code_analysis/commands/universal_file_edit/session.py`:
   - Add `apply_tree_operation(session: EditSession, operation: EditOperation) -> None` delegating to core adapter

3. `code_analysis/commands/universal_file_edit/tree_temp_edit_batch.py`:
   - Map insert/delete/replace (and move when present) from command ops to `EditOperation` with integer `short_id` from `node_ref`
   - Replace serialize + `apply_source_mutation(lambda _: whole)` path for valid sessions
   - Retire or gate `_run_legacy_tree_temp_apply` for valid-mode sessions

4. `code_analysis/commands/universal_file_edit/text_draft_apply.py`:
   - Resolve `node_ref` to short_id; dispatch via `apply_tree_operation`

5. `code_analysis/commands/universal_file_edit/sidecar_cst_apply.py`:
   - Route valid-session Python edits through `apply_tree_operation`; stop `write_sidecar_atomic` on live path during active session

6. `code_analysis/commands/universal_file_edit/move_nodes_command.py`:
   - Use `MOVE` EditOperation through session adapter

7. `code_analysis/commands/universal_file_edit/open_command.py`:
   - Stop `_write_sidecar_draft` from overwriting unified `.tree` with `CST_TREE_V1` format

8. `code_analysis/commands/universal_file_edit/format_group.py`:
   - Expose all six ops in `available_operations` per format group where handlers support them

9. Tests proving valid-session edits use short_id + `apply_edit_operation`:
   - `tests/unit/test_edit_session_tree_operations.py` — mock/spy or integration asserting `EditOperationKind` dispatch and short_id preservation

**Excluded:**
- G-004 changes to `code_analysis/tree/edit_operations.py` (already complete)
- Preview routing fixes (G-004 owns 6 failing preview tests)
- HRS/MRS edits

## Boundaries

- Do not modify `code_analysis/tree/edit_operations.py` or handler op implementations (G-004)
- EditSession lifecycle entity (`open/close/revalidate`) stays in G-003; only add thin `apply_tree_operation` public method
- Do not fix `test_tree_temp_edit_session_preview.py` node_ref failures (G-004)

## Dependencies

- G-004 `apply_edit_operation` + `op_edit_attributes` complete
- Prior G-003 remediation (integration, SessionRepo) complete

## Parallelization note

Phase 1 (adapter + tree_temp) blocks tests. Phase 2 (text, sidecar, move, open) can parallelize after adapter lands.

## Expected outcome

- Production valid-mode edits call `apply_edit_operation` with integer short_id
- {d003} invariant holds for Python path (no external CST_TREE_V1 write during session)
- New unit tests pass; existing G-003 green suite remains green

## File inventory

| action | path | purpose |
|--------|------|---------|
| create | `code_analysis/core/edit_session/edit_operations_adapter.py` | Bridge G-004 dispatch to session tree + post-mutation |
| modify | `code_analysis/core/edit_session/edit_session.py` | Add `apply_tree_operation(operation: EditOperation)` |
| modify | `code_analysis/core/edit_session/__init__.py` | Export if needed |
| modify | `code_analysis/commands/universal_file_edit/session.py` | Command-layer `apply_tree_operation` |
| modify | `code_analysis/commands/universal_file_edit/tree_temp_edit_batch.py` | short_id EditOperation routing |
| modify | `code_analysis/commands/universal_file_edit/text_draft_apply.py` | short_id routing |
| modify | `code_analysis/commands/universal_file_edit/sidecar_cst_apply.py` | Session-aware op dispatch |
| modify | `code_analysis/commands/universal_file_edit/move_nodes_command.py` | MOVE op |
| modify | `code_analysis/commands/universal_file_edit/open_command.py` | Unified tree on open |
| modify | `code_analysis/commands/universal_file_edit/format_group.py` | Six op availability |
| create | `tests/unit/test_edit_session_tree_operations.py` | short_id + dispatch proof |

## Forbidden approaches

- Do not duplicate handler op logic inside EditSession
- Do not keep parallel whole-source replacement for valid-mode structural edits
- Do not use UUID/json_pointer/line-range as primary valid-mode edit addressing

## Escalation

Escalate to global orchestrator only if handler gaps prevent six-op coverage for a format group (would need HRS fork).
