# Parallel waves — G-006 green closure atomic steps

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-006-node-id-map/README.yaml`
- Tactical task: `docs/tech_spec/branches/g-006-node-id-map/tasks/g-006-green-closure.md`
- Technical specification: `docs/tech_spec/tech_spec.md`

## Prerequisite

A-001 complete: `code_analysis/core/tree_lifecycle/node_id_map.py` exists and import smoke test passes.

## Wave 1 — tests and restore fix (parallel)

GC-001 and GC-002 have **no hard dependency** on each other. Run concurrently when safe (one coder per file).

| Step | Target |
|------|--------|
| GC-001 `test_node_id_map.md` | `tests/unit/test_node_id_map.py` (create) |
| GC-002 `marker_cycle_restore_validate_and_repair.md` | `code_analysis/core/edit_session/marker_cycle.py` (modify restore path) |

## Final gate

After both steps:

```bash
source .venv/bin/activate
pytest tests/unit/test_node_id_map.py -q
pytest tests/unit/test_marker_cycle.py -q
black --check code_analysis/core/tree_lifecycle/node_id_map.py code_analysis/core/edit_session/marker_cycle.py
flake8 code_analysis/core/tree_lifecycle/node_id_map.py code_analysis/core/edit_session/marker_cycle.py
pytest tests/unit/test_marker_cycle.py tests/tree_pipeline_parity/test_unified_vs_legacy.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py tests/test_tree_temp_edit_session_lifecycle.py tests/unit/test_edit_session_lifecycle.py -q
```

All tests must pass (xfail allowed where marked).
