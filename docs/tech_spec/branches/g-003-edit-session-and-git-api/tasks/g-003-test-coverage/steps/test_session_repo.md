# Atomic step AS-001: Unit tests for SessionRepo (C-013)

## Executor role

`coder_auto`

## Execution directive

Create `tests/unit/test_session_repo.py` with four test functions exercising `SessionRepo.init`, `commit_full`, `commit_degraded`, `log`, and `revert`. Do not modify production code in this step.

## Parent links (mandatory)

1. Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
2. Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file (full path from repo root):** `tests/unit/test_session_repo.py`
- **action:** create

## Dependency contract

- **Depends on:** `g-003-core-bugfixes.md` complete (`SessionRepo` implementation stable).
- **Blocks:** AS-005 (recommended context; not a hard import dependency).

## Required context

- `SessionRepo` lives in `code_analysis/core/edit_session/session_repo.py`.
- Commits stage files named `source_name` and `tree_name` inside `repo_dir`.
- `revert(rev=...)` restores tree bytes at `rev` and calls `commit_full` (adds a new commit; history is not truncated).

## Read first (exact paths)

1. `code_analysis/core/edit_session/session_repo.py` — full API.
2. `tests/unit/test_session_heartbeat.py` — pytest + `tmp_path` style reference.

## Expected file change

- New file `tests/unit/test_session_repo.py` with module docstring, helpers, and four test functions listed below.

## Forbidden alternatives

- Do not read or edit files under `test_data/`.
- Do not mock `dulwich`; use real `SessionRepo` against `tmp_path`.
- Do not modify `session_repo.py` or any production module.
- Do not skip revert history-preservation assertion.

## Atomic operations

1. Create `tests/unit/test_session_repo.py`.
2. Add module docstring (see File header).
3. Add helper `_write_pair(repo_dir, source_name, tree_name, source_text, tree_text)`.
4. Implement four test functions with exact names from tactical task.

## File header (exact module docstring)

