# Step 03 — `code_analysis/core/file_identity.py`

## Goal
Create a small shared helper module that centralizes file identity decisions currently duplicated across watcher, database CRUD, indexing, and diagnostics.

## Why this step exists
The current bug class came from local code treating `relative_path` as a cross-project identity. A weak model will likely repeat this mistake unless the rule is encoded in one place.

## New file to create
`code_analysis/core/file_identity.py`

## Current code checked before this step
Existing path helpers already exist and must be reused where applicable:

```text
code_analysis.core.path_normalization.normalize_path_simple
code_analysis.core.path_normalization.normalize_file_path
```

Do not invent a third incompatible normalization algorithm.

## Responsibilities of the new module
Implement pure helper functions only. No database writes in this module.

Required helpers:

```python
normalize_project_file_path(path: str | Path) -> str
```
Return normalized absolute path string using existing path normalization helpers.

```python
relative_path_for_project(abs_path: str | Path, project_root: str | Path) -> str
```
Return project-relative POSIX path or raise a clear exception if the file is outside project root.

```python
is_same_absolute_file(path_a: str | Path, path_b: str | Path) -> bool
```
Compare normalized absolute paths.

## Required identity classification
Do **not** implement an always-false helper as the main API. Instead define explicit cases.

Use an enum or constants similar to:

```python
class FileIdentityCase(Enum):
    SAME_PROJECT_SAME_ABSOLUTE_PATH = "same_project_same_absolute_path"
    DIFFERENT_PROJECT_SAME_ABSOLUTE_PATH = "different_project_same_absolute_path"
    DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY = "different_project_same_relative_path_only"
    UNRELATED = "unrelated"
```

Then implement:

```python
classify_file_identity_case(...)
```

It must classify:
- same project + same absolute path;
- different project + same absolute path;
- different project + same relative path only;
- unrelated files.

`DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY` is **not** a conflict. It is a safe, expected case for parallel project roots and allowlisted `.venv/site-packages` dependencies.

## Required changes in existing files
After creating the helper, update only one caller first:
- `code_analysis/core/database/files/crud.py`

Do not update every subsystem in the same patch. This step must stay small.

## Must not do
- Do not import database classes into `file_identity.py`.
- Do not call `clear_file_data` from this module.
- Do not encode allowlisted `.venv` rules here; that belongs to ignore policy.
- Do not migrate IDs.
- Do not create a helper that simply returns `False` without explaining identity cases.

## Tests to add
Create:
`tests/test_file_identity.py`

Cases:
1. Same absolute path with different syntactic form resolves equal.
2. Same relative path under different project roots is classified as `DIFFERENT_PROJECT_SAME_RELATIVE_PATH_ONLY`, not as a conflict.
3. File outside project root raises/returns explicit error.
4. Nested project roots with the same absolute file classify as `DIFFERENT_PROJECT_SAME_ABSOLUTE_PATH`.
5. Existing `tests/test_add_file_cross_project_path.py` still passes after using the helper.

## Verification
Run:

```text
python -m pytest tests/test_file_identity.py tests/test_add_file_cross_project_path.py -v
```

Then restart server and check:

```text
view_worker_logs(worker_type="indexing", log_levels=["ERROR", "WARNING", "CRITICAL"])
```

Expected:
- no regression in add_file behavior;
- no false relative-path conflicts.

## References
- Previous step: `01-code_analysis_core_database_files_crud.md`
- Ignore-policy is separate: `04-code_analysis_core_project_ignore_policy.md`
- Path-only comprehensive analysis cleanup: `02-code_analysis_commands_comprehensive_analysis_mcp_execute_single.md`
