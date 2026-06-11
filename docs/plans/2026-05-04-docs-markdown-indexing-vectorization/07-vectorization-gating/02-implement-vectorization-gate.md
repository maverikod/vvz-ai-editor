# 02. Implement vectorization gate

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Prevent Markdown docs chunks from being embedded when `docs_indexing.vectorize=false`.

## Inputs

- [01-find-vectorization-selection.md](01-find-vectorization-selection.md)
- [../06-indexing-chunker-integration/02-persist-markdown-chunks.md](../06-indexing-chunker-integration/02-persist-markdown-chunks.md)

## Actions

1. Add a filter at the selected vectorization point.
2. If chunk belongs to Markdown docs and config says `vectorize=false`, skip embedding.
3. Do not assign `vector_id` for skipped docs chunks.
4. Do not update FAISS for skipped docs chunks.
5. Preserve existing behavior for code chunks.
6. Add tests for false and true modes.

## Output

Code changes plus notes in:

```text
revectorize-rebuild-behavior.md
vectorization-test-cases.md
```

## Verification

With `vectorize=false`, Markdown chunks exist but have no vector search entries.
