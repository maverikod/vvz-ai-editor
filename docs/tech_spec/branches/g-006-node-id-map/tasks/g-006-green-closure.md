# G-006 Green Closure — Corrective Tactical Task

## Purpose

Close G-006 (Node Identity and Map / NodeIdMap) to GREEN: confirm `node_id_map.py` matches T-001/A-001, add dedicated unit tests for the three public map operations, and fix the `marker_cycle.restore_marked_tree` MAP bypass so G-006 repair semantics apply on session restore.

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- HRS: `docs/plans/marked_tree_unification/source_spec.md` (Block 12 — `{n001}`, `{n002}`, `{n003}`, `{a007}`)
- MRS: `docs/plans/marked_tree_unification/spec.yaml` (C-024 TreeNodeUuid, C-025 NodeIdMap)
- Global step: `docs/plans/marked_tree_unification/G-006-node-id-map/README.yaml`
- Tactical step: `docs/plans/marked_tree_unification/G-006-node-id-map/T-001-node-id-map-module/README.yaml`
- Atomic step: `docs/plans/marked_tree_unification/G-006-node-id-map/T-001-node-id-map-module/atomic_steps/A-001-node-id-map-module.yaml`

## Scope

**Included:**

- Create `tests/unit/test_node_id_map.py` with direct coverage of `NodeIdMap.build`, `validate_and_repair`, `resolve`, helpers, and error paths per A-001 algorithms
- Fix `code_analysis/core/edit_session/marker_cycle.py` `restore_marked_tree`: after `NodeIdMap.build`, run `validate_and_repair` on the built map instead of overwriting MAP with pre-hide snapshot; catch `NodeIdMapError` explicitly
- Re-run G-006-relevant pytest bundle until green

**Excluded (defer — not blocking G-006 module GREEN):**

- `HandlerRegistry` injecting `NodeIdMap` into format handlers for `resolve_uuid_for_short_id` — internal wiring follow-on
- `edit_operations.py` post-edit MAP refresh via `validate_and_repair` — G-004 consumer integration
- Six failing `test_tree_temp_universal_*_preview_sessions.py` tests — preview routing (G-004), unless fix is trivially in G-006 scope
- HRS/MRS/spec.yaml edits
- `test_data/` code

## Boundaries

- Do NOT modify `source_spec.md` or `spec.yaml`
- Do NOT touch `test_data/`
- Do NOT add public API beyond A-001 `__all__` on `node_id_map.py` unless a bug fix requires minimal change
- Do NOT refactor unrelated modules

## Dependencies

- none

## Parallelization note

Two independent tracks may run in parallel after tactical brief:

1. `tests/unit/test_node_id_map.py` creation
2. `marker_cycle.py` restore fix

## Expected outcome

- `pytest tests/unit/test_node_id_map.py -q` — all pass
- `pytest tests/unit/test_marker_cycle.py -q` — all pass (UUID/`next_free` preservation on denude/restore)
- `pytest tests/unit/test_marker_cycle.py tests/tree_pipeline_parity/test_unified_vs_legacy.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py tests/test_tree_temp_edit_session_lifecycle.py tests/unit/test_edit_session_lifecycle.py -q` — all pass (xfail allowed where marked)
- A-001 import smoke test (`python -c` block) — exit 0
- `black --check`, `flake8` on `node_id_map.py` — exit 0
- Researcher re-audit confirms P0 gaps closed for G-006 module + restore path

## Correction items (from verification 2026-05-31)

### P0 — Test coverage (required for GREEN)

1. **Create `tests/unit/test_node_id_map.py`** covering:
   - `compute_content_fingerprint` empty and non-empty
   - `NodeIdMap.build` first creation: two nodes → `next_free == 3`, distinct UUID4s, bidirectional `resolve`
   - `NodeIdMap.build` rebuild with `prior_map`: same fingerprint → same UUID preserved; new fingerprint → new UUID
   - `NodeIdMap.validate_and_repair`: fingerprint unchanged → UUID preserved even if entry uuid temporarily wrong; orphan map entries dropped; `next_free` bumped to `max(short_id)+1`
   - `NodeIdMap.resolve`: `UnknownShortIdError`, `UnknownTreeNodeUuidError`, `NodeIdMapError` when both/neither args provided
   - `parse_tree_file` / `serialize_tree_file` round-trip; missing section errors; duplicate key errors
   - Assert serialized TREE section contains no UUID4 pattern (regex on tree body only)

### P0 — G-006 coherence on marker restore

2. **`code_analysis/core/edit_session/marker_cycle.py` `restore_marked_tree`**:
   - After `NodeIdMap.build(...)`, construct `NodeIdMap` from built map, call `validate_and_repair(tree_marked_text=..., discovered_nodes=..., checksums=...)` and use returned `TreeSections` (do NOT assign `built_sections.map = state.map_section`)
   - Replace bare `except ValueError` with `except NodeIdMapError`
   - Existing tests in `tests/unit/test_marker_cycle.py` must still pass (UUID stability on denude/restore when structure unchanged)

## Questions/escalation rule

Escalate to global orchestrator if:

- `test_denude_restore_preserves_map_uuids` fails after validate_and_repair fix and requires HRS change to C-012 marker-freeze semantics
- HandlerRegistry wiring or edit-path MAP refresh is mandatory for G-006 frozen status (vs G-004 follow-on)

## File inventory

| action | path | purpose |
|--------|------|---------|
| create | `tests/unit/test_node_id_map.py` | Direct unit tests for NodeIdMap module |
| modify | `code_analysis/core/edit_session/marker_cycle.py` | Use validate_and_repair on restore; explicit NodeIdMapError catch |

## Test plan

| test file | test names (minimum) | asserts |
|-----------|---------------------|---------|
| `tests/unit/test_node_id_map.py` | `test_compute_content_fingerprint_empty`, `test_build_first_creation`, `test_build_rebuild_preserves_uuid_by_fingerprint`, `test_validate_and_repair_preserves_uuid`, `test_validate_and_repair_drops_orphan_entries`, `test_resolve_bidirectional`, `test_resolve_unknown_short_id`, `test_resolve_unknown_uuid`, `test_resolve_requires_exactly_one_arg`, `test_parse_serialize_roundtrip`, `test_parse_missing_sections`, `test_tree_section_has_no_uuid` | Per A-001 algorithms and GREEN criteria 1–4 |
| `tests/unit/test_marker_cycle.py` | existing suite | No regression after marker_cycle fix |

## Forbidden approaches

- Do NOT overwrite MAP with pre-hide snapshot in restore path
- Do NOT add UUID strings to TREE text in tests or production
- Do NOT skip `validate_and_repair` on restore when `discovered_nodes` is non-empty
- Do NOT modify `node_id_map.py` unless a test reveals a genuine bug
