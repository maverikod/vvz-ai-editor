# Atomic step AS-003: Unit tests for EditSession lifecycle (C-012)

## Executor role

`coder_auto`

## Execution directive

Create `tests/unit/test_edit_session_lifecycle.py` covering FINAL-2 open guard, valid/invalid mutation paths, re-validation, and close cleanup. Do not modify production code.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/unit/test_edit_session_lifecycle.py`
- **action:** create

## Dependency contract

- **Depends on:** `g-003-core-bugfixes.md` complete.
- **Blocks:** AS-005, AS-006 (shared EditSession patterns).

## Required context

- `EditSession.open`, `apply_valid_tree_mutation`, `apply_plaintext_mutation`, `close`, `get_active_session` in `code_analysis/core/edit_session/edit_session.py`.
- `EditSessionError` and `CONTENT_NOT_ALLOWED_FOR_VALID_FILE`.
- `SessionTreeValidity.VALID` / `INVALID`.
- Valid JSON file + sibling `.tree` from `TreeBuilder.build` yields VALID session.

## Read first (exact paths)

1. `code_analysis/core/edit_session/edit_session.py` — full lifecycle API.
2. `code_analysis/core/tree_lifecycle/builder.py`
3. `code_analysis/core/tree_lifecycle/checksum.py` — `compute_content_checksum`
4. `tests/test_tree_temp_edit_session_lifecycle.py` — command-level patterns (checksum assertions)

## Expected file change

- New module with helpers and five test functions (exact names from tactical task).

## Forbidden alternatives

- Do not use `commands.universal_file_edit.session.EditSession` (legacy in-memory model).
- Do not edit `test_data/`.
- Do not mock `SessionRepo`; use real commits.
- Do not leave sessions open (always `close()` in `finally` or fixture teardown).

## Atomic operations

1. Create file + docstring.
2. Add helpers `_setup_valid_json(tmp_path) -> tuple[Path, Path, str]` returning `(project_root, source_abs, rel_path)`.
3. Add `_setup_invalid_json(tmp_path) -> tuple[Path, Path, str]` (valid source file, **no** sidecar / broken parse).
4. Implement five tests.

## File header

```
"""
Unit tests for core EditSession lifecycle (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Imports

- `from __future__ import annotations`
- `from pathlib import Path`
- `import pytest`
- `from code_analysis.core.edit_session.edit_session import (`  
  `    CONTENT_NOT_ALLOWED_FOR_VALID_FILE,`  
  `    EditSession,`  
  `    EditSessionError,`  
  `    SessionTreeValidity,`  
  `    get_active_session,`  
  `)`
- `from code_analysis.core.tree_lifecycle.builder import TreeBuilder`
- `from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum`

## Class/function skeleton

**Helper:** `def _setup_valid_json(tmp_path: Path) -> tuple[Path, Path, str]:`  
Create `nested/demo.json` with `'{"counter": 1}\n'`, build sibling tree, return `(tmp_path, source_abs, "nested/demo.json")`.

**Helper:** `def _setup_invalid_json(tmp_path: Path) -> tuple[Path, Path, str]:`  
Create `broken/demo.json` with content `'not-json\n'` only (no `.tree` file).

**Test 1:** `def test_open_rejects_content_when_valid_external_file(tmp_path: Path) -> None:`

**Test 2:** `def test_valid_mutation_commits_tree_and_source(tmp_path: Path) -> None:`

**Test 3:** `def test_invalid_plaintext_commits_source_only(tmp_path: Path) -> None:`

**Test 4:** `def test_revalidation_restores_valid_mode(tmp_path: Path) -> None:`

**Test 5:** `def test_close_removes_session_directory(tmp_path: Path) -> None:`

## Method logic — test 1

1. `(root, source_abs, rel) = _setup_valid_json(tmp_path)`.
2. `pytest.raises(EditSessionError)` context opening `EditSession.open(source_abs=source_abs, project_root=root, file_path=rel, content='{"counter": 99}\n')`.
3. Assert raised exception args[0] == `CONTENT_NOT_ALLOWED_FOR_VALID_FILE`.

## Method logic — test 2

1. Setup valid JSON; `session = EditSession.open(source_abs=source_abs, project_root=root, file_path=rel)`.
2. Try/finally: `session.close()` in finally.
3. Assert `session.tree_validity == SessionTreeValidity.VALID`.
4. `initial_commits = len(session.session_repo.log())` (expect 1).
5. Define `mutator` that replaces `"counter": 1` with `"counter": 42` in denuded JSON string argument.
6. `session.apply_valid_tree_mutation(mutator)`.
7. Assert `len(session.session_repo.log()) == initial_commits + 1`.
8. Assert `session.session_source_path.read_text(encoding="utf-8")` contains `"42"`.
9. Assert `session.session_tree_path.is_file()`.

## Method logic — test 3

1. `(root, source_abs, rel) = _setup_invalid_json(tmp_path)`.
2. `session = EditSession.open(...)`.
3. Assert `session.tree_validity == SessionTreeValidity.INVALID`.
4. `before = len(session.session_repo.log())`.
5. `session.apply_plaintext_mutation('{"counter": 5}\n')`.
6. Assert `len(session.session_repo.log()) == before + 1`.
7. Assert `session.session_repo.log()[0].message == "session: plaintext mutation"`.
8. Assert `session.tree_validity == SessionTreeValidity.INVALID` **before** any accidental revalidation — use broken initial content `'not-json\n'` and mutation `'{"still":1}\n'` if revalidation would trigger; **prescribed mutation:** `'<<<broken>>>\n'` so source stays unparseable.
9. Revised step 5: `session.apply_plaintext_mutation('<<<broken>>>\n')` — stays INVALID, degraded commit only.

## Method logic — test 4

1. `(root, source_abs, rel) = _setup_invalid_json(tmp_path)`.
2. Open session; assert INVALID.
3. `session.apply_plaintext_mutation('{"counter": 7}\n')` (valid JSON).
4. Assert `session.tree_validity == SessionTreeValidity.VALID`.
5. Assert `session.session_tree_path.is_file()`.
6. Close session.

## Method logic — test 5

1. Setup valid JSON; open session.
2. `session_dir = session.session_dir`.
3. Assert `session_dir.exists()`.
4. `sid = session.session_id`.
5. `session.close()`.
6. Assert not `session_dir.exists()`.
7. `pytest.raises(KeyError): get_active_session(sid)`.

## Error handling

- Test 1 expects `EditSessionError`; use `pytest.raises`.
- Test 5 expects `KeyError` from `get_active_session`.

## Edge cases

- Test 3: mutation must remain unparseable to test degraded-only path.
- Test 4: mutation must be parseable JSON to trigger `_try_revalidate`.

## Constants and literals

- Valid JSON: `'{"counter": 1}\n'`
- Valid rel: `"nested/demo.json"`
- Invalid rel: `"broken/demo.json"`
- Invalid initial: `'not-json\n'`
- Plaintext degraded body: `'<<<broken>>>\n'`
- Revalidation body: `'{"counter": 7}\n'`

## Mandatory validation

```bash
source .venv/bin/activate
black tests/unit/test_edit_session_lifecycle.py
flake8 tests/unit/test_edit_session_lifecycle.py
mypy tests/unit/test_edit_session_lifecycle.py
pytest tests/unit/test_edit_session_lifecycle.py -v
```

Expected: 5 passed.

**Completion condition:** all tests pass.

## Decision rules

- Always use **core** `code_analysis.core.edit_session.EditSession`.
- Close sessions in `finally` blocks to avoid leaking `_active_sessions`.

## Blackstops

- If `EditSession.open` does not register in `_active_sessions`, stop — core bugfix incomplete.

## Handoff package

- File: `tests/unit/test_edit_session_lifecycle.py`
- Command: `pytest tests/unit/test_edit_session_lifecycle.py -v`
- Expected: 5 PASSED
