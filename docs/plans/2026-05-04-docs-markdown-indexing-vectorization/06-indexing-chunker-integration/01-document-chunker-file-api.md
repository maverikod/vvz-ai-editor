# 01. Document chunker file API

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Find and document the existing file-based chunker API used by the current pipeline.

## Inspect

- `code_analysis/core/svo_client_manager_chunker.py`
- `code_analysis/core/svo_client_manager.py`
- `code_analysis/core/vectorization_worker_pkg/chunking.py`

## Actions

1. Find the function that sends a file or file content to the chunker.
2. Record required input fields.
3. Record returned chunk fields.
4. Check whether `.md` is accepted or blocked.
5. Do not implement a new splitter in this task.

## Output

Create or update:

```text
chunker-file-api-contract.md
```

## Verification

Use read-only commands and record exact file paths and function names.
