# Atomic step GC-002: Fix `restore_marked_tree` to use `validate_and_repair`

## Executor role

`coder_auto`

## Execution directive

Modify `code_analysis/core/edit_session/marker_cycle.py` function `restore_marked_tree` so that after `NodeIdMap.build`, the code constructs the returned `NodeIdMap` instance, calls `validate_and_repair`, and serializes the **repaired** `TreeSections` — without overwriting MAP with the pre-hide snapshot. Replace bare `except ValueError` with `except NodeIdMapError`. Do **not** modify any file other than `marker_cycle.py`.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-006-node-id-map/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-006-node-id-map/tasks/g-006-green-closure.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`
4. Reference atomic step (module spec): `docs/plans/marked_tree_unification/G-006-node-id-map/T-001-node-id-map-module/atomic_steps/A-001-node-id-map-module.yaml`

## Step scope

- **Target file:** `code_analysis/core/edit_session/marker_cycle.py`
- **action:** modify

## Dependency contract

- **Depends on:** `code_analysis/core/tree_lifecycle/node_id_map.py` (A-001) must exist. GC-001 (`test_node_id_map.md`) is **optional** for this step (may run in parallel); full G-006 green gate requires both GC-001 and GC-002 complete.
- **Blocks:** G-006 green closure verification bundle.

## Required context

- Current bug (lines 83–94): after `NodeIdMap.build`, code assigns `built_sections.map = state.map_section`, bypassing G-006 repair semantics and discarding build output.
- Required fix: call `validate_and_repair` on the `NodeIdMap` returned from `build`; use its returned `TreeSections` directly.
- `NodeIdMapError` is the base exception for NodeIdMap validation failures (subclass of `ValueError`).
- Empty `discovered_nodes` branch (lines 76–82) is **unchanged** — only the non-empty path is modified.
- Existing tests `test_denude_restore_preserves_map_uuids` and `test_restore_uses_prior_map_next_free` in `tests/unit/test_marker_cycle.py` must still pass (UUID/`next_free` preservation on identity round-trip).

## Read first (exact paths)

1. `code_analysis/core/edit_session/marker_cycle.py` — current `restore_marked_tree` implementation
2. `code_analysis/core/tree_lifecycle/node_id_map.py` — `NodeIdMap.build`, `NodeIdMap.validate_and_repair`, `NodeIdMapError`
3. `tests/unit/test_marker_cycle.py` — regression tests that must pass
4. `docs/tech_spec/branches/g-006-node-id-map/tasks/g-006-green-closure.md` — P0 item 2

## Expected file change

- Update imports to include `NodeIdMapError`.
- Rewrite non-empty `discovered_nodes` branch in `restore_marked_tree` (see Atomic operations).
- Update one-line docstring on `restore_marked_tree` to mention `validate_and_repair` (replace "preserve MAP bytes" wording).

## Forbidden alternatives

- Do NOT assign `built_sections.map = state.map_section` (forbidden MAP bypass).
- Do NOT assign `built_sections.checksums = state.checksums_section` after repair (checksums are passed into `validate_and_repair` and returned in repaired sections).
- Do NOT skip `validate_and_repair` when `discovered_nodes` is non-empty.
- Do NOT catch bare `except ValueError` for NodeIdMap failures — catch `NodeIdMapError` explicitly.
- Do NOT modify `node_id_map.py`, test files, or any file other than `marker_cycle.py`.
- Do NOT change `denude_marked_tree` or `MarkerEditState`.
- Do NOT change the empty-`discovered_nodes` early-return branch.

## Atomic operations

1. Add `NodeIdMapError` to the import tuple from `code_analysis.core.tree_lifecycle.node_id_map`.
2. Update `restore_marked_tree` docstring summary line to: `"""Re-embed short_id markers via handler.mark + NodeIdMap build/validate_and_repair (C-012)."""`.
3. Replace the non-empty `discovered_nodes` try/except block (current lines 83–94) with the algorithm below.
4. Run mandatory validation commands.

## File header

**No change** to module docstring header (author/email block stays). Only update the `restore_marked_tree` function docstring as specified.

## Imports (complete list for target file after edit)

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from code_analysis.core.tree_lifecycle.node_id_map import (
    ChecksumsSection,
    DiscoveredNode,
    MapSection,
    NodeIdMap,
    NodeIdMapError,
    TreeSections,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from code_analysis.tree.handler_registry import HandlerRegistry
```

**Change from current:** add `NodeIdMapError` to the import tuple (alphabetically after `NodeIdMap`).

## Class/function skeleton (modified entities only)

**Unchanged:** `MARKER_CYCLE_ERROR`, `MarkerEditState`, `denude_marked_tree` — do not edit.

**Modified function signature (unchanged):**

```python
def restore_marked_tree(
    *,
    source_abs: Path,
    denuded_after_mutation: str,
    state: MarkerEditState,
) -> str:
    """Re-embed short_id markers via handler.mark + NodeIdMap build/validate_and_repair (C-012)."""
```

## Method logic — `restore_marked_tree` (full function after edit)

Keep lines 62–82 exactly as today (handler resolve, mark, parse_content, discovered_nodes construction, source_sha256, empty discovered_nodes early return).

