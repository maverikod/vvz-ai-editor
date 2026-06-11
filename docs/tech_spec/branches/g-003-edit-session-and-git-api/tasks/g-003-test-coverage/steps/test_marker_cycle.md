# Atomic step AS-002: Unit tests for marker hide/restore cycle (C-012)

## Executor role

`coder_auto`

## Execution directive

Create `tests/unit/test_marker_cycle.py` with two test functions for `denude_marked_tree` and `restore_marked_tree`. Do not modify production code.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/unit/test_marker_cycle.py`
- **action:** create

## Dependency contract

- **Depends on:** `g-003-core-bugfixes.md` complete.
- **Blocks:** AS-003 (related lifecycle tests; can run in parallel).

## Required context

- `denude_marked_tree` and `restore_marked_tree` in `code_analysis/core/edit_session/marker_cycle.py`.
- Build marked tree fixtures via `TreeBuilder.build` (three-section `.tree` sibling layout).
- MAP UUIDs must be preserved byte-for-byte through denude/restore when content unchanged.

## Read first (exact paths)

1. `code_analysis/core/edit_session/marker_cycle.py`
2. `code_analysis/core/tree_lifecycle/builder.py` — `TreeBuilder.build`
3. `code_analysis/core/tree_lifecycle/checksum.py` — `compute_content_checksum`
4. `code_analysis/core/tree_lifecycle/node_id_map.py` — `parse_tree_file`, `serialize_tree_file`
5. `tests/tree_pipeline_parity/test_unified_vs_legacy.py` — fixture pattern for JSON sample

## Expected file change

- New test module with helpers and two test functions.

## Forbidden alternatives

- Do not use legacy `.trees/` paths.
- Do not edit `test_data/`.
- Do not modify `marker_cycle.py`.
- Do not compare MAP by object identity only; compare serialized MAP section bytes or entry UUID sets plus `next_free`.

## Atomic operations

1. Create file with docstring.
2. Add `_build_json_marked_tree(tmp_path: Path) -> tuple[Path, Path, str]` helper returning `(source_abs, sidecar_path, marked_text)`.
3. Implement `test_denude_restore_preserves_map_uuids`.
4. Implement `test_restore_uses_prior_map_next_free`.

## File header

```
"""
Unit tests for EditSession marker denude/restore cycle (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Imports

- `from __future__ import annotations`
- `from pathlib import Path`
- `import pytest`
- `from code_analysis.core.edit_session.marker_cycle import denude_marked_tree, restore_marked_tree`
- `from code_analysis.core.tree_lifecycle.builder import TreeBuilder`
- `from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum`
- `from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file, serialize_tree_file`

## Class/function skeleton

**Helper:** `def _build_json_marked_tree(tmp_path: Path) -> tuple[Path, Path, str]:`  
Build `sample.json` with content `'{"alpha": 1, "beta": 2}\n'`, run `TreeBuilder.build`, return source path, sibling sidecar path, and full marked tree file text.

**Test 1:** `def test_denude_restore_preserves_map_uuids(tmp_path: Path) -> None:`

**Test 2:** `def test_restore_uses_prior_map_next_free(tmp_path: Path) -> None:`

## Method logic — helper `_build_json_marked_tree`

1. `name = "sample.json"`.
2. `source_abs = tmp_path / name`.
3. `content = '{"alpha": 1, "beta": 2}\n'`.
4. `source_abs.write_text(content, encoding="utf-8")`.
5. `checksum = compute_content_checksum(content)`.
6. `ref = TreeBuilder.build(content=content, source_abs=source_abs, file_path=name, content_checksum=checksum)`.
7. `marked_text = ref.sidecar_path.read_text(encoding="utf-8")`.
8. Return `(source_abs, ref.sidecar_path, marked_text)`.

## Method logic — test 1 `test_denude_restore_preserves_map_uuids`

1. `(source_abs, _sidecar, marked) = _build_json_marked_tree(tmp_path)`.
2. `before = parse_tree_file(marked)`.
3. `before_uuids = sorted(e.uuid for e in before.map.entries)`.
4. `before_next_free = before.map.next_free`.
5. `denuded, state = denude_marked_tree(source_abs=source_abs, marked_tree=marked)`.
6. Assert `state.map_section == before.map` (dataclass equality) OR assert `serialize_tree_file` MAP sections match.
7. `restored = restore_marked_tree(source_abs=source_abs, denuded_after_mutation=denuded, state=state)`.
8. `after = parse_tree_file(restored)`.
9. `after_uuids = sorted(e.uuid for e in after.map.entries)`.
10. Assert `before_uuids == after_uuids`.
11. Assert `after.map.next_free == before_next_free`.
12. Assert `after.checksums == before.checksums`.

## Method logic — test 2 `test_restore_uses_prior_map_next_free`

1. Build marked tree as above; parse to `sections`.
2. Record `prior_next_free = sections.map.next_free` (must be `>= 3` for two-key JSON object; if not, still assert equality after restore).
3. Denude and restore with **unchanged** denuded text (identity round-trip).
4. Parse restored text to `restored_sections`.
5. Assert `restored_sections.map.next_free == prior_next_free`.
6. For every `MapEntry` in `sections.map.entries`, find matching `short_id` in `restored_sections.map.entries` and assert same `uuid` string.

## Error handling

- Do not catch `ValueError` from restore; identity round-trip must succeed.

## Edge cases

- Multiple MAP entries: preserve all UUID4 values, not only root.
- Empty denuded mutation (no-op) still runs restore path.

## Constants and literals

- Sample JSON content: `'{"alpha": 1, "beta": 2}\n'`
- File name: `"sample.json"`

## Mandatory validation

```bash
source .venv/bin/activate
black tests/unit/test_marker_cycle.py
flake8 tests/unit/test_marker_cycle.py
mypy tests/unit/test_marker_cycle.py
pytest tests/unit/test_marker_cycle.py -v
```

Expected: 2 passed.

**Completion condition:** all tests pass.

## Decision rules

- Use JSON handler sample (simplest three-section tree).
- Preserve MAP via `MarkerEditState.map_section` as production code does.

## Blackstops

- If `TreeBuilder.build` fails for sample JSON, stop and report core bugfix incomplete.

## Handoff package

- File: `tests/unit/test_marker_cycle.py`
- Command: `pytest tests/unit/test_marker_cycle.py -v`
- Expected: 2 PASSED
