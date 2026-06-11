# G-003 Remediation: Wire universal_file_* to Core EditSession (C-012)

## Purpose

Make the production edit pipeline use `code_analysis.core.edit_session.EditSession` so `get_active_session()` populates the registry and `session_git_*` / `session_write` commands work on sessions opened via `universal_file_open`.

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
- T-001 EditSession lifecycle (active-session registry as sole resolution mechanism)

## Scope

**Included:**
- Refactor `code_analysis/commands/universal_file_edit/session.py` to delegate to core `EditSession` OR replace legacy in-memory `EditSession` with thin wrapper/facade over core C-012.
- Ensure `UniversalFileOpenCommand` (open_command.py) calls `EditSession.open(...)` and returns `session_id` from core instance.
- Ensure edit path applies mutations via `apply_valid_tree_mutation` / `apply_plaintext_mutation` based on session tree validity (not only legacy draft buffer).
- Ensure `UniversalFileCloseCommand` calls core `EditSession.close()`.
- Eliminate dual registry: `session_git_*` and `session_write` must resolve same sessions as `universal_file_*`.

**Excluded:**
- Removing `universal_file_write` entirely (may remain for backward compat if it delegates to `session_write` preview/confirm semantics).
- G-000 sidecar path migration in unrelated preview tests.

## Boundaries

- Do not rename public MCP command names (`universal_file_open`, etc.).
- Do not modify HRS/MRS.

## Dependencies

- `g-003-core-bugfixes.md` (recommended complete first)

## Parallelization note

Serialize after core bugfixes. Parallel with test implementation once wiring approach is clear.

## Expected outcome

- Opening a file via `universal_file_open` registers core `EditSession` in `_active_sessions`.
- `session_git_log` with returned `session_id` returns commit history after edits.
- `session_write` preview/confirm operates on same session.
- Existing tests in `tests/test_tree_temp_edit_session_lifecycle.py` continue to pass (update only if session_id/draft semantics change in response shape).

## Correction items

Researcher audit:
- `EditSession.open()` has zero production call sites.
- Legacy `commands.universal_file_edit.session.EditSession` is separate in-memory model.
- Registry split blocks E2E G-003.

## File inventory

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/commands/universal_file_edit/session.py` | Delegate to core EditSession |
| modify | `code_analysis/commands/universal_file_edit/open_command.py` | Call `EditSession.open` |
| modify | `code_analysis/commands/universal_file_edit/close_command.py` | Call core `close()` |
| modify | `code_analysis/commands/universal_file_edit/write_command.py` | Optional: delegate external write to `session_write` semantics or core preview/confirm |
| modify | `code_analysis/commands/universal_file_edit/tree_temp_write_commit.py` or edit path | Route mutations through core apply_* methods |

Exact edit routing files to be confirmed by coder from call graph; minimum set above is mandatory.

## Class/function inventory

### Core (consume, do not duplicate)

- `code_analysis.core.edit_session.EditSession.open(project_id, file_path, content=None) -> EditSession`
- `EditSession.apply_valid_tree_mutation(mutator: Callable) -> None`
- `EditSession.apply_plaintext_mutation(new_source: str) -> None`
- `EditSession.close() -> None`
- `get_active_session(session_id: str) -> EditSession`

### Legacy facade (modify)

- `commands.universal_file_edit.session.create_session` → must create/register core session
- `get_session(session_id)` → must call `get_active_session` or wrap same dict

## Error handling map

| condition | exception / code | behavior |
|-----------|------------------|----------|
| FINAL-2 content on valid file | `EditSessionError` / `CONTENT_NOT_ALLOWED_FOR_VALID_FILE` | propagate to open command response |
| Unknown session_id | `KeyError` | existing SESSION_NOT_FOUND patterns |

## Test plan

- Existing: `tests/test_tree_temp_edit_session_lifecycle.py`, `tests/test_tree_temp_edit_session_preview.py` must stay green.
- New integration tests in `g-003-test-coverage.md`.

## Concrete examples

1. `universal_file_open` → response includes `session_id`; `get_active_session(session_id)` succeeds.
2. After `universal_file_edit` + commit, `session_git_log` lists ≥2 commits (initial + mutation).

## Forbidden approaches

- Do not maintain two parallel session registries.
- Do not leave `EditSession.open()` unused after this task.
- Do not bypass per-mutation SessionRepo commits during edit commit path.
