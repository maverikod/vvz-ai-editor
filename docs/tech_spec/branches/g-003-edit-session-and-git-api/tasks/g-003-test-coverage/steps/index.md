# Atomic step index — G-003 test coverage

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
- Tactical task: `docs/tech_spec/branches/g-003-edit-session-and-git-api/tasks/g-003-test-coverage.md`
- Technical specification: `docs/tech_spec/tech_spec.md`

## Goal

Add pytest coverage for EditSession (C-012), SessionRepo (C-013), marker cycle, session_git_* / session_write MCP commands, and fix stale `.trees/` sidecar path tests.

## Atomic steps

| Step ID | File | Target | Depends on |
|---------|------|--------|------------|
| AS-001 | `test_session_repo.md` | `tests/unit/test_session_repo.py` | `g-003-core-bugfixes.md` |
| AS-002 | `test_marker_cycle.md` | `tests/unit/test_marker_cycle.py` | `g-003-core-bugfixes.md` |
| AS-003 | `test_edit_session_lifecycle.md` | `tests/unit/test_edit_session_lifecycle.py` | `g-003-core-bugfixes.md` |
| AS-004 | `fix_stale_sidecar_path_tests.md` | 4 legacy test modules (see step) | none (parallel with AS-001–003) |
| AS-005 | `test_session_git_commands.md` | `tests/test_session_git_commands.py` | `g-003-universal-file-integration.md`, AS-001–003 |
| AS-006 | `test_session_write_command.md` | `tests/test_session_write_command.py` | `g-003-universal-file-integration.md`, AS-003 |

## Execution order

1. Wave 1 (parallel): AS-001, AS-002, AS-003, AS-004
2. Wave 2 (parallel after integration): AS-005, AS-006

See `parallel_waves.md` for details.