```
"""
Unit tests for SessionRepo per-mutation git history (C-013).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Imports

Complete import list (exact syntax):

- `from __future__ import annotations`
- `from pathlib import Path`
- `import pytest`
- `from code_analysis.core.edit_session.session_repo import SessionRepo`

## Class/function skeleton

No classes.

**Helper:** `def _write_pair(repo_dir: Path, source_name: str, tree_name: str, source_text: str, tree_text: str) -> None:`  
Summary: Write `repo_dir / source_name` and `repo_dir / tree_name` with UTF-8 text; create parent dirs if needed.

**Test 1:** `def test_init_full_commit_captures_tree_and_source(tmp_path: Path) -> None:`

**Test 2:** `def test_commit_degraded_source_only(tmp_path: Path) -> None:`

**Test 3:** `def test_two_mutations_two_commits(tmp_path: Path) -> None:`

**Test 4:** `def test_revert_adds_new_commit_not_reset(tmp_path: Path) -> None:`

## Method logic — helper `_write_pair`

1. `repo_dir.mkdir(parents=True, exist_ok=True)`.
2. `(repo_dir / source_name).write_text(source_text, encoding="utf-8")`.
3. `(repo_dir / tree_name).write_text(tree_text, encoding="utf-8")`.

## Method logic — test 1 `test_init_full_commit_captures_tree_and_source`

1. Set constants: `source_name = "demo.json"`, `tree_name = "demo.json.tree"`, `repo_dir = tmp_path / "repo_full"`.
2. Call `_write_pair(repo_dir, source_name, tree_name, '{"a":1}\n', '---CHECKSUMS---\ntree-v1\n')`.
3. `repo = SessionRepo.init(repo_dir=repo_dir, source_name=source_name, tree_name=tree_name, include_tree=True)`.
4. `commits = repo.log()`.
5. Assert `len(commits) == 1`.
6. Assert `commits[0].message == "session: initial commit"`.
7. `shown_source = repo.show_source(rev=commits[0].hash).decode("utf-8")`.
8. Assert `shown_source == '{"a":1}\n'`.
9. `shown_tree = repo.show_tree(rev=commits[0].hash).decode("utf-8")`.
10. Assert `"tree-v1" in shown_tree`.

## Method logic — test 2 `test_commit_degraded_source_only`

1. Same names; `repo_dir = tmp_path / "repo_deg"`.
2. `_write_pair(..., source_text='broken\n', tree_text='ignored\n')`.
3. `repo = SessionRepo.init(..., include_tree=False)`.
4. Assert `len(repo.log()) == 1`.
5. Assert `repo.log()[0].message == "session: initial commit (degraded)"`.
6. `head = repo.log()[0].hash`.
7. Assert `repo.show_source(rev=head).decode("utf-8") == "broken\n"`.

## Method logic — test 3 `test_two_mutations_two_commits`

1. `repo_dir = tmp_path / "repo_mut"`, names as above.
2. `_write_pair(..., '{"v":1}\n', 'tree-a\n')`.
3. `repo = SessionRepo.init(..., include_tree=True)`.
4. Overwrite working files: source `'{"v":2}\n'`, tree `'tree-b\n'`.
5. `repo.commit_full(message="session: mutation 1")`.
6. Overwrite tree to `'tree-c\n'`.
7. `repo.commit_full(message="session: mutation 2")`.
8. Assert `len(repo.log()) == 3`.
9. Assert messages in order (newest first from walker): `"session: mutation 2"`, `"session: mutation 1"`, `"session: initial commit"`.

## Method logic — test 4 `test_revert_adds_new_commit_not_reset`

1. `repo_dir = tmp_path / "repo_rev"`.
2. `_write_pair(..., '{"x":1}\n', 'tree-initial\n')`.
3. `repo = SessionRepo.init(..., include_tree=True)`.
4. `initial_hash = repo.log()[0].hash`.
5. Overwrite tree to `'tree-changed\n'`, `repo.commit_full(message="session: mutation")`.
6. `count_before = len(repo.log())` (must be 2).
7. `new_hash = repo.revert(rev=initial_hash)`.
8. `count_after = len(repo.log())`.
9. Assert `count_after == count_before + 1` (revert adds commit; history not reset).
10. Assert `new_hash != initial_hash`.
11. Assert `repo.show_tree(rev=new_hash).decode("utf-8") == "tree-initial\n"`.

## Error handling

- Tests rely on pytest assertions; no custom exception handling in test bodies.
- If `SessionRepo.init` raises, test fails (do not catch).

## Edge cases

- Empty repo_dir parent: helper creates it.
- Dulwich walker returns newest commit first: index `[0]` is HEAD.

## Constants and literals

- `source_name`: `"demo.json"`
- `tree_name`: `"demo.json.tree"`
- Initial full message: `"session: initial commit"`
- Initial degraded message: `"session: initial commit (degraded)"`
- Mutation messages: `"session: mutation 1"`, `"session: mutation 2"`, `"session: mutation"`

## Expected deliverables

- New test module with four passing tests.

## Mandatory validation

Run from project root with venv active:

```bash
source .venv/bin/activate
black tests/unit/test_session_repo.py
flake8 tests/unit/test_session_repo.py
mypy tests/unit/test_session_repo.py
pytest tests/unit/test_session_repo.py -v
```

Expected: black reformats or "unchanged"; flake8 silent (exit 0); mypy "Success: no issues found"; pytest 4 passed.

**Completion condition:** all tests pass.

## Decision rules

- Use real filesystem paths under `tmp_path` only.
- Do not parametrized-merge tests; one function per scenario.

## Blackstops

- If `SessionRepo.init` API differs from read-first file, stop and escalate to orchestrator_tactical (parent docs stale).
- If dulwich not installed in venv, stop and report CR-005 venv issue.

## Handoff package

- File: `tests/unit/test_session_repo.py`
- Verification command: `pytest tests/unit/test_session_repo.py -v`
- Expected: 4 PASSED
