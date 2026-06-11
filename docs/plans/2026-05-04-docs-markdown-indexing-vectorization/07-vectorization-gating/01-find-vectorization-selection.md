# 01. Find vectorization selection point

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Find where chunks are selected for embedding and FAISS insertion.

## Inspect

- `code_analysis/core/vectorization_worker_pkg`
- `code_analysis/core/indexing_worker_pkg/vectorize_after_index.py`
- `code_analysis/core/database/files/update_vectorize.py`

## Actions

1. Find the query or function that selects chunks for vectorization.
2. Find where `vector_id` is assigned.
3. Find where FAISS is updated.
4. Record where Markdown docs should be filtered when `vectorize=false`.
5. Do not change behavior in this task unless the insertion point is trivial.

## Output

Create or update:

```text
vectorization-gate-design.md
```

## Verification

Use read-only commands first. Mention file paths and function names.
