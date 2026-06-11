# Parallel waves — G-003 test coverage atomic steps

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
- Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
- Technical specification: `docs/tech_spec/tech_spec.md`

## Wave 1 — unit tests and sidecar path fixes (parallel)

Run concurrently; no cross-dependencies.

| Step | Target |
|------|--------|
| AS-001 `test_session_repo.md` | `tests/unit/test_session_repo.py` |
| AS-002 `test_marker_cycle.md` | `tests/unit/test_marker_cycle.py` |
| AS-003 `test_edit_session_lifecycle.md` | `tests/unit/test_edit_session_lifecycle.py` |
| AS-004 `fix_stale_sidecar_path_tests.md` | 4 files under `tests/` |

**Prerequisite:** `g-003-core-bugfixes.md` complete (AS-001–003). AS-004 has no upstream dependency.

## Wave 2 — MCP command integration tests (parallel)

Run only after **`g-003-universal-file-integration.md`** is complete and Wave 1 steps are done.

| Step | Target |
|------|--------|
| AS-005 `test_session_git_commands.md` | `tests/test_session_git_commands.py` |
| AS-006 `test_session_write_command.md` | `tests/test_session_write_command.py` |

AS-005 and AS-006 may run in parallel with each other.

## Final gate

After all waves:

```bash
source .venv/bin/activate
pytest tests/unit/test_session_repo.py tests/unit/test_marker_cycle.py tests/unit/test_edit_session_lifecycle.py tests/test_session_git_commands.py tests/test_session_write_command.py tests/test_tree_temp_universal_json_preview_sessions.py tests/test_tree_temp_universal_yaml_preview_sessions.py tests/test_tree_temp_universal_json_edit_write_close.py tests/test_tree_temp_universal_yaml_edit_write_close.py -v
```

All tests must pass.
