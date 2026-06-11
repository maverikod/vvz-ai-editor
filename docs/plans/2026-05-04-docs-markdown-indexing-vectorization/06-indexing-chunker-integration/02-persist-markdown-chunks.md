# 02. Persist Markdown chunks in existing structures

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Store Markdown chunks through the existing file and chunk persistence path.

## Inputs

- [01-document-chunker-file-api.md](01-document-chunker-file-api.md)
- [../01-current-state-inventory/schema-observations.md](../01-current-state-inventory/schema-observations.md)

## Actions

1. Find current code that inserts or updates file records.
2. Find current code that inserts or updates chunk records.
3. Reuse that path for eligible `.md` files.
4. Do not create docs-specific tables.
5. Choose a safe `chunk_type` only after checking existing consumers.
6. Record required mapping fields.

## Output

Create or update:

```text
code-chunks-mapping.md
markdown-chunk-type-decision.md
```

## Verification

A test Markdown file must create normal file and chunk records.
