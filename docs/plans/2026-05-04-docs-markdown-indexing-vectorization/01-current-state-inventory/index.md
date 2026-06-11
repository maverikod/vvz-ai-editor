# 01. Current state inventory

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../00-index/index.md](../00-index/index.md)
- Следующий шаг: [../02-config-contract/index.md](../02-config-contract/index.md)
- Итоговые проверки: [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)

## Цель

Перед изменениями зафиксировать фактическое состояние существующего pipeline: БД, file watcher, indexing worker, chunker integration, vectorization worker и `semantic_search`.

## Исходные файлы для анализа

БД и storage:

```text
code_analysis/core/database/**
code_analysis/core/database_client/objects/vector_chunk.py
code_analysis/core/faiss_manager.py
```

Watcher/indexing/vectorization:

```text
code_analysis/core/file_watcher*
code_analysis/core/file_watcher_pkg/**
code_analysis/core/indexing_worker_pkg/**
code_analysis/core/vectorization_worker_pkg/**
```

Chunker/SVO/search:

```text
code_analysis/core/svo_client_manager.py
code_analysis/core/svo_client_manager_chunker.py
code_analysis/core/svo_client_manager_embedding.py
code_analysis/core/svo_client_manager_config.py
code_analysis/commands/semantic_search_mcp.py
```

## Задачи

- Изучить схему БД и драйверные абстракции для `files`, `code_chunks`, vector ids, FAISS mapping.
- Изучить file watcher: обнаружение проектов, чтение `projectid`, ignore rules, detection of new/changed/deleted files.
- Изучить indexing worker: как файл становится chunks.
- Изучить chunker file API: как текущий pipeline отправляет файл в chunker.
- Изучить vectorization worker: как chunks получают embeddings и `vector_id`.
- Изучить `semantic_search`: какие поля он читает из `code_chunks JOIN files`.

## Ожидаемые артефакты шага

Создать наблюдения в этом же каталоге:

```text
schema-observations.md
watcher-observations.md
indexing-observations.md
chunker-observations.md
vectorization-observations.md
semantic-search-observations.md
```

## Передача в следующие шаги

- Результаты `schema-observations.md` используются в [06-indexing-chunker-integration](../06-indexing-chunker-integration/index.md) и [07-vectorization-gating](../07-vectorization-gating/index.md).
- Результаты `watcher-observations.md` используются в [05-watcher-integration](../05-watcher-integration/index.md).
- Результаты `semantic-search-observations.md` используются в [08-search-and-diagnostics](../08-search-and-diagnostics/index.md).

## Проверка

- Все наблюдения основаны на реальном коде и MCP-read командах.
- В наблюдениях явно указано, какие таблицы/поля обязательны для Markdown chunks.
- Зафиксировано, как `semantic_search` будет видеть `.md` chunks при `vectorize=true`.
