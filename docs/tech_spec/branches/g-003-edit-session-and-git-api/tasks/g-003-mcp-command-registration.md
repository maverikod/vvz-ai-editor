# G-003 Remediation: Register Session Git and session_write MCP Commands

## Purpose

Expose C-014 SessionGitApi commands and T-004 `session_write` via server hooks so MCP clients can invoke them. Atomic step A-001 for session_write explicitly deferred registration.

## Parent links

- Plan global step: `docs/plans/marked_tree_unification/G-003-edit-session-and-git-api/README.yaml`
- Tactical steps: T-003 SessionGitApi, T-004 session_write

## Scope

**Included:**
- Import and register six command classes in `hooks_register_part2.py`:
  - `SessionGitLogCommand`
  - `SessionGitDiffCommand`
  - `SessionGitShowCommand`
  - `SessionGitStatusCommand`
  - `SessionGitRevertCommand`
  - `SessionWriteCommand`
- Use same registration pattern as adjacent `UniversalFile*` commands (`reg.register(..., 'custom')`).

**Excluded:**
- Schema/metadata changes unless required for import errors
- Core EditSession logic changes

## Boundaries

- Do not modify command implementation files except import path fixes if broken.
- Do not touch `test_data/`.

## Dependencies

- none (parallel with core bugfixes)

## Parallelization note

Fully parallel with `g-003-core-bugfixes.md`.

## Expected outcome

After server restart, `help` lists all six commands; each accepts `project_id` and `session_id`.

## Correction items

Researcher audit: zero references to `SessionGitLogCommand` etc. in `hooks_register_part1.py` / `hooks_register_part2.py`.

## File inventory

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/hooks_register_part2.py` | Register six G-003 commands |

## Import map (hooks_register_part2.py)

```python
from code_analysis.commands.universal_file_edit.session_git_log_command import SessionGitLogCommand
from code_analysis.commands.universal_file_edit.session_git_diff_command import SessionGitDiffCommand
from code_analysis.commands.universal_file_edit.session_git_show_command import SessionGitShowCommand
from code_analysis.commands.universal_file_edit.session_git_status_command import SessionGitStatusCommand
from code_analysis.commands.universal_file_edit.session_git_revert_command import SessionGitRevertCommand
from code_analysis.commands.universal_file_edit.session_write_command import SessionWriteCommand
```

Register names: `session_git_log`, `session_git_diff`, `session_git_show`, `session_git_status`, `session_git_revert`, `session_write` (match each class `.name` attribute).

## Test plan

- `tester_auto`: grep hooks file for six class names; optional import smoke `python -c "from code_analysis.hooks_register_part2 import ..."` 
- Covered by `tests/test_session_git_commands.py` after test task completes

## Forbidden approaches

- Do not register in part1 if part2 is the established home for universal_file_edit commands.
- Do not duplicate registration entries.
