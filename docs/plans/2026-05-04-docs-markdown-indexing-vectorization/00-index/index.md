# План реализации: Markdown docs indexing and optional vectorization

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- Текущий индекс: [00-index/index.md](index.md)
- Первый шаг: [../01-current-state-inventory/index.md](../01-current-state-inventory/index.md)
- Общий стандарт metadata/schema: [../../METADATA_SCHEMA_STANDARD.md](../../METADATA_SCHEMA_STANDARD.md)

## Назначение

Этот индекс описывает глобальные шаги реализации задачи из `../01-task-spec.md`.

Каждый шаг вынесен в отдельный подкаталог с собственным `index.md`. Каждый `index.md` должен быть самодостаточным: содержать ссылки на входные документы, соседние шаги, исходные файлы и ожидаемые артефакты.

## Порядок выполнения

1. [01-current-state-inventory](../01-current-state-inventory/index.md) — зафиксировать текущее состояние БД, watcher, indexer, vectorizer, chunker и `semantic_search`.
2. [02-config-contract](../02-config-contract/index.md) — спроектировать и закрепить контракт `code_analysis.docs_indexing`.
3. [03-config-validator-generator](../03-config-validator-generator/index.md) — добавить поддержку секции в validator/generator/CLI.
4. [04-markdown-eligibility](../04-markdown-eligibility/index.md) — реализовать Markdown-only фильтрацию include/exclude.
5. [05-watcher-integration](../05-watcher-integration/index.md) — подключить docs-файлы к file watcher без изменения поведения по умолчанию.
6. [06-indexing-chunker-integration](../06-indexing-chunker-integration/index.md) — провести `.md` через существующий file -> chunk pipeline и chunker file API.
7. [07-vectorization-gating](../07-vectorization-gating/index.md) — реализовать `vectorize=false` по умолчанию и optional vectorization.
8. [08-search-and-diagnostics](../08-search-and-diagnostics/index.md) — проверить fulltext/semantic behavior и добавить диагностику при необходимости.
9. [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md) — выполнить unit/integration/MCP-level проверки.
10. [10-docs-and-rollout](../10-docs-and-rollout/index.md) — обновить документацию и зафиксировать rollout/compatibility.

Rollout и совместимость (сводка): [rollout-and-compatibility.md](rollout-and-compatibility.md).

## Ключевые ограничения

- Только `.md` файлы.
- `enabled=false` по умолчанию.
- `vectorize=false` по умолчанию.
- Настройки только в основном config, не в `projectid`.
- Не создавать отдельные `docs_chunks` / `docs_vectors`.
- Не редактировать `.venv`, `site-packages`, установленные зависимости.

## Definition of Done

Блок считается готовым только когда:

- конфиг валидируется;
- генератор создаёт безопасные defaults;
- `.md` eligibility работает по include/exclude;
- watcher не меняет поведение при disabled config;
- индексирование `.md` идёт через существующий chunk pipeline;
- `vectorize=false` не создаёт embeddings/FAISS;
- `vectorize=true` создаёт vector entries через существующий worker;
- результат проверен отдельными read/search/MCP-командами.