# Atomic step: schema observations

## Parent step

01-current-state-inventory

## Code file / area

```text
code_analysis/core/database/**
code_analysis/core/database/schema*
code_analysis/core/database/files/*
code_analysis/core/database/code_chunk*
code_analysis/core/database_client/objects/vector_chunk.py
code_analysis/core/faiss_manager.py
```

## Atomic goal

Inspect and document the current database schema behavior for `files`, `code_chunks`, vector ids, FAISS mapping, project_id linkage, deleted flags, file path identity, `chunk_uuid`, `chunk_type`, `chunk_text`, `line`, `token_count`, and `bm25_score`.

## Required output

Create or update:

```text
docs/plans/2026-05-04-docs-markdown-indexing-vectorization/01-current-state-inventory/schema-observations.md
```

## Constraints

Do not change implementation code in this atomic step. Record actual behavior only.
