# Step 22: tests MCP universal_file_commands

## Scope

Add MCP-level regression coverage for universal file commands and legacy compatibility. Unit tests alone are not enough.

Owned files:

- MCP regression test files for universal file commands
- test fixtures under dedicated test data only
- observations updates

Do not run destructive tests on `vast_srv` or real user projects. Use only dedicated test projects, temporary copies, or `test_data` subdirectories.

## Current-code reads before edits

Run these MCP reads/searches first:

```text
list_projects include_deleted=true
list_project_files file_pattern=code_analysis/commands/*universal* python_only=false
help universal_file_read
help universal_file_save
help universal_file_replace
help universal_file_delete
help write_project_text_lines
read_project_text_file docs/plans/2026-04-27-universal-file-commands-refactor/README.md lines 1-320
read_project_text_file docs/plans/2026-04-27-universal-file-commands-refactor/observations.md lines 1-220
```

If universal commands are not registered yet, record that and stop this step until Steps 09-12 and 17 are complete.

## Test project safety

Before any write/delete test, record the target project:

```text
project_id
name
path
deleted flag
files_count/chunks_count if available
```

Do not use `vast_srv` for destructive or write tests.

## Required positive MCP tests

### Text read/replace/save behavior

```text
create_text_file test .md
universal_file_read .md -> handler_id=text
universal_file_replace .md dry_run=true diff=true -> diff returned and file unchanged
universal_file_replace .md dry_run=false diff=true -> success true
read_project_text_file .md -> changed content verified
```

Repeat at least one read/replace case for `.txt`. Include `.rst` and `.adoc` routing checks.

### JSON behavior

```text
create_text_file test .json with valid JSON
universal_file_read .json -> handler_id=json
universal_file_replace .json -> JSON handler semantics, not raw text line replacement
json_load_file or universal_file_read -> verify resulting JSON structure
```

### Python behavior

```text
create_text_file test .py with valid Python
universal_file_read .py -> handler_id=python or documented safe Python read response
universal_file_replace .py -> CST-safe path only, or documented unsupported-operation error before side effects
```

If Python replace is supported, verify with CST/readback and syntax validation.

## Required negative MCP tests

```text
universal_file_read .toml -> UNSUPPORTED_FILE_EXTENSION
universal_file_replace .toml -> UNSUPPORTED_FILE_EXTENSION before backup/write
universal_file_replace unknown suffix -> UNSUPPORTED_FILE_EXTENSION before backup/write
universal_file_replace .json with text range params -> schema/handler error before write
universal_file_replace .py through text params -> Python handler or error, never text handler
universal_file_replace invalid text range -> INVALID_RANGE before backup/write
universal_file_replace overlapping multi-ranges -> overlap error before backup/write
write_project_text_lines .json -> TEXT_FILE_SUFFIX_NOT_ALLOWED
write_project_text_lines .py -> PYTHON_FILE_FORBIDDEN
write_project_text_lines .go/.rs -> CODE_FILE_FORBIDDEN
```

## Queue/proxy result rule

Do not treat proxy envelope success as command success. For every MCP call inspect the inner result:

```text
result.success
result.data.success when present
result.error.code when present
```

A proxy response with outer `success=true` and inner `result.success=false` is a failed command.

## Validation evidence

For every write-like operation:

1. save raw command response in observations or test logs;
2. run a separate read command;
3. compare expected content/structure;
4. record whether backup/write/index side effects happened only after validation.

## Observations entry

Append one block per bug or behavior:

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

Stop and report if:

- a command is missing from help/registration;
- no safe test project is available;
- a write would target `vast_srv` or a real project;
- queue/proxy status hides an inner command failure;
- read-back verification fails.
