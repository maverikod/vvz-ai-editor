# G-003 Closure: {h008} Six-Operation Contract Coherence

## Verdict

**COHERENT_DUPLICATION** (primary valid-mode structural path unified; secondary fallbacks documented below).

After Phase 1+2 remediation, valid-session **structural** edits on the unified path route through:

```
command layer → apply_tree_operation → EditSession.apply_tree_operation
  → apply_edit_on_session_tree (edit_operations_adapter.py)
  → apply_edit_operation (G-004, code_analysis/tree/edit_operations.py)
  → FormatHandler.op_* on marked TREE text
  → _post_mutation_full ({d003}: unmark export, CHECKSUMS, SessionRepo.commit_full)
```

G-004 does not modify EditSession internals. EditSession owns lifecycle and {d003} post-mutation; G-004 owns operation semantics on marked tree text.

## Six-operation mapping ({h001}–{h007})

| HRS op | `EditOperationKind` | G-004 handler | G-003 command entry (VALID + unified gate) |
|--------|---------------------|---------------|---------------------------------------------|
| {h002} insert | `INSERT` | `handler.op_insert` | `sidecar_cst_apply` → `apply_command_ops_on_session_tree`; `tree_temp_edit_batch._apply_valid_tree_temp_mutations`; `text_draft_apply._run_valid_text_tree_apply` |
| {h003} delete | `DELETE` | `handler.op_delete` | Same gates |
| {h004} replace | `REPLACE` | `handler.op_replace` | Same gates |
| {h005} move | `MOVE` | `handler.op_move` | `move_nodes_command._run_valid_session_move_batch`; sidecar/text via `command_op_to_edit_operation` |
| {h006} edit_attributes | `EDIT_ATTRIBUTES` | `handler.op_edit_attributes` | Sidecar/text unified gates (tree-temp valid mapper: not yet wired) |
| {h007} edit-content | `EDIT_CONTENT` | `handler.op_edit_content` | Sidecar/text unified gates (tree-temp valid mapper: not yet wired) |

Op construction: `command_op_to_edit_operation` / `_tree_temp_op_to_edit_operation` in `edit_operations_adapter.py`.

## Why this satisfies {h008} on the primary path

1. **short_id addressing:** `apply_edit_operation` validates integer `short_id` via `validate_short_id` ({n003}). Command layer resolves MAP UUID / json_pointer to short_id before dispatch where legacy tests require it.
2. **Fresh short_id on insert ({a007}):** `apply_edit_operation` passes `next_free`, returns incremented value; MAP synced via `_sync_map_after_tree_mutation`.
3. **Preserved short_id on replace/move:** Handler contracts in G-004; no reallocation on replace/move ops.
4. **Leaf-only edit-content ({h007}):** Enforced in handler `op_edit_content`.
5. **{d003} per-mutation:** Each `apply_edit_on_session_tree` call ends in `_post_mutation_full` (one SessionRepo commit per op).

## Documented secondary paths (not six-op dispatch)

These remain for backward compatibility or non-structural edits; targeted for retirement or gating:

| Path | When | Why kept |
|------|------|----------|
| `apply_valid_tree_mutation` whole-source | Open sync, legacy callers | Whole-file replace, not a single structural op |
| Legacy CST `run_sidecar_cst_edit_batch` | UUID span refs not in MAP | Pre-unified Python sidecar; gate `sidecar_ops_use_unified_tree` |
| Text line-range buffer | No `node_ref` | Plain-text splice, not tree op |
| Tree-temp legacy in-memory | `tree_temp_roots is None` | Pre-session JSON/YAML temp model |
| INVALID plaintext | `tree_validity == INVALID` | {h008} explicitly defers to degraded source-only path |

## Denude/restore vs direct marked-tree ops

`marker_cycle.denude_marked_tree` / `restore_marked_tree` remain used by `apply_valid_tree_mutation` (whole-source path). The unified adapter applies `handler.op_*` directly on marked TREE section text and repairs MAP — equivalent marker semantics, different implementation. Both preserve MAP UUID4 and `next_free`; unified path is authoritative for six-op dispatch per tactical decision.

## Escalation

No HRS change required. Remaining work: close legacy-addressing test regressions (json_pointer/YAML/markdown slug resolution) and G-004 preview routing (5 tests — not G-003 scope).

## Parent links

- `docs/plans/marked_tree_unification/source_spec.md` — {h008}, {h001}–{h007}
- `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-h008-six-operation-unification.md`
