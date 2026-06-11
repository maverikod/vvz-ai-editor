# Step 14: code_analysis/commands/write_project_text_lines_command.py

## Scope

Fix the legacy `write_project_text_lines` command so it remains safe while the universal file command layer is introduced.

This step owns only:

- `code_analysis/commands/write_project_text_lines_command.py`
- directly needed shared helper code for text-safe metadata update, if no suitable helper exists
- tests that verify this command behavior

Do not edit `.venv`, `site-packages`, installed packages, or unrelated packages.

## Current-code reads before edits

Run MCP reads/searches first:

```text
read_project_text_file code_analysis/commands/write_project_text_lines_command.py lines 1-520
read_project_text_file code_analysis/commands/project_text_file_guard.py lines 1-220
fulltext_search update_file_data_atomic_batch
fulltext_search build_file_data_atomic_batches ast.parse
```

Confirm and record in `observations.md`:

- current command already restricts writes to `.adoc`, `.md`, `.rst`, `.txt`;
- current command still calls `update_file_data_atomic_batch` after a text write;
- this call is the bug source for Markdown/plain text.

## Implementation

1. Preserve public parameters:

```text
project_id
file_path
start_line
end_line
new_lines
backup
```

2. Keep existing source suffix guards. Do not weaken them.

3. Keep the strict plain-text allowlist:

```text
.adoc
.md
.rst
.txt
```

4. Remove direct use of `update_file_data_atomic_batch` from the plain-text write path.

5. Replace it with a text-safe metadata update path that updates only generic file metadata:

```text
path
project_id
line count
last modified time
file record existence/state
```

6. Do not call Python AST, CST, entity extraction, chunk extraction, vector indexing, or code-oriented file-data update for these text suffixes.

7. Validation must happen before backup and before write:

- unsupported suffix;
- source-code suffix;
- invalid range;
- missing project;
- missing file;
- venv path.

8. For writes, do not clamp out-of-range values silently. Invalid write ranges must return `INVALID_RANGE` before backup/write.

9. Preserve backup/restore behavior for actual write failures.

## Validation

Run MCP-level checks, not only unit tests.

Required positive check:

```text
create_text_file on a test .md file with overwrite=true
write_project_text_lines on that .md file
read_project_text_file on that .md file
```

Expected:

- proxy envelope may be success, but inner command result must also have `success=true`;
- read-back confirms changed content;
- result does not include `UPDATE_FILE_DATA_ERROR`;
- no Python parse error appears.

Required negative checks:

```text
write_project_text_lines on .py -> PYTHON_FILE_FORBIDDEN
write_project_text_lines on .go or .rs -> CODE_FILE_FORBIDDEN
write_project_text_lines on .json -> TEXT_FILE_SUFFIX_NOT_ALLOWED
write_project_text_lines with start_line > end_line -> INVALID_RANGE before backup/write
write_project_text_lines under .venv -> PROJECT_VENV_WRITE_FORBIDDEN
```

## Read-back verification

After every source edit, read the changed source file with `read_project_text_file`.

After every MCP write test, verify with a separate `read_project_text_file` command.

## Observations entry

Append to `docs/plans/2026-04-27-universal-file-commands-refactor/observations.md`:

```text
Command:
Expected:
Actual:
Error:
Root cause:
Fix:
Post-fix verification:
Status:
```

## Stop condition

Stop and report instead of guessing if:

- no text-safe metadata update can be implemented without changing storage abstractions;
- `update_file_data_atomic_batch` is used by non-text code in a way that needs a separate storage-layer design;
- MCP write succeeds at proxy level but inner command result has `success=false`.
