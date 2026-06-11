# 06. Indexing and chunker integration

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../05-watcher-integration/index.md](../05-watcher-integration/index.md)
- Следующий шаг: [../07-vectorization-gating/index.md](../07-vectorization-gating/index.md)
- Наблюдения indexing: [../01-current-state-inventory/indexing-observations.md](../01-current-state-inventory/indexing-observations.md)
- Наблюдения chunker: [../01-current-state-inventory/chunker-observations.md](../01-current-state-inventory/chunker-observations.md)
- Наблюдения schema: [../01-current-state-inventory/schema-observations.md](../01-current-state-inventory/schema-observations.md)

## Цель

Провести eligible `.md` files через существующий file -> chunk pipeline и существующий chunker file API.

## Входные материалы

- Watcher output: [../05-watcher-integration/index.md](../05-watcher-integration/index.md)
- Schema observations: [../01-current-state-inventory/schema-observations.md](../01-current-state-inventory/schema-observations.md)
- Chunker observations: [../01-current-state-inventory/chunker-observations.md](../01-current-state-inventory/chunker-observations.md)
- Vectorization gate target: [../07-vectorization-gating/index.md](../07-vectorization-gating/index.md)

## Релевантные исходники

```text
code_analysis/core/indexing_worker_pkg/**
code_analysis/core/vectorization_worker_pkg/chunking.py
code_analysis/core/vectorization_worker_pkg/file_batch_packing.py
code_analysis/core/vectorization_worker_pkg/batch_processor.py
code_analysis/core/svo_client_manager.py
code_analysis/core/svo_client_manager_chunker.py
code_analysis/core/database/**
code_analysis/core/database_client/objects/vector_chunk.py
```

## Главное правило

Не реализовывать отдельный Markdown splitter, если существующий chunker file API может принять `.md` файл.

## Задачи

- Найти существующий контракт file-based chunking.
- Проверить, поддерживает ли chunker `.md` input.
- Если поддерживает — использовать его напрямую.
- Если не поддерживает — зафиксировать ограничение и создать follow-up task для chunker owner.
- Сохранять Markdown chunks в существующую `code_chunks` структуру.
- Не создавать `docs_chunks` или `docs_vectors`.
- Определить и документировать допустимый `chunk_type` для Markdown.
- Проверить, что `chunk_text`, `line`, `token_count`, `chunk_uuid`, `file_id`, `project_id` заполняются совместимо с текущими search commands.

## Expected flow

```text
eligible .md file
  -> existing files row
  -> existing chunker file command/API
  -> chunk results
  -> existing code_chunks insert/update path
  -> optional vectorization gate
```

## Ожидаемые артефакты шага

```text
chunker-file-api-contract.md
markdown-chunk-type-decision.md
code-chunks-mapping.md
indexing-change-notes.md
```

## Передача в следующие шаги

- `code_chunks` mapping используется в [07-vectorization-gating](../07-vectorization-gating/index.md).
- Chunk/search fields используются в [08-search-and-diagnostics](../08-search-and-diagnostics/index.md).
- Test cases используются в [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).

## Выход шага

- `.md` files become rows in `files` and `code_chunks` using existing pipeline.
- Chunker file API use is documented in observations.
- No parallel docs-specific persistence is introduced.

## Проверка

- Test `.md` file creates `files` row.
- Test `.md` file creates `code_chunks` rows.
- Chunk rows include expected `file_path`, `chunk_text`, `line`.
- Non-md files do not enter this path.
