# 01. Document semantic search behavior

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Document how Markdown chunks should appear or not appear in `semantic_search`.

## Inspect

- `code_analysis/commands/semantic_search_mcp.py`
- `code_analysis/core/faiss_manager.py`
- `code_analysis/core/database`

## Actions

1. Confirm that semantic search reads FAISS vector ids.
2. Confirm that results are joined back to file and chunk records.
3. State that Markdown docs appear only when vectorized.
4. State that Markdown docs must not appear when `vectorize=false`.
5. Record the exact result fields that should be preserved.

## Output

Create or update:

```text
semantic-search-docs-behavior.md
```

## Verification

Output must mention `code_chunks`, `files`, `vector_id`, and `chunk_text`.
