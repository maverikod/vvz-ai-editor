# Issue: Indexing worker fails to chunk docs/yaml files — wrong path resolution

## Summary

Docs and YAML files from non-`code_analysis` projects (e.g. `ai_editor`) are
permanently stuck in `needing_chunking`. The chunking worker calls
`resolve_indexed_file_path` which tries three path candidates in order;
candidate 1 is correct but **the required columns are missing from the SELECT**
that feeds the chunking loop, so it silently falls through to candidate 3
(stored `files.path`) — which contains only a project-relative path, not an
absolute one. `Path(rel_path).is_file()` → False → worker skips the file
every cycle forever.

## Observed symptom

Indexing worker log (repeated every cycle, hundreds of times):
```
WARNING - File /home/vasilyvz/projects/tools/code_analysis/docs/plans/ai_editor/audit_report.md
          is outside root /home/vasilyvz/projects/tools/ai_editor, using absolute path
WARNING - handler_error=File does not exist
```

The path `…/code_analysis/docs/plans/ai_editor/…` is wrong. The correct path
is `…/ai_editor/docs/plans/ai_editor/…`.

`get_database_status` for project `ai_editor` shows a stable `needing_chunking`
count that never decreases despite repeated cycle passes.

## Root cause — code path analysis

### Step 1: `get_files_needing_chunking` (query.py:47)

Returns rows with only these columns:
```sql
SELECT DISTINCT f.id, f.project_id, f.path, f.has_docstring
FROM files f
WHERE …
```

**Missing columns:** `f.relative_path`, and joined `watch_dir_paths.absolute_path`
(as `watch_absolute_path`), `projects.name` (as `project_name`),
`projects.root_path` (as `project_root_path`).

### Step 2: `_request_chunking_for_files` (chunking.py:28)

Passes each `file_record` dict from Step 1 directly to:
```python
file_path_obj = resolve_indexed_file_path(file_record)
```

### Step 3: `resolve_indexed_file_path` (resolve_indexed_file_path.py)

Tries three candidates **in order**:
```python
# Candidate 1 — correct formula per architecture:
watch_abs / project_name / relative_path
# → requires watch_absolute_path, project_name, relative_path — ALL MISSING

# Candidate 2:
root_path / relative_path
# → requires project_root_path, relative_path — ALL MISSING

# Candidate 3 (legacy fallback):
Path(files.path)
# → present, but files.path stores a project-relative string like
#   "docs/plans/ai_editor/audit_report.md" (not absolute)
```

Since candidates 1 and 2 are always skipped (missing data), candidate 3 runs:
```python
Path("docs/plans/ai_editor/audit_report.md").is_file()
# → resolves relative to CWD = /home/vasilyvz/projects/tools/code_analysis
# → /home/vasilyvz/projects/tools/code_analysis/docs/plans/ai_editor/audit_report.md
# → does not exist → None
```

Worker logs `"no file on disk after resolving path"` and skips. File stays in
`needing_chunking` forever.

### Why `analyze_file` had the same symptom

`analyze_file` (update_indexes_analyzer.py:246) also called `file_path.resolve()`
on a relative path, resolving against CWD instead of `root_path`. That produced
the same wrong prefix in the log. This is a separate but related path-resolution
bug (also to be fixed, see fix sketch below).

## Correct path formula (per architecture)

From `resolve_indexed_file_path.py` docstring and `list_watch_dirs` /
`list_projects` data:
```
absolute_path = watch_dir.absolute_path / project.name / file.relative_path
             = /home/vasilyvz/projects/tools / ai_editor / docs/plans/ai_editor/audit_report.md
             = /home/vasilyvz/projects/tools/ai_editor/docs/plans/ai_editor/audit_report.md  ✓
```

All three pieces are available in the DB; they just need to be JOIN-ed into the
rows fetched by `get_files_needing_chunking`.

## Fix

### Fix 1 — `get_files_needing_chunking` (query.py)

Join `projects` and `watch_dir_paths` and include the required columns:

```python
return cast(
    List[Dict[str, Any]],
    self._fetchall(
        f"""
            SELECT DISTINCT
                f.id,
                f.project_id,
                f.path,
                f.relative_path,
                f.has_docstring,
                p.root_path         AS project_root_path,
                p.name              AS project_name,
                wd.absolute_path    AS watch_absolute_path
            FROM files f
            JOIN projects p ON p.id = f.project_id
            LEFT JOIN watch_dir_paths wd ON wd.id = p.watch_dir_id
            WHERE f.project_id = ?
            AND {WHERE_FILES_ACTIVE_F}
            AND (
                {WHERE_HAS_DOCSTRING_F}
                OR EXISTS (
                    SELECT 1 FROM classes c
                    WHERE c.file_id = f.id
                    AND c.docstring IS NOT NULL AND c.docstring != ''
                )
                OR EXISTS (
                    SELECT 1 FROM functions fn
                    WHERE fn.file_id = f.id
                    AND fn.docstring IS NOT NULL AND fn.docstring != ''
                )
                OR EXISTS (
                    SELECT 1 FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    WHERE c.file_id = f.id
                    AND m.docstring IS NOT NULL AND m.docstring != ''
                )
            )
            AND (f.needs_chunking = 1 OR NOT EXISTS (
                SELECT 1 FROM code_chunks cc
                WHERE cc.file_id = f.id
            ))
            ORDER BY f.updated_at DESC
            LIMIT ?
            """,
        (project_id, limit),
    ),
)
```

With these columns present, `resolve_indexed_file_path` will match candidate 1
(`watch_absolute_path / project_name / relative_path`) and return the correct
absolute path.

### Fix 2 — `analyze_file` (update_indexes_analyzer.py:246)

The function receives `file_path: Path` and `root_path: Path`. When called from
`code_mapper_mcp_command.py` for **Python files**, `collect_python_files_for_indexing`
returns absolute paths, so `file_path.resolve()` happens to work.

However callers that pass relative paths (e.g. from the DB `files.path` column)
will resolve against CWD. The safe fix: always build the absolute path
explicitly from `root_path` when `file_path` is not already absolute:

```python
# line 246-247 — replace:
file_path = file_path.resolve()
root_path = root_path.resolve()

# with:
root_path = root_path.resolve()
if not file_path.is_absolute():
    file_path = (root_path / file_path).resolve()
else:
    file_path = file_path.resolve()
```

This is a defensive fix; Fix 1 is the primary fix for the chunking problem.

## Affected files

| File | Change |
|---|---|
| `code_analysis/core/database/files/query.py` | `get_files_needing_chunking`: add JOIN + missing columns |
| `code_analysis/commands/update_indexes_analyzer.py` | `analyze_file`: safe path build from root_path |

## Verification

After fix, `get_database_status` for project `ai_editor` should show
`needing_chunking` decreasing each cycle until 0. The log warning
`"File … is outside root …"` must not appear for files that belong to the
project being chunked.

Test: create a new `.md` file in any non-`code_analysis` project, wait one
cycle, verify `needing_chunking` drops by 1 and the file gets chunks in
`code_chunks`.
