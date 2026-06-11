# 02. Document fulltext behavior and diagnostics

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Decide and document how indexed Markdown chunks interact with fulltext search and worker diagnostics.

## Inspect

- `code_analysis/commands/search_mcp_commands_fulltext.py`
- `code_analysis/commands/search_mcp_commands.py`
- `code_analysis/core/indexing_worker_pkg`
- `code_analysis/core/vectorization_worker_pkg`

## Actions

1. Find what storage fulltext search reads.
2. Decide whether Markdown chunks are searchable when `vectorize=false`.
3. Record the decision and exact reason.
4. List diagnostics needed for skipped and processed Markdown files.
5. Prefer existing logs and commands before adding new commands.

## Output

Create or update:

```text
fulltext-docs-behavior.md
diagnostics-design.md
```

## Verification

The output must say whether fulltext can see Markdown chunks without vectorization.