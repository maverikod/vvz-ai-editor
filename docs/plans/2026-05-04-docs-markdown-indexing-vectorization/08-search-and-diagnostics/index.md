# 08. Search behavior and diagnostics

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../07-vectorization-gating/index.md](../07-vectorization-gating/index.md)
- Следующий шаг: [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)
- Наблюдения semantic search: [../01-current-state-inventory/semantic-search-observations.md](../01-current-state-inventory/semantic-search-observations.md)
- Наблюдения schema: [../01-current-state-inventory/schema-observations.md](../01-current-state-inventory/schema-observations.md)

## Цель

Проверить и задокументировать, как Markdown docs chunks участвуют в существующих search-командах, и добавить диагностику при необходимости.

## Входные материалы

- Vectorization gate: [../07-vectorization-gating/index.md](../07-vectorization-gating/index.md)
- Chunk mapping: [../06-indexing-chunker-integration/index.md](../06-indexing-chunker-integration/index.md)
- Semantic search observations: [../01-current-state-inventory/semantic-search-observations.md](../01-current-state-inventory/semantic-search-observations.md)
- Test plan: [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)

## Релевантные исходники

```text
code_analysis/commands/semantic_search_mcp.py
code_analysis/commands/search_mcp_commands.py
code_analysis/commands/search_mcp_commands_fulltext.py
code_analysis/commands/check_vectors_command.py
code_analysis/core/database/**
code_analysis/core/vectorization_worker_pkg/**
```

## Semantic search contract

Current `semantic_search` resolves FAISS `vector_id` results back through existing `code_chunks JOIN files` rows.

Therefore:

- Markdown docs can appear in `semantic_search` only when `vectorize=true` and chunks have valid `vector_id` / FAISS entries.
- Markdown docs must not appear in `semantic_search` when `vectorize=false`.
- No separate semantic docs search path should be introduced.

## Fulltext/BM25 behavior

Study and document whether fulltext/BM25 uses `code_chunks`, `files`, raw file content, or another index.

Required decision:

- If Markdown docs are chunked with `vectorize=false`, should fulltext search include them?
- If yes, verify through existing fulltext index update path.
- If no, document the limitation and add diagnostic output.

## Diagnostics tasks

- Add logs for docs indexing decisions:
  - disabled
  - non-md
  - outside roots
  - not included
  - excluded
  - indexed
  - chunked
  - skipped vectorization
  - vectorized
- Reuse existing worker logs where possible.
- Avoid noisy per-file logs unless debug mode is enabled or worker diagnostics already use per-file events.

## Optional command/API changes

Only add a diagnostic command if existing commands cannot answer docs indexing state.

Candidate diagnostics:

```text
docs_indexing_status
```

But prefer existing commands when possible:

```text
list_project_files
fulltext_search
semantic_search
check_vectors
get_worker_status
get_database_status
```

## Ожидаемые артефакты шага

```text
semantic-search-docs-behavior.md
fulltext-docs-behavior.md
diagnostics-design.md
diagnostics-command-decision.md
```

## Передача в следующие шаги

- Search expectations используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).
- User-facing behavior используется в [10-docs-and-rollout](../10-docs-and-rollout/index.md).

## Выход шага

- Documented search behavior for docs chunks.
- Diagnostics/logging strategy implemented or explicitly deemed unnecessary.
- No duplicate search implementation for docs.

## Проверка

- With `vectorize=false`, semantic search does not return `.md` docs.
- With `vectorize=true`, semantic search can return `.md` docs through existing result shape.
- Fulltext behavior is verified and documented.
- Logs explain why a Markdown file was skipped or processed.