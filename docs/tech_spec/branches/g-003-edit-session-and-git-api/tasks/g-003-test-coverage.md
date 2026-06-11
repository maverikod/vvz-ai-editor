# G-003 Remediation: Test Coverage for Edit Session and Git API

## Purpose

Add pytest coverage for T-001–T-004 behaviors not exercised by legacy universal_file tests, satisfying GREEN criterion #2 for G-003.

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
- All four G-003 tactical steps (T-001–T-004)

## Scope

**Included — new test modules:**
- `tests/unit/test_session_repo.py` — init FULL/DEGRADED, one commit per mutation, log, revert creates new commit
- `tests/unit/test_marker_cycle.py` — denude/restore preserves MAP/CHECKSUMS; UUID4 unchanged
- `tests/unit/test_edit_session_lifecycle.py` — open/FINAL-2 guard, valid vs invalid mutation paths, revalidation, close deletes session dir
- `tests/test_session_git_commands.py` — all five session_git_* commands with temp session fixture; SESSION_NOT_FOUND without open session
- `tests/test_session_write_command.py` — preview no external write; confirm copies; requires session_id

**Included — fix stale tests (sidecar path):**
- Update `tests/test_tree_temp_universal_json_preview_sessions.py`
- Update `tests/test_tree_temp_universal_yaml_preview_sessions.py`
- Fix collection errors in `tests/test_tree_temp_universal_json_edit_write_close.py` and `tests/test_tree_temp_universal_yaml_edit_write_close.py` (replace deleted `sidecar_paths` imports with co-located sibling tree path helpers)

**Excluded:**
- `test_data/` server-sandboxed tests (use tester_ca if needed later)

## Boundaries

- Tests only under `tests/`; no test_data edits via direct file tools.

## Dependencies

- `g-003-core-bugfixes.md` complete
- `g-003-mcp-command-registration.md` complete
- `g-003-universal-file-integration.md` complete (integration tests depend on wiring)

## Parallelization note

Planner creates atomic steps first. Coder implements tests after integration lands. Stale sidecar test fixes can start in parallel with integration if paths are independent.

## Expected outcome

- `pytest tests/unit/test_session_repo.py tests/unit/test_marker_cycle.py tests/unit/test_edit_session_lifecycle.py tests/test_session_git_commands.py tests/test_session_write_command.py` — all pass
- Previously failing 8 preview session tests pass
- 2 collection-error modules collect and pass

## Test plan detail

### test_session_repo.py

- `test_init_full_commit_captures_tree_and_source`
- `test_commit_degraded_source_only`
- `test_two_mutations_two_commits`
- `test_revert_adds_new_commit_not_reset`

### test_marker_cycle.py

- `test_denude_restore_preserves_map_uuids`
- `test_restore_uses_prior_map_next_free`

### test_edit_session_lifecycle.py

- `test_open_rejects_content_when_valid_external_file`
- `test_valid_mutation_commits_tree_and_source`
- `test_invalid_plaintext_commits_source_only`
- `test_revalidation_restores_valid_mode`
- `test_close_removes_session_directory`

### test_session_git_commands.py

- Fixtures: tmp project dir, open core EditSession, apply mutation
- `test_session_git_log_returns_commits`
- `test_session_git_diff_tree_mode`
- `test_session_git_diff_source_mode`
- `test_session_git_show`, `test_session_git_status`, `test_session_git_revert`
- `test_missing_session_id_errors`

### test_session_write_command.py

- `test_preview_does_not_modify_external_files`
- `test_confirm_copies_when_confirm_true`

## Forbidden approaches

- Do not skip integration tests with only mocked SessionRepo while leaving wiring broken.
- Do not use `.trees/` legacy paths in updated preview tests; use co-located `{file}.tree` sibling layout.
