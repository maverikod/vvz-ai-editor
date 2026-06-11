# Atomic step index — G-006 green closure

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-006-node-id-map/README.yaml`
- Tactical task: `docs/tech_spec/branches/g-006-node-id-map/tasks/g-006-green-closure.md`
- Technical specification: `docs/tech_spec/tech_spec.md`

## Goal

Close G-006 (NodeIdMap / C-025) to GREEN: add dedicated unit tests for the three public map operations and fix `restore_marked_tree` to use `validate_and_repair` instead of overwriting MAP with the pre-hide snapshot.

## Atomic steps

| Step ID | File | Target | Priority | Depends on |
|---------|------|--------|----------|------------|
| GC-001 | `test_node_id_map.md` | `tests/unit/test_node_id_map.py` | 1 | A-001 (`node_id_map.py`) |
| GC-002 | `marker_cycle_restore_validate_and_repair.md` | `code_analysis/core/edit_session/marker_cycle.py` | 2 | A-001; GC-001 optional |

## Execution order

1. **Wave 1 (parallel-safe):** GC-001 and GC-002 may run concurrently after A-001 is implemented.
2. **Green gate:** both steps complete; run full pytest bundle from `g-006-green-closure.md`.

See `parallel_waves.md` for details.
