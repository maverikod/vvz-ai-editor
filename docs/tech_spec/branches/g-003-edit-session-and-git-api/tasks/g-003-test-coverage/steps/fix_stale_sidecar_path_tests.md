# Atomic step AS-004: Fix stale sidecar path tests (co-located `.tree` layout)

## Executor role

`coder_auto`

## Execution directive

Update four existing test modules that still reference deleted `code_analysis.core.tree_temp.sidecar_paths` and legacy `tmp_path / ".trees" / ...` paths. Migrate to co-located sibling sidecars via `sibling_tree_path` and three-section marked tree parsing via `parse_tree_file`. Do not modify production code.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

This is one **logical group** step touching exactly these four files (modify each):

| # | Target file |
|---|-------------|
| 1 | `tests/test_tree_temp_universal_json_preview_sessions.py` |
| 2 | `tests/test_tree_temp_universal_yaml_preview_sessions.py` |
| 3 | `tests/test_tree_temp_universal_json_edit_write_close.py` |
| 4 | `tests/test_tree_temp_universal_yaml_edit_write_close.py` |

- **action:** modify (all four)

## Dependency contract

- **Depends on:** none (may run parallel with AS-001–003).
- **Blocks:** final pytest gate in tactical task.

## Required context

- Deleted module: `code_analysis.core.tree_temp.sidecar_paths` — remove all imports.
- Replacement: `from code_analysis.tree.sibling_convention import sibling_tree_path`
- Sidecar path formula: `sibling_tree_path(source_abs.resolve())` → `<dir>/<name>.tree` next to source.
- Sidecar **on-disk format** after universal_file write commit: three-section marked tree (`---CHECKSUMS---`, `---MAP---`, `---TREE---`), **not** legacy JSON `{"source_sha256", "root": [...]}`.
- Preview tests previously used `_find_stable_by_path` on JSON sidecar roots; replace with MAP UUID lookup by JSON/YAML pointer (see shared helper below).
- Reference migration pattern: `tests/test_tree_temp_edit_session_lifecycle.py` (uses `sibling_tree_path` + `parse_tree_file`).

## Read first (exact paths)

1. All four target test files (full read).
2. `code_analysis/tree/sibling_convention.py`
3. `code_analysis/core/tree_lifecycle/node_id_map.py` — `parse_tree_file`
4. `code_analysis/tree/handler_registry.py` — `HandlerRegistry.default_registry()`
5. `tests/test_tree_temp_edit_session_lifecycle.py` — post-migration assertions

## Expected file change

- Remove broken imports; fix collection errors in edit_write_close modules.
- Replace every `tmp_path / ".trees" / f"{rel}.tree"` (and variants) with `_sidecar_path(tmp_path, rel)`.
- Replace JSON sidecar payload reads with `parse_tree_file` + MAP UUID helpers in preview tests.
- Replace `json.loads(sidecar)` checksum assertions in edit_write_close with `parse_tree_file(...).checksums["source_sha256"]`.

## Forbidden alternatives

- Do not reintroduce `resolve_trees_sidecar_path` or `.trees/` directory layout.
- Do not edit `test_data/`.
- Do not skip any of the four files.
- Do not change test function names (keep existing test entry points).
- Do not weaken assertions to always-pass placeholders.

## Shared helpers (add to each preview file; adapt pointer logic for YAML)

Add these functions near existing helpers in **both** preview modules:

**`def _sidecar_path(tmp: Path, rel: str) -> Path:`**  
Return `sibling_tree_path((tmp / rel).resolve())`.

**`def _normalize_pointer(pointer: str) -> str:`**  
If `pointer in ("", "/")`: return `"/"`. Else ensure leading `/` (e.g. `"/svc/env"`).

**`def _uuid_for_pointer(*, source_path: Path, sidecar_path: Path, pointer: str) -> str:`**

Algorithm:

1. `sections = parse_tree_file(sidecar_path.read_text(encoding="utf-8"))`.
2. `handler = HandlerRegistry.default_registry().resolve(source_path)`.
3. `source_text = source_path.read_text(encoding="utf-8")`.
4. `nodes = handler.parse_content(source_path, source_text)`.
5. `want = _normalize_pointer(pointer)`.
6. Loop nodes: if `str(node.attributes.get("json_pointer", "")) == want` OR (`want == "/"` and node.attributes.get("json_pointer") in ("", "/")): capture `target_short_id = int(node.short_id)`; break.
7. If no match: `raise KeyError(want)`.
8. Loop `sections.map.entries`: if `entry.short_id == target_short_id`: return `entry.uuid`.
9. Raise `KeyError` if no MAP entry.

