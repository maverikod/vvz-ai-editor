# 01. Database schema inventory

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

Read-only task. Do not edit code.

## Goal

Describe how current storage represents project files, text chunks, vector ids, and search mapping.

## Inspect

- `code_analysis/core/database`
- `code_analysis/core/database_client/objects/vector_chunk.py`
- `code_analysis/core/faiss_manager.py`

## Actions

1. Find where file records are defined.
2. Find where chunk records are defined.
3. Find fields used by vector search.
4. Record fields required for a Markdown chunk to work with existing search.
5. Record any uncertainty as open questions.

## Output file

Write findings to:

```text
schema-observations.md
```

## Required sections

- Files storage
- Chunk storage
- Vector mapping
- Required Markdown chunk fields
- Open questions

## Verification

Use only read commands. Mention inspected file paths in the output.
