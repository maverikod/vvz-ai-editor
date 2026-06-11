# Atomic step GC-001: Unit tests for NodeIdMap module (C-025)

## Executor role

`coder_auto`

## Execution directive

Create `tests/unit/test_node_id_map.py` with twelve test functions covering `compute_content_fingerprint`, `NodeIdMap.build`, `NodeIdMap.validate_and_repair`, `NodeIdMap.resolve`, `parse_tree_file`, and `serialize_tree_file` per A-001 algorithms and G-006 green-closure P0 item 1. Do **not** modify production code unless a test reveals a genuine bug in `node_id_map.py` (escalate before changing production).

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-006-node-id-map/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-006-node-id-map/tasks/g-006-green-closure.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`
4. Reference atomic step (module spec): `docs/plans/marked_tree_unification/G-006-node-id-map/T-001-node-id-map-module/atomic_steps/A-001-node-id-map-module.yaml`

## Step scope

- **Target file:** `tests/unit/test_node_id_map.py`
- **action:** create

## Dependency contract

- **Depends on:** `code_analysis/core/tree_lifecycle/node_id_map.py` (A-001 implementation) must exist.
- **Blocks:** GC-002 (`marker_cycle_restore_validate_and_repair.md`) — optional; GC-002 may run in parallel but full G-006 green gate requires both steps complete.

## Required context

- NodeIdMap (C-025) exposes exactly three public map-mutation operations: `build`, `validate_and_repair`, `resolve`.
- TreeNodeUuid (C-024) is UUID4 stored **only** in MAP section; TREE carries integer short_id markers only.
- `validate_and_repair` preserves UUID4 when `content_fingerprint` is unchanged; drops map entries with no matching discovered node; bumps `next_free` to at least `max(short_id)+1`.
- Short_id allocation: first creation starts `next_free = 1`; after two nodes at short_id 1 and 2, `next_free == 3`.

## Read first (exact paths)

1. `code_analysis/core/tree_lifecycle/node_id_map.py` — full module (types, exceptions, algorithms)
2. `docs/plans/marked_tree_unification/G-006-node-id-map/T-001-node-id-map-module/atomic_steps/A-001-node-id-map-module.yaml` — locked algorithms and wire format
3. `docs/tech_spec/branches/g-006-node-id-map/tasks/g-006-green-closure.md` — P0 test matrix

## Expected file change

- New test module with module-level constants/helpers and twelve test functions (exact names below).

## Forbidden alternatives

- Do NOT embed UUID strings in `tree_marked_text` or TREE section content in any test.
- Do NOT modify `node_id_map.py` unless a test failure proves a genuine bug (stop and escalate first).
- Do NOT modify `marker_cycle.py` or any file other than the target test file.
- Do NOT use `test_data/` fixtures.
- Do NOT skip any of the twelve required test function names.
- Do NOT use bare `except:` or `print()`.

## Atomic operations

1. Create file with module docstring (see File header).
2. Add module-level constants and `_make_discovered_nodes` helper.
3. Implement all twelve test functions in the order listed under **Class/function skeleton**.
4. Run mandatory validation commands.

## File header

```python
"""
Unit tests for NodeIdMap build, validate_and_repair, and resolve (C-025).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Imports

```python
from __future__ import annotations

import re
import uuid

import pytest

from code_analysis.core.tree_lifecycle.node_id_map import (
    DiscoveredNode,
    MapEntry,
    MapSection,
    NodeIdMap,
    NodeIdMapError,
    UnknownShortIdError,
    UnknownTreeNodeUuidError,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
```

## Class/function skeleton

**Constants (module level):**

```python
SOURCE_SHA256 = "a" * 64
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
UUID4_IN_TREE_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
```

**Helper:** `def _make_discovered_nodes() -> tuple[list[DiscoveredNode], str]:`

**Test functions (exact names, all required):**

1. `def test_compute_content_fingerprint_empty() -> None:`
2. `def test_build_first_creation() -> None:`
3. `def test_build_rebuild_preserves_uuid_by_fingerprint() -> None:`
4. `def test_validate_and_repair_preserves_uuid() -> None:`
5. `def test_validate_and_repair_drops_orphan_entries() -> None:`
6. `def test_resolve_bidirectional() -> None:`
7. `def test_resolve_unknown_short_id() -> None:`
8. `def test_resolve_unknown_uuid() -> None:`
9. `def test_resolve_requires_exactly_one_arg() -> None:`
10. `def test_parse_serialize_roundtrip() -> None:`
11. `def test_parse_missing_sections() -> None:`
12. `def test_tree_section_has_no_uuid() -> None:`

## Method logic — helper `_make_discovered_nodes`

1. Set `fp_alpha = compute_content_fingerprint("alpha")`.
2. Set `fp_beta = compute_content_fingerprint("beta")`.
3. Build and return:
   ```python
   (
       [
           DiscoveredNode(
               content_fingerprint=fp_alpha,
               kind="line",
               marker_short_id=1,
           ),
           DiscoveredNode(
               content_fingerprint=fp_beta,
               kind="line",
               marker_short_id=2,
           ),
       ],
       "[1] alpha\n[2] beta",
   )
   ```

## Method logic — test 1 `test_compute_content_fingerprint_empty`

1. Call `result = compute_content_fingerprint("")`.
2. Assert `result == EMPTY_SHA256`.
3. Assert `len(result) == 64`.

## Method logic — test 2 `test_build_first_creation`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. Call `sections, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Assert `sections.map.next_free == 3`.
4. Assert `len(sections.map.entries) == 2`.
5. Assert `sections.map.entries[0].short_id == 1` and `sections.map.entries[1].short_id == 2`.
6. Set `uuid1 = sections.map.entries[0].uuid` and `uuid2 = sections.map.entries[1].uuid`.
7. Assert `uuid1 != uuid2`.
8. For each `u` in `(uuid1, uuid2)`: call `uuid.UUID(u, version=4)` — must not raise.
9. Call `r1 = nm.resolve(short_id=1)`; assert `r1.short_id == 1` and `r1.uuid == uuid1`.
10. Call `r2 = nm.resolve(uuid=uuid1)`; assert `r2.short_id == 1` and `r2.uuid == uuid1`.

## Method logic — test 3 `test_build_rebuild_preserves_uuid_by_fingerprint`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. First build: `sections1, _ = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Record `preserved_uuid = sections1.map.entries[0].uuid` (short_id 1, fingerprint of `"alpha"`).
4. Change second node to new content identity:
   - `fp_gamma = compute_content_fingerprint("gamma")`.
   - `rebuild_nodes = [nodes[0], DiscoveredNode(content_fingerprint=fp_gamma, kind="line", marker_short_id=2)]`.
   - `rebuild_tree = "[1] alpha\n[2] gamma"`.
5. Second build with prior: `sections2, nm2 = NodeIdMap.build(tree_marked_text=rebuild_tree, discovered_nodes=rebuild_nodes, source_sha256=SOURCE_SHA256, prior_map=sections1.map)`.
6. Find entry with `short_id == 1` in `sections2.map.entries`; assert its `uuid == preserved_uuid`.
7. Find entry with `short_id == 2`; assert its `uuid != preserved_uuid` (new fingerprint → new UUID).
8. Assert `sections2.map.next_free == 3`.

## Method logic — test 4 `test_validate_and_repair_preserves_uuid`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `sections, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Record `original_uuid = nm.resolve(short_id=1).uuid`.
4. Call `repaired = nm.validate_and_repair(tree_marked_text=tree_text, discovered_nodes=nodes, checksums=sections.checksums)`.
5. Find entry with `short_id == 1` in `repaired.map.entries`.
6. Assert entry `uuid == original_uuid`.
7. Assert `repaired.map.next_free == 3`.
8. Assert `repaired.checksums == sections.checksums`.
9. Assert `repaired.tree == tree_text`.

## Method logic — test 5 `test_validate_and_repair_drops_orphan_entries`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `sections, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Build orphan entry not present in discovered nodes:
   - `orphan_fp = compute_content_fingerprint("orphan")`.
   - `orphan_uuid = str(uuid.uuid4())`.
   - `orphan = MapEntry(short_id=99, uuid=orphan_uuid, content_fingerprint=orphan_fp, kind="line")`.
4. Construct corrupted map: `corrupted = MapSection(next_free=2, entries=list(sections.map.entries) + [orphan])`.
5. Create `nm_corrupt = NodeIdMap(corrupted)`.
6. Call `repaired = nm_corrupt.validate_and_repair(tree_marked_text=tree_text, discovered_nodes=nodes, checksums=sections.checksums)`.
7. Assert `len(repaired.map.entries) == 2`.
8. Assert no entry has `short_id == 99`.
9. Assert `repaired.map.next_free == 3` (bumped from 2 to `max(short_id)+1`).
10. Assert set of short_ids in repaired entries equals `{1, 2}`.

## Method logic — test 6 `test_resolve_bidirectional`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `_, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. For `sid` in `(1, 2)`:
   - `by_short = nm.resolve(short_id=sid)`.
   - `by_uuid = nm.resolve(uuid=by_short.uuid)`.
   - Assert `by_uuid.short_id == sid`.
   - Assert `by_uuid.uuid == by_short.uuid`.

## Method logic — test 7 `test_resolve_unknown_short_id`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `_, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Use `with pytest.raises(UnknownShortIdError) as exc_info:` call `nm.resolve(short_id=999)`.
4. Assert `exc_info.value.short_id == 999`.

## Method logic — test 8 `test_resolve_unknown_uuid`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `_, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Set `unknown = str(uuid.uuid4())` (guaranteed not in map).
4. Use `with pytest.raises(UnknownTreeNodeUuidError) as exc_info:` call `nm.resolve(uuid=unknown)`.
5. Assert `exc_info.value.node_uuid == unknown`.

## Method logic — test 9 `test_resolve_requires_exactly_one_arg`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `_, nm = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. Use `with pytest.raises(NodeIdMapError, match="provide exactly one"):` call `nm.resolve()`.
4. Use `with pytest.raises(NodeIdMapError, match="provide exactly one"):` call `nm.resolve(short_id=1, uuid=str(uuid.uuid4()))`.

## Method logic — test 10 `test_parse_serialize_roundtrip`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `sections, _ = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. `text = serialize_tree_file(sections)`.
4. `roundtrip = parse_tree_file(text)`.
5. Assert `roundtrip.checksums == sections.checksums`.
6. Assert `roundtrip.map.next_free == sections.map.next_free`.
7. Assert `len(roundtrip.map.entries) == len(sections.map.entries)`.
8. For each original entry, find matching `short_id` in roundtrip; assert same `uuid`, `content_fingerprint`, `kind`.
9. Assert `roundtrip.tree == sections.tree`.

## Method logic — test 11 `test_parse_missing_sections`

1. Use `with pytest.raises(NodeIdMapError, match="missing CHECKSUMS section"):` call `parse_tree_file("no markers here")`.
2. Build text with CHECKSUMS and MAP but no TREE:
   ```python
   bad = (
       "---CHECKSUMS---\n"
       "source_sha256: " + SOURCE_SHA256 + "\n"
       "---MAP---\n"
       "next_free: 1\n"
       "entries: []\n"
   )
   ```
3. Use `with pytest.raises(NodeIdMapError, match="missing TREE section"):` call `parse_tree_file(bad)`.

## Method logic — test 12 `test_tree_section_has_no_uuid`

1. `(nodes, tree_text) = _make_discovered_nodes()`.
2. `sections, _ = NodeIdMap.build(tree_marked_text=tree_text, discovered_nodes=nodes, source_sha256=SOURCE_SHA256)`.
3. `full_text = serialize_tree_file(sections)`.
4. Split at first `"---TREE---\n"`; take everything after as `tree_body`.
5. Assert `UUID4_IN_TREE_RE.search(tree_body) is None` (no UUID4 pattern in TREE body).
6. Assert `"---MAP---" in full_text` (sanity: MAP section exists and holds UUIDs separately).

## Error handling

- Tests 7–9 and 11 use `pytest.raises`; do not catch exceptions manually elsewhere.
- If `NodeIdMap.build` raises unexpectedly during fixture setup, let pytest fail (do not swallow).

## Edge cases covered

| Test | Edge case |
|------|-----------|
| `test_compute_content_fingerprint_empty` | empty string input |
| `test_build_rebuild_preserves_uuid_by_fingerprint` | new fingerprint at existing short_id gets new UUID; old fingerprint keeps UUID |
| `test_validate_and_repair_drops_orphan_entries` | orphan map entry removed; `next_free` raised when too low |
| `test_parse_missing_sections` | missing CHECKSUMS and missing TREE |
| `test_tree_section_has_no_uuid` | UUID4 only in MAP, never in TREE text |

## Constants and literals

| Name | Value | Usage |
|------|-------|-------|
| `SOURCE_SHA256` | `"a" * 64` | valid checksum for all build/repair calls |
| `EMPTY_SHA256` | `"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"` | SHA-256 of empty UTF-8 |
| `tree_text` (via helper) | `"[1] alpha\n[2] beta"` | marked TREE with two short_ids |
| `orphan short_id` | `99` | orphan entry test |
| `unknown short_id` | `999` | resolve error test |

## Mandatory validation

```bash
source .venv/bin/activate
black tests/unit/test_node_id_map.py
flake8 tests/unit/test_node_id_map.py
mypy tests/unit/test_node_id_map.py
pytest tests/unit/test_node_id_map.py -v
```

**Expected success patterns:**

- black: exit 0 ("reformatted" or "would leave unchanged")
- flake8: no output, exit 0
- mypy: `Success: no issues found`
- pytest: **12 passed**, exit 0

**Completion condition:** all tests pass.

## Decision rules

- Use plain string content (`"alpha"`, `"beta"`, `"gamma"`) for fingerprints; no format handlers needed.
- Use `pytest.raises(..., match=...)` with substring patterns exactly as specified.
- Do not compare full serialized file bytes unless round-trip test; compare structured fields.

## Blackstops

- If `node_id_map.py` is missing, stop — A-001 not implemented.
- If more than one test fails due to production bug, stop after documenting failures; escalate before editing `node_id_map.py`.

## Handoff package

- **File:** `tests/unit/test_node_id_map.py`
- **Command:** `pytest tests/unit/test_node_id_map.py -q`
- **Expected:** 12 passed, 0 failed
