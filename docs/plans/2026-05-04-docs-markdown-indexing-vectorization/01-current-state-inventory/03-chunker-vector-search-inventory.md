# 03. Chunker, vectorization, and search inventory

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

Read-only task. Do not edit code.

## Goal

Describe how chunks are created, vectorized, and returned by search commands.

## Inspect

- `code_analysis/core/svo_client_manager_chunker.py`
- `code_analysis/core/vectorization_worker_pkg`
- `code_analysis/commands/semantic_search_mcp.py`
- `code_analysis/commands/check_vectors_command.py`

## Actions

1. Find the existing file-based chunker call.
2. Record whether file suffix is checked before chunking.
3. Find how chunks get embeddings.
4. Find how vector ids are connected to search results.
5. Record what must be true for Markdown docs to appear in semantic search.

## Output files

Write findings to:

```text
chunker-observations.md
vectorization-observations.md
semantic-search-observations.md
```

## Verification

Use only read commands. Mention inspected file paths and function names.
