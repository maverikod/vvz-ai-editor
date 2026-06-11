# Final implementation report — Markdown docs indexing

**Шаг:** [index.md](index.md).  
**Статус черновика:** отчёт заполняется после завершения реализации и MCP-верификации.

## 1. Конфигурация

- Секция `code_analysis.docs_indexing`: поля `enabled`, `vectorize`, `roots`, `include`, `exclude`; defaults как в [01-task-spec.md](../01-task-spec.md).
- Валидатор: опциональная секция; строгие правила для путей и Markdown-only include.
- Генератор/CLI: аргументы и явные defaults без включения фичи по умолчанию.

## 2. Пайплайн

- Eligibility: `.md`, относительные пути, exclude над include.
- Watcher: подключение только при `enabled=true`; иначе без изменений для кода.
- Indexing/chunker: существующий file API → `code_chunks`, тип `DocBlock`.
- Vectorization gate: при `vectorize=false` нет embeddings/FAISS для доков; при `true` — существующий worker.

## 3. Поиск

- Fulltext: целевое поведение по ТЗ — совпадения по проиндексированным Markdown при `vectorize=false` (проверка — шаг 08 и тесты).
- Semantic: доки в выдаче только при `vectorize=true` и валидных `vector_id`.

## 4. Совместимость

См. [compatibility-notes.md](compatibility-notes.md) и [../00-index/rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md).

## 5. Известные ограничения

См. [../09-tests-and-mcp-verification/known-limitations.md](../09-tests-and-mcp-verification/known-limitations.md).

## 6. MCP verification — доказательства

**Ожидаемый источник правды:** [../09-tests-and-mcp-verification/mcp-verification-results.md](../09-tests-and-mcp-verification/mcp-verification-results.md).

До заполнения этого файла зафиксируйте для каждой проверки:

- команду и параметры;
- ожидаемый результат;
- фактический результат (кратко);
- вложенный успех (`result.command.result.success` для очередей), если применимо.

Команды-кандидаты из шага 09: `list_projects`, `list_project_files`, `get_database_status`, `get_worker_status`, `fulltext_search`, `semantic_search`, `check_vectors`, `queue_get_job_status`.

## 7. Перезапуск

После выката конфигурации и бинарных/кодовых изменений — **restart** демона code analysis server.
