<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step A1: Gate mutable batch path for fine-grained REPLACE/DELETE targets

## Executor role

`coder_auto`

## Execution directive

Implement the tactical decision to skip the mutable CST batch path when any operation in the batch is a `REPLACE` or `DELETE` whose target node metadata type belongs to `FINE_GRAINED_REPLACE_NODE_TYPES`, by extending `code_analysis/core/cst_tree/tree_modifier.py` only.

## Parent links (mandatory)

- Parent global step: [`docs/tech_spec/steps/improve_precise_micro_edit_semantics.md`](../../../../../steps/improve_precise_micro_edit_semantics.md)
- Parent tactical task: [`docs/tech_spec/branches/improve_precise_micro_edit_semantics/tasks/tactical_mutable_batch_fine_grained_fallback.md`](../../tactical_mutable_batch_fine_grained_fallback.md)

## Technical specification reference

- [`docs/tech_spec/tech_spec.md`](../../../../../tech_spec.md) — project-wide constraints; this change aligns with goal (8): improving server precise micro-edit semantics.

## Step scope

- **Target file (single):** `code_analysis/core/cst_tree/tree_modifier.py`
- **Action:** modify

## Dependency contract

- **Upstream:** None within this tactical task.
- **Downstream:** Atomic step A2 (`test_batched_two_param_replaces_equivalence.md`) depends on this step’s merged behavior.

## Required context

- Batched `modify_tree` currently calls `_use_mutable_batch_path(operations)` with no tree context; metadata lookup requires the loaded `CSTTree`.
- `FINE_GRAINED_REPLACE_NODE_TYPES` is defined in `tree_modifier_ops_parse.py` as `frozenset({"Param", "Name"})` and must be imported, not copied.

## Read first (full paths)

1. `code_analysis/core/cst_tree/tree_modifier.py` — entire file, especially `modify_tree`, `_use_mutable_batch_path`, and imports.
2. `code_analysis/core/cst_tree/tree_modifier_ops_parse.py` — confirm `FINE_GRAINED_REPLACE_NODE_TYPES` name and definition.
3. `code_analysis/core/cst_tree/models.py` — `TreeOperation`, `TreeOperationType`, `TreeNodeMetadata`, `CSTTree` fields (`metadata_map`).

## Expected file change

- Add import of `FINE_GRAINED_REPLACE_NODE_TYPES` from `tree_modifier_ops_parse` using the same relative import style as other imports from that package subtree in this file (prefer `from .tree_modifier_ops_parse import FINE_GRAINED_REPLACE_NODE_TYPES` unless an existing re-export pattern in this module forbids it).
- Extend `_use_mutable_batch_path` so it can read `tree.metadata_map` for target node types.
- Update the sole call site inside `modify_tree` to pass the loaded `tree` into `_use_mutable_batch_path`.
- Preserve the existing module docstring and author lines at the top of the file.

## Forbidden alternatives

- Do not duplicate the `{"Param", "Name"}` frozenset literal in `tree_modifier.py`.
- Do not change `TreeOperation` schema, MCP command handlers, or `tree_modifier_validate.py` in this step.
- Do not modify `tests/` in this step.
- Do not refactor unrelated logic in `tree_modifier.py` (only signature extension, import, and the new gate block plus call-site argument).
- Do not introduce circular imports; if `tree_modifier_ops_parse` cannot be imported from `tree_modifier.py`, stop and escalate (blackstop).

## Atomic operations

1. Add the `FINE_GRAINED_REPLACE_NODE_TYPES` import as specified above.
2. Change `_use_mutable_batch_path` to accept **`operations: List[TreeOperation]`** and **`tree: CSTTree`** (add `CSTTree` to the existing `models` import list if not already present).
3. Keep the existing docstring of `_use_mutable_batch_path` accurate: it should still state when the batch path is used, and reflect that fine-grained `REPLACE`/`DELETE` targets exclude the batch path.
4. Preserve the existing early return `False` when mutable CST helpers are unavailable (`build_from_libcst`, `serialize_to_source`, `apply_operations` import failure branch).
5. Preserve the existing `replace_count`, `insert_count`, `has_delete`, and `has_range_or_move` computations exactly as today (same predicates on `TreeOperationType`).
6. Preserve the existing rule: if `has_range_or_move` is true, return `False` (do not use mutable batch).
7. **New gate (placement):** immediately after the `has_range_or_move` check returns `False` continuation (i.e. after that block completes without returning), and **before** the final `return replace_count > 1 or insert_count > 1 or has_delete`:
   - Iterate `op` over `operations` in list order.
   - If `op.action` is `TreeOperationType.REPLACE` or `TreeOperationType.DELETE`:
     - Let `nid` be `op.node_id` (string).
     - If `nid` is falsy (empty string), skip this operation for the fine-grained gate (do not raise).
     - Otherwise call `tree.metadata_map.get(nid)` → `meta`.
     - If `meta` is not `None` and `getattr(meta, "type", "")` is truthy and **that string is in** `FINE_GRAINED_REPLACE_NODE_TYPES`, **return `False`** immediately (force LibCST sequential path).
     - If `meta` is `None` or `meta.type` missing or empty, **do not** return based on fine-grained rule; continue scanning remaining operations.
