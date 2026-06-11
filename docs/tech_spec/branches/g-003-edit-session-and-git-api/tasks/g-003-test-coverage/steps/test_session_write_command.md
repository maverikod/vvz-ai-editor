# Atomic step AS-006: Integration tests for session_write MCP command (C-012)

## Executor role

`coder_auto`

## Execution directive

Create `tests/test_session_write_command.py` with two tests for preview (no external write) and confirm (atomic copy-out). Do not modify production code.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_session_write_command.py`
- **action:** create

## Dependency contract

- **Depends on:** `g-003-universal-file-integration.md` **must be complete**.
- **Depends on (recommended):** AS-003 (`EditSession.preview_external_write` / `confirm_external_copy_out` behavior).
- **Blocks:** none.

## Required context

- `SessionWriteCommand` in `code_analysis/commands/universal_file_edit/session_write_command.py`.
- Preview (`confirm=False`): calls `preview_external_write()`; never touches external files.
- Confirm (`confirm=True`): calls `confirm_external_copy_out()`; copies in-session source + tree to external sibling paths when tree validity is VALID.
- Requires active `session_id` from `EditSession.open`.

## Read first (exact paths)

1. `code_analysis/commands/universal_file_edit/session_write_command.py`
2. `code_analysis/core/edit_session/edit_session.py` — preview/confirm methods
3. `code_analysis/tree/sibling_convention.py` — external tree path
4. `tests/test_tree_temp_edit_session_lifecycle.py` — external file hash patterns

## Expected file change

- New async test module with helper, fixture, two tests.

## Forbidden alternatives

- Do not use `UniversalFileWriteCommand` in place of `SessionWriteCommand`.
- Do not edit `test_data/`.
- Do not mock `shutil.copy2` (exercise real copy-out).
- Do not confirm before mutating (no-op confirm is valid but doesn't test copy).

## File header

```
"""
Integration tests for session_write two-stage external copy-out (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Imports

- `from __future__ import annotations`
- `import hashlib`
- `from pathlib import Path`
- `import pytest`
- `from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult`
- `from code_analysis.commands.universal_file_edit.errors import SESSION_NOT_FOUND`
- `from code_analysis.commands.universal_file_edit.session_write_command import SessionWriteCommand`
- `from code_analysis.core.edit_session.edit_session import EditSession, get_active_session`
- `from code_analysis.core.tree_lifecycle.builder import TreeBuilder`
- `from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum`
- `from code_analysis.tree.sibling_convention import sibling_tree_path`

## Constants

- `PROJECT_ID = "00000000-0000-0000-0000-000000000014"`
- `REL = "write/demo.json"`
- `INITIAL_JSON = '{"n": 1}\n'`
- `MUTATED_JSON fragment in session after edit: '"n": 99'`

## Helper

**`def _sha_hex(path: Path) -> str:`** — return `hashlib.sha256(path.read_bytes()).hexdigest()`.

## Fixture `open_mutated_session`

**`@pytest.fixture def open_mutated_session(tmp_path: Path) -> EditSession:`**

1. Write external source at `tmp_path / REL` with `INITIAL_JSON`.
2. Build sibling tree via `TreeBuilder.build`.
3. `session = EditSession.open(source_abs=..., project_root=tmp_path, file_path=REL)`.
4. Mutate: `session.apply_valid_tree_mutation(lambda t: t.replace('"n": 1', '"n": 99'))`.
5. Yield session; close in finally.

## Test 1 — `test_preview_does_not_modify_external_files`

**`@pytest.mark.asyncio`**

1. Use fixture session.
2. `source = tmp_path / REL`; `tree = sibling_tree_path(source)`.
3. Record `source_hash_before = _sha_hex(source)` and `tree_hash_before = _sha_hex(tree)`.
4. `cmd = SessionWriteCommand()`.
5. `res = await cmd.execute(project_id=PROJECT_ID, session_id=session.session_id, confirm=False)`.
6. Assert SuccessResult; `res.data["phase"] == "preview"`.
7. Assert `res.data["has_changes"] is True`.
8. Assert `"source_diff" in res.data` and diff non-empty.
9. Assert `_sha_hex(source) == source_hash_before`.
10. Assert `_sha_hex(tree) == tree_hash_before`.
11. Assert external source text still contains `"n": 1` (not yet copied).

## Test 2 — `test_confirm_copies_when_confirm_true`

**`@pytest.mark.asyncio`**

1. Use fixture session (mutated in-session, external still initial).
2. `cmd = SessionWriteCommand()`.
3. Preview first: `await cmd.execute(..., confirm=False)` — assert has_changes True.
4. `confirm_res = await cmd.execute(project_id=PROJECT_ID, session_id=session.session_id, confirm=True)`.
5. Assert SuccessResult; `confirm_res.data["phase"] == "confirmed"`.
6. External source text contains `"n": 99`.
7. `tree = sibling_tree_path((tmp_path / REL).resolve())` still exists.
8. Assert `tree.read_text(encoding="utf-8")` contains `---TREE---` (marked tree artefact).
9. Assert in-session source hash matches external: `_sha_hex(session.session_source_path) == _sha_hex(tmp_path / REL)`.

## Additional test (required by tactical task "requires session_id")

Add **`async def test_missing_session_id_errors(tmp_path: Path) -> None:`**

1. `res = await SessionWriteCommand().execute(project_id=PROJECT_ID, session_id="00000000-0000-4000-8000-000000000088")`.
2. Assert ErrorResult with `code == SESSION_NOT_FOUND`.

## Error handling

- Preview/confirm success paths only in main tests; missing session expects ErrorResult.

## Edge cases

- Confirm when `has_changes` False: not tested here (mutation ensures changes).
- VALID session copies both artefacts (assert tree updated).

## Mandatory validation

```bash
source .venv/bin/activate
black tests/test_session_write_command.py
flake8 tests/test_session_write_command.py
mypy tests/test_session_write_command.py
pytest tests/test_session_write_command.py -v
```

Expected: 3 passed.

**Completion condition:** all tests pass.

## Decision rules

- Use `SessionWriteCommand` only (not legacy write_mode on `UniversalFileWriteCommand`).
- Pass explicit `confirm=False` in preview test.

## Blackstops

- If preview modifies external files, stop — production bug in `session_write` / `EditSession.preview_external_write`; escalate before weakening test.

## Handoff package

- File: `tests/test_session_write_command.py`
- Command: `pytest tests/test_session_write_command.py -v`
- Expected: 3 PASSED