Replace calls like `_find_stable_by_path(payload, "/svc/env")` with `_uuid_for_pointer(source_path=tmp_path / _REL, sidecar_path=_sidecar_path(tmp_path, _REL), pointer="/svc/env")`.

Replace `_find_stable_by_path(payload, "")` with pointer `"/"` (root scalar test).

Remove obsolete `_find_stable_by_path` if unused.

## File 3 & 4 — edit_write_close modules

### Import changes (both JSON and YAML files)

- **Remove:** `from code_analysis.core.tree_temp.sidecar_paths import resolve_trees_sidecar_path`
- **Add:** `from code_analysis.tree.sibling_convention import sibling_tree_path`
- **Add:** `from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file`

### Helper `_sidecar`

Replace body:

```python
def _sidecar(tmp: Path, rel: str = _REL) -> Path:
    return sibling_tree_path((tmp / rel).resolve())
```

Update all `_sidecar(tmp_path)` calls to pass `rel` when tests use non-default paths.

### Sidecar assertion migration (JSON file test `test_replace_via_json_pointer_updates_draft_then_commits`)

Replace:

```python
payload = json.loads(sc.read_text(encoding="utf-8"))
assert payload["source_sha256"] == _sha(...)
assert isinstance(payload["root"], list)
```

With:

```python
sections = parse_tree_file(sc.read_text(encoding="utf-8"))
assert sections.checksums["source_sha256"] == _sha((tmp_path / _REL).read_bytes())
assert sections.tree.strip() != ""
assert sections.map.next_free >= 1
```

Apply same pattern anywhere sidecar JSON payload is parsed in both edit_write_close files.

## Preview file pointer replacements (JSON)

Constants unchanged: `_REL = "cfg/detail.json"`, `_DOC`, `_PID`, etc.

Every assignment `sc = tmp_path / ".trees" / f"{_REL}.tree"` → `sc = _sidecar_path(tmp_path, _REL)`.

Every `payload = json.loads(sc.read_text(...))` used only for stable ID lookup → remove; use `_uuid_for_pointer` instead.

Tests affected (keep names):

- `test_scalar_stable_id_resolves_container_children_matching_parent_preview`
- `test_root_scalar_json_preview_equivalent_without_ref`
- `test_rescan_after_external_edit_and_removed_sidecar_generates_new_uuid`
- `test_stable_id_persists_across_sessions_without_disk_change`

For rescan test: after `sc.unlink()`, sidecar is recreated on next commit at **same sibling path** `_sidecar_path(tmp_path, _REL)`.

## Preview file pointer replacements (YAML)

Same helper pattern; `_REL = "cluster/cfg/detail.yaml"`.

Tests affected:

- `test_yaml_scalar_node_ref_matches_container_preview_set`
- `test_yaml_root_scalar_matches_absent_node_ref`
- `test_yaml_sidecar_regenerates_stable_id_after_external_edit_with_sidecar_removed`
- `test_yaml_stable_id_stable_across_reopen_without_disk_change`

YAML pointers: `/svc`, `/svc/env`, etc. (match existing `_find_stable_by_path` arguments).

## Imports to add (preview files)

Add to both preview modules:

- `from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file`
- `from code_analysis.tree.handler_registry import HandlerRegistry`
- `from code_analysis.tree.sibling_convention import sibling_tree_path`

## Mandatory validation

Run from project root:

```bash
source .venv/bin/activate
black tests/test_tree_temp_universal_json_preview_sessions.py tests/test_tree_temp_universal_yaml_preview_sessions.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py
flake8 tests/test_tree_temp_universal_json_preview_sessions.py tests/test_tree_temp_universal_yaml_preview_sessions.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py
pytest tests/test_tree_temp_universal_json_preview_sessions.py tests/test_tree_temp_universal_yaml_preview_sessions.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py -v
```

Expected:

- No collection errors (edit_write_close modules import cleanly).
- All tests in the four modules PASSED (8 previously failing preview tests + full edit_write_close suite).

**Completion condition:** all tests pass.

## Decision rules

- One coordinated migration: all four files in a single coder pass.
- Preserve async `@pytest.mark.asyncio` patterns and mock DB patches unchanged unless path-related.

## Blackstops

- If preview commands still write legacy JSON sidecar (not three-section), stop and escalate — integration/sidecar writer not migrated.
- If `_uuid_for_pointer` cannot match nodes, read `code_analysis/tree/handlers/json_handler.py` / `yaml_handler.py` attribute keys and adjust pointer normalization only within this step (do not change handlers).

## Handoff package

- Modified: four test files listed above.
- Verification: pytest command above — 0 errors, all green.