8. If the loop completes without triggering the fine-grained return, keep the **unchanged** final boolean expression: `return replace_count > 1 or insert_count > 1 or has_delete`.
9. In `modify_tree`, after `tree = get_tree(tree_id)` is known and before the `try:` that branches on batch vs sequential, change the condition to pass `tree`: invoke `_use_mutable_batch_path(operations, tree)` (argument order exactly: operations first, tree second).

## Expected deliverables

- Updated `tree_modifier.py` matching the algorithm above.
- No other files touched.

## Mandatory validation

- All tests in the repository that the project normally runs for CST changes must pass before handoff; at minimum run the commands below from the repository root with `.venv` activated per project rules.

## Decision rules

- **Single prescribed approach:** extend `_use_mutable_batch_path` with a `tree: CSTTree` parameter and gate on `tree.metadata_map`; do not introduce a parallel global cache or thread-local.
- **Missing metadata:** never force sequential path solely because `node_id` is absent from `metadata_map`; only `type in FINE_GRAINED_REPLACE_NODE_TYPES` when metadata exists triggers sequential path for that batch.

## Blackstops

- Importing `FINE_GRAINED_REPLACE_NODE_TYPES` causes a circular import or runtime failure → stop; report to orchestrator; do not duplicate the frozenset.
- Any test failure in `tests/test_mutable_cst_layer.py` or `tests/test_tree_modifier.py` after this change → diagnose whether the gate is too broad; do not weaken the tactical rule without escalation.

## Handoff package

- Diff limited to `code_analysis/core/cst_tree/tree_modifier.py`.
- Paste validation command outputs showing success patterns below.

---

## LLAMA-readiness — target file

- **Path:** `code_analysis/core/cst_tree/tree_modifier.py`
- **Action:** modify
- **Module docstring:** keep existing (CST tree modifier; author Vasiliy Zdanovskiy; email vasilyvz@gmail.com).

## Imports (complete list after edit)

Must include every import the file needs after your edit; at minimum preserve all existing imports and add:

- `from .tree_modifier_ops_parse import FINE_GRAINED_REPLACE_NODE_TYPES`

Ensure `CSTTree` appears in the `from .models import (...)` tuple if the new signature references `CSTTree`.

## Function skeleton (changed / touched symbols only)

- **Signature:** `def _use_mutable_batch_path(operations: List[TreeOperation], tree: CSTTree) -> bool:`
- **`modify_tree`:** unchanged signature; only the inner call to `_use_mutable_batch_path` gains the second argument `tree`.

## Method / function logic — `_use_mutable_batch_path`

1. If mutable CST helpers are missing, return `False`.
2. Compute `replace_count`, `insert_count`, `has_delete`, `has_range_or_move` exactly as in the current file before your edit.
3. If `has_range_or_move`, return `False`.
4. Run the new loop over `operations` as specified in Atomic operations §7.
5. Return `replace_count > 1 or insert_count > 1 or has_delete`.

## Error handling

- No new exception types. The gate must not raise on missing `node_id` or missing metadata entries.

## Return value specification

- `_use_mutable_batch_path` returns `True` only when the mutable batch path should run (all prior conditions unchanged except the new fine-grained exclusion).

## Edge cases

- Empty `operations` list → fine-grained loop does nothing; final return is `False` (no replaces/inserts/deletes).
- Batch with two statement-level replaces only → fine-grained loop never returns early; if counts satisfy mutable batch, return `True` as today.
- Batch with two `Param` replaces → fine-grained loop returns `False` on first `Param`; sequential path used.
- Batch with one `DELETE` on a `Name` → fine-grained loop returns `False`.
- `REPLACE` with whitespace-only or malformed `node_id` that validation would reject later → still apply gate if `node_id` is non-empty and metadata exists; validation order remains unchanged in `modify_tree` (validation already ran before `_use_mutable_batch_path` is called).

## Constants and literals

- Use only the imported `FINE_GRAINED_REPLACE_NODE_TYPES`; no string literals `"Param"` or `"Name"` for membership tests in this file.

## Exact validation commands (repository root, venv active)

```text
black code_analysis/core/cst_tree/tree_modifier.py
→ stdout contains "reformatted" OR "already well formatted"

flake8 code_analysis/core/cst_tree/tree_modifier.py
→ exit code 0; no output

mypy code_analysis/core/cst_tree/tree_modifier.py
→ stdout contains "Success: no issues found"

pytest tests/test_mutable_cst_layer.py tests/test_tree_modifier.py tests/test_cst_modify_tree_command.py -v
→ all tests PASSED
```

## Test expectations for this step

- No new tests in this step; regression suite above must remain green.

## Forbidden patterns (LLAMA)

- Do not use `Any` for the new parameters.
- Do not add public API exports beyond what already exists.
- Do not call `print()` for logging.