Replace the current `try` block (non-empty path) with:

1. Enter `try:` block.
2. Call `built_sections, id_map = NodeIdMap.build(tree_marked_text=candidate_marked, discovered_nodes=discovered_nodes, source_sha256=source_sha256, prior_map=state.map_section)`.
   - Note: use name `id_map` (not `_id_map`); the instance is used in step 3.
3. Call `repaired_sections = id_map.validate_and_repair(tree_marked_text=candidate_marked, discovered_nodes=discovered_nodes, checksums=state.checksums_section)`.
4. `return serialize_tree_file(repaired_sections)`.
5. On exception: `except NodeIdMapError as exc:` then `raise ValueError(f"{MARKER_CYCLE_ERROR}: {exc}") from exc`.

**Remove entirely (must not remain in file):**

```python
    built_sections.map = state.map_section
    built_sections.checksums = state.checksums_section
    return serialize_tree_file(built_sections)
```

**Remove:** `except ValueError as exc:` — replace with `except NodeIdMapError as exc:`.

### Pseudocode (non-empty path only)

```
try:
    built_sections, id_map = NodeIdMap.build(
        tree_marked_text=candidate_marked,
        discovered_nodes=discovered_nodes,
        source_sha256=source_sha256,
        prior_map=state.map_section,
    )
    repaired_sections = id_map.validate_and_repair(
        tree_marked_text=candidate_marked,
        discovered_nodes=discovered_nodes,
        checksums=state.checksums_section,
    )
    return serialize_tree_file(repaired_sections)
except NodeIdMapError as exc:
    raise ValueError(f"{MARKER_CYCLE_ERROR}: {exc}") from exc
```

Note: `built_sections` is assigned but only used implicitly via `id_map` state; do not serialize `built_sections` directly.

## Error handling

| Location | Exception | Action |
|----------|-----------|--------|
| `NodeIdMap.build` | `NodeIdMapError` | catch, re-raise as `ValueError(f"{MARKER_CYCLE_ERROR}: {exc}")` |
| `id_map.validate_and_repair` | `NodeIdMapError` | same catch block |
| Other errors (handler.mark, etc.) | propagate | do not catch |

Do NOT use bare `except ValueError` — `NodeIdMapError` is more specific and documents intent.

## Return value specification

- Function still returns `str` — full three-section serialized tree file text from `serialize_tree_file(repaired_sections)`.
- `repaired_sections.map` reflects post-repair MAP (not pre-hide snapshot).
- `repaired_sections.checksums` equals `state.checksums_section` (passed through validate_and_repair).

## Edge cases

| Case | Behavior |
|------|----------|
| `discovered_nodes` empty | unchanged early return using `state.map_section` directly (lines 76–82) |
| Identity denude/restore (no content change) | `validate_and_repair` preserves UUIDs and `next_free` — existing marker_cycle tests must pass |
| `NodeIdMap.build` raises | wrapped in `ValueError` with `MARKER_CYCLE_ERROR` prefix |
| `validate_and_repair` raises | same wrap |

## Constants and literals

| Name | Value | Usage |
|------|-------|-------|
| `MARKER_CYCLE_ERROR` | `"MARKER_CYCLE_ERROR"` | unchanged; prefix in re-raised ValueError |

## Mandatory validation

```bash
source .venv/bin/activate
black code_analysis/core/edit_session/marker_cycle.py
flake8 code_analysis/core/edit_session/marker_cycle.py
mypy code_analysis/core/edit_session/marker_cycle.py
pytest tests/unit/test_marker_cycle.py -v
pytest tests/unit/test_node_id_map.py -q
```

**Expected success patterns:**

- black: exit 0
- flake8: no output, exit 0
- mypy: `Success: no issues found`
- `test_marker_cycle.py`: **2 passed** (`test_denude_restore_preserves_map_uuids`, `test_restore_uses_prior_map_next_free`)
- `test_node_id_map.py`: all passed (requires GC-001 complete; if GC-001 not done yet, run marker_cycle tests only and note GC-001 pending)

**Full G-006 bundle (run after GC-001 + GC-002):**

```bash
pytest tests/unit/test_marker_cycle.py tests/tree_pipeline_parity/test_unified_vs_legacy.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py tests/test_tree_temp_edit_session_lifecycle.py tests/unit/test_edit_session_lifecycle.py -q
```

Expected: all pass (xfail allowed where marked).

**Completion condition:** all tests pass.

## Decision rules

- Keep `prior_map=state.map_section` in `build` call — repair runs on top of built map seeded from pre-hide prior.
- Do not add logging.
- Do not refactor unrelated code in the file.

## Blackstops

- If `test_denude_restore_preserves_map_uuids` fails after the fix and the failure requires changing C-012 marker-freeze semantics, stop and escalate to global orchestrator (per tactical task escalation rule).
- If `NodeIdMapError` is not importable from `node_id_map.py`, stop — A-001 incomplete.

## Handoff package

- **File:** `code_analysis/core/edit_session/marker_cycle.py`
- **Primary regression command:** `pytest tests/unit/test_marker_cycle.py -v`
- **Expected:** 2 PASSED, UUID sets and `next_free` unchanged on identity round-trip
