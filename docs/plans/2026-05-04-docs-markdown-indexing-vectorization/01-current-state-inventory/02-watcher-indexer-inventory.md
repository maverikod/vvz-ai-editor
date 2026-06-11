# 02. Watcher and indexer inventory

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

Read-only task. Do not edit code.

## Goal

Describe how the current watcher discovers files and how indexing work is scheduled.

## Inspect

- `code_analysis/core/file_watcher_pkg`
- `code_analysis/core/indexing_worker_pkg`
- `code_analysis/core/config.py`

## Actions

1. Find how projects and project roots are discovered.
2. Find how ignored paths are filtered.
3. Find how new or changed files are detected.
4. Find how indexing work is queued or marked.
5. Record where docs eligibility should later be inserted.

## Output file

Write findings to:

```text
watcher-observations.md
indexing-observations.md
```

## Verification

Use only read commands. Mention inspected file paths and function names.
