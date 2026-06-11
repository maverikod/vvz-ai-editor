# Atomic step AS-005: Integration tests for session_git_* MCP commands (C-014)

## Executor role

`coder_auto`

## Execution directive

Create `tests/test_session_git_commands.py` exercising all five `session_git_*` commands against a live core `EditSession` registered via `EditSession.open`. Do not modify production code.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file:** `tests/test_session_git_commands.py`
- **action:** create

## Dependency contract

- **Depends on:** `g-003-universal-file-integration.md` **must be complete** (single registry; MCP commands registered). Also `g-003-mcp-command-registration.md` and `g-003-core-bugfixes.md`.
- **Depends on (recommended):** AS-001, AS-003 complete for stable SessionRepo/EditSession behavior.
- **Blocks:** none.

## Required context

- Commands resolve sessions via `get_active_session(session_id)` from core `EditSession.open`.
- Error code for missing session: `SESSION_NOT_FOUND` from `code_analysis/commands/universal_file_edit/errors.py`.
- Fixture opens JSON file with valid sibling tree, applies one valid mutation to produce ≥2 commits.

## Read first (exact paths)

1. `code_analysis/commands/universal_file_edit/session_git_log_command.py`
2. `code_analysis/commands/universal_file_edit/session_git_diff_command.py`
3. `code_analysis/commands/universal_file_edit/session_git_show_command.py`
4. `code_analysis/commands/universal_file_edit/session_git_status_command.py`
5. `code_analysis/commands/universal_file_edit/session_git_revert_command.py`
6. `code_analysis/core/edit_session/edit_session.py`
7. `tests/unit/test_edit_session_lifecycle.py` (after AS-003) — fixture patterns

## Expected file change

- New async test module with fixture + six test functions.

## Forbidden alternatives

- Do not mock `SessionRepo.log` while leaving command wiring untested.
- Do not use legacy `commands.universal_file_edit.session.create_session` without core `EditSession.open`.
- Do not edit `test_data/`.
- Do not modify command implementations.

## Atomic operations

1. Create module + docstring.
2. Add `@pytest.fixture` `mutated_json_session`.
3. Implement six tests (exact names below).

## File header

