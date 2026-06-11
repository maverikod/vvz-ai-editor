# 01. Locate watcher config entry

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Find the safest point where the file watcher can read `code_analysis.docs_indexing`.

## Inspect

- `code_analysis/core/file_watcher_pkg`
- `code_analysis/core/config.py`
- `code_analysis/core/config_server.py`

## Actions

1. Find watcher initialization code.
2. Find how current config is passed to watcher.
3. Find existing ignore/filter code.
4. Record the exact function where docs eligibility should be called.
5. Do not change behavior in this task unless the entry point is obvious and small.

## Output

Create or update:

```text
watcher-change-notes.md
```

## Verification

Use read-only MCP commands first. Mention file paths and function names.
