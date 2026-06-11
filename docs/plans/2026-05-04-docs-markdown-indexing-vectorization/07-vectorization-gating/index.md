# 07. Vectorization gating

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../06-indexing-chunker-integration/index.md](../06-indexing-chunker-integration/index.md)
- Следующий шаг: [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)
- Наблюдения vectorization: [../01-current-state-inventory/vectorization-observations.md](../01-current-state-inventory/vectorization-observations.md)
- Наблюдения schema: [../01-current-state-inventory/schema-observations.md](../01-current-state-inventory/schema-observations.md)

## Цель

Реализовать строгий gate для Markdown docs vectorization.

## Входные материалы

- Chunk persistence contract: [../06-indexing-chunker-integration/index.md](../06-indexing-chunker-integration/index.md)
- Config contract: [../02-config-contract/index.md](../02-config-contract/index.md)
- Vectorization observations: [../01-current-state-inventory/vectorization-observations.md](../01-current-state-inventory/vectorization-observations.md)
- Semantic search target behavior: [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)

## Релевантные исходники

```text
code_analysis/core/vectorization_worker_pkg/**
code_analysis/core/indexing_worker_pkg/vectorize_after_index.py
code_analysis/core/faiss_manager.py
code_analysis/core/database/files/update_vectorize.py
code_analysis/commands/vector_commands/revectorize.py
code_analysis/commands/vector_commands/rebuild_faiss.py
code_analysis/commands/semantic_search_mcp.py
```

## Главное правило

`code_analysis.docs_indexing.vectorize=false` по умолчанию и означает: Markdown chunks не получают embeddings и не попадают в FAISS.

## Задачи

- Найти место, где chunks выбираются для vectorization.
- Добавить фильтр: Markdown docs chunks eligible только при `docs_indexing.vectorize=true`.
- При `vectorize=false` не запрашивать embeddings для Markdown chunks.
- При `vectorize=false` не назначать `vector_id` Markdown chunks.
- При `vectorize=false` не писать Markdown vectors в FAISS.
- При `vectorize=true` использовать существующий embedding worker и FAISS flow.
- Проверить поведение `revectorize` и `rebuild_faiss` для Markdown chunks.

## Expected behavior

```text
enabled=false
  -> docs ignored

enabled=true, vectorize=false
  -> docs chunked if indexing enabled
  -> no embeddings
  -> no FAISS entries
  -> semantic_search does not return docs

enabled=true, vectorize=true
  -> docs chunked
  -> embeddings created
  -> FAISS entries created
  -> semantic_search may return docs
```

## Ожидаемые артефакты шага

```text
vectorization-gate-design.md
revectorize-rebuild-behavior.md
vectorization-test-cases.md
```

## Передача в следующие шаги

- Search expectations используются в [08-search-and-diagnostics](../08-search-and-diagnostics/index.md).
- Test cases используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).
- Rollout notes используются в [10-docs-and-rollout](../10-docs-and-rollout/index.md).

## Выход шага

- Vectorization gate implemented.
- Revectorize/rebuild behavior documented.
- Tests cover both vectorize states.

## Проверка

- With `vectorize=false`, DB chunks exist but no vector entries exist for Markdown docs.
- With `vectorize=false`, `semantic_search` does not return Markdown docs.
- With `vectorize=true`, vector entries are created by existing worker.
- With `vectorize=true`, `semantic_search` can return Markdown docs.