```
"""
Integration tests for session_git_* MCP commands (C-014).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Imports

- `from __future__ import annotations`
- `from pathlib import Path`
- `import pytest`
- `from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult`
- `from code_analysis.commands.universal_file_edit.errors import SESSION_NOT_FOUND`
- `from code_analysis.commands.universal_file_edit.session_git_diff_command import SessionGitDiffCommand`
- `from code_analysis.commands.universal_file_edit.session_git_log_command import SessionGitLogCommand`
- `from code_analysis.commands.universal_file_edit.session_git_revert_command import SessionGitRevertCommand`
- `from code_analysis.commands.universal_file_edit.session_git_show_command import SessionGitShowCommand`
- `from code_analysis.commands.universal_file_edit.session_git_status_command import SessionGitStatusCommand`
- `from code_analysis.core.edit_session.edit_session import EditSession`
- `from code_analysis.core.tree_lifecycle.builder import TreeBuilder`
- `from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum`

## Constants

- `PROJECT_ID = "00000000-0000-0000-0000-0000000000g3"` — use `"00000000-0000-0000-0000-000000000013"` (valid hex UUID for schema).
- `REL = "session/git_demo.json"`
- `INITIAL_JSON = '{"value": 1}\n'`

## Fixture `mutated_json_session`

**Signature:** `@pytest.fixture def mutated_json_session(tmp_path: Path) -> EditSession:`

Algorithm:

1. `source = tmp_path / REL`; create parent dirs; write `INITIAL_JSON`.
2. `checksum = compute_content_checksum(INITIAL_JSON)`.
3. `TreeBuilder.build(content=INITIAL_JSON, source_abs=source, file_path=REL, content_checksum=checksum)`.
4. `session = EditSession.open(source_abs=source, project_root=tmp_path, file_path=REL)`.
5. `session.apply_valid_tree_mutation(lambda t: t.replace('"value": 1', '"value": 2'))`.
6. `yield session`.
7. In `finally`: if `session.is_open`: `session.close()`.

## Test functions (exact names)

1. `async def test_session_git_log_returns_commits(mutated_json_session: EditSession) -> None:`
2. `async def test_session_git_diff_tree_mode(mutated_json_session: EditSession) -> None:`
3. `async def test_session_git_diff_source_mode(mutated_json_session: EditSession) -> None:`
4. `async def test_session_git_show(mutated_json_session: EditSession) -> None:`
5. `async def test_session_git_status(mutated_json_session: EditSession) -> None:`
6. `async def test_missing_session_id_errors(tmp_path: Path) -> None:`

Mark async tests with `@pytest.mark.asyncio`.

## Test 1 — `test_session_git_log_returns_commits`

1. `cmd = SessionGitLogCommand()`.
2. `res = await cmd.execute(project_id=PROJECT_ID, session_id=mutated_json_session.session_id)`.
3. Assert `isinstance(res, SuccessResult)`.
4. `commits = res.data["commits"]`.
5. Assert `len(commits) >= 2`.
6. Assert each entry has keys `hash`, `message`, `timestamp`.
7. Assert `commits[0]["hash"]` is 40-char hex (git sha).

## Test 2 — `test_session_git_diff_tree_mode`

1. `log = mutated_json_session.session_repo.log()`.
2. `rev_b = log[0]["hash"] if isinstance(log[0], dict) else log[0].hash` — use attribute `.hash` from dataclass when calling repo directly; from command response use dict keys.
3. Prefer: `commits = mutated_json_session.session_repo.log()` → `rev_new = commits[0].hash`, `rev_old = commits[1].hash`.
4. `cmd = SessionGitDiffCommand()`.
5. `res = await cmd.execute(project_id=PROJECT_ID, session_id=mutated_json_session.session_id, mode="tree", rev_a=rev_old, rev_b=rev_new)`.
6. Assert SuccessResult; `diff = res.data["diff"]`; assert `diff` contains `"tree@"` or `"---"` unified diff hunk markers.

## Test 3 — `test_session_git_diff_source_mode`

1. `rev_a = mutated_json_session.session_repo.log()[-1].hash` (initial commit).
2. `res = await SessionGitDiffCommand().execute(project_id=PROJECT_ID, session_id=mutated_json_session.session_id, mode="source", rev_a=rev_a)`.
3. Assert SuccessResult; assert `"in-session-source" in res.data["diff"]`.

## Test 4 — `test_session_git_show`

1. `rev = mutated_json_session.session_repo.log()[0].hash`.
2. `res = await SessionGitShowCommand().execute(project_id=PROJECT_ID, session_id=mutated_json_session.session_id, rev=rev)`.
3. Assert SuccessResult; `content = res.data["content"]`.
4. Assert `"---TREE---" in content` or `"value"` in content (tree artefact text).

## Test 5 — `test_session_git_status`

1. `res = await SessionGitStatusCommand().execute(project_id=PROJECT_ID, session_id=mutated_json_session.session_id)`.
2. Assert SuccessResult; assert `res.data["clean"] is True`.

## Test 6 — `test_missing_session_id_errors`

1. `bogus = "00000000-0000-4000-8000-000000000099"`.
2. For each command class in `(SessionGitLogCommand, SessionGitDiffCommand, SessionGitShowCommand, SessionGitStatusCommand, SessionGitRevertCommand)`:
   - Build minimal valid params: log/status use `(project_id, bogus)`; diff add `mode="tree", rev_a="a"*40, rev_b="b"*40`; show/revert add `rev="a"*40`.
   - `res = await cmd().execute(...)`.
   - Assert `isinstance(res, ErrorResult)`.
   - Assert `res.code == SESSION_NOT_FOUND`.

## Error handling

- Tests expect SuccessResult or ErrorResult; no bare exceptions.

## Edge cases

- Log walker order: index 0 is HEAD (newest).
- Revert command missing-session uses same SESSION_NOT_FOUND check (include in test 6).

## Mandatory validation

```bash
source .venv/bin/activate
black tests/test_session_git_commands.py
flake8 tests/test_session_git_commands.py
mypy tests/test_session_git_commands.py
pytest tests/test_session_git_commands.py -v
```

Expected: 6 passed.

**Completion condition:** all tests pass.

## Decision rules

- Use core `EditSession.open` fixture, not universal_file_open (unless needed for registry — open registers automatically).
- `project_id` is schema-required but ignored by commands; still pass constant.

## Blackstops

- If `get_active_session` fails for session opened via `EditSession.open`, stop — `g-003-universal-file-integration` incomplete.

## Handoff package

- File: `tests/test_session_git_commands.py`
- Command: `pytest tests/test_session_git_commands.py -v`
- Expected: 6 PASSED
