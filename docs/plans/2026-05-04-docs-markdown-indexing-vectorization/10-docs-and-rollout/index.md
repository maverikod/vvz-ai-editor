# 10. Documentation and rollout

## Навигация

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План: [../00-index/index.md](../00-index/index.md)
- Предыдущий шаг: [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)
- Главный индекс: [../00-index/index.md](../00-index/index.md)
- Результаты MCP verification: [../09-tests-and-mcp-verification/mcp-verification-results.md](../09-tests-and-mcp-verification/mcp-verification-results.md)
- Known limitations: [../09-tests-and-mcp-verification/known-limitations.md](../09-tests-and-mcp-verification/known-limitations.md)
- Rollout и совместимость (сводка): [../00-index/rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md)

## Цель

Обновить пользовательскую и инженерную документацию после реализации Markdown docs indexing.

## Входные материалы

- Основное ТЗ: [../01-task-spec.md](../01-task-spec.md)
- План реализации: [../00-index/index.md](../00-index/index.md)
- Search behavior: [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md)
- Test/MCP results: [../09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md)

## Документация для обновления

```text
docs/METADATA_SCHEMA_STANDARD.md
docs/COMMANDS_GUIDE.md
docs/PROJECT_RULES.md
docs/commands/*/README.md, если появляются новые или изменённые команды
```

## Релевантные исходники

```text
code_analysis/core/config_generator.py
code_analysis/core/config_validator/**
code_analysis/core/file_watcher*
code_analysis/core/file_watcher_pkg/**
code_analysis/core/indexing_worker_pkg/**
code_analysis/core/vectorization_worker_pkg/**
code_analysis/commands/semantic_search_mcp.py
```

## Что описать

- Docs indexing поддерживает только `.md` файлы.
- Docs indexing disabled by default.
- Docs vectorization disabled by default.
- Настройки находятся в main config: `code_analysis.docs_indexing`.
- `projectid` не используется для этих настроек.
- Docs chunks используют существующий `files` / `code_chunks` / optional vector pipeline.
- `semantic_search` возвращает docs только если `vectorize=true` и vector pipeline успешно создал FAISS entries.
- Non-md files are out of scope.

## Rollout steps

1. Добавить config section with safe defaults.
2. Запустить validator tests.
3. Запустить generator tests.
4. Запустить watcher/indexing tests на dedicated test project.
5. Запустить vectorization tests отдельно для `vectorize=false` и `vectorize=true`.
6. Выполнить MCP verification из [09-tests-and-mcp-verification](../09-tests-and-mcp-verification/index.md).
7. Обновить docs.
8. Зафиксировать known limitations.
9. Сообщить пользователю, что нужен restart сервера для применения config/code changes.

## Compatibility

- Existing configs without `docs_indexing` must remain valid.
- Existing code indexing behavior must not change when docs indexing disabled.
- Existing `semantic_search` result shape must not change.
- Existing DB tables must be reused, not replaced by docs-specific tables.

## Ожидаемые артефакты шага

```text
documentation-change-notes.md
rollout-notes.md
compatibility-notes.md
final-implementation-report.md
```

## Выход шага

- Updated documentation.
- Rollout notes.
- Compatibility notes.
- Known limitations.
- Final implementation report with MCP command evidence.

## Проверка

- Docs clearly state Markdown-only behavior.
- Docs clearly state disabled defaults.
- Docs clearly state config location.
- Docs reference existing chunk/vector pipeline.
- Final report includes MCP command evidence from [../09-tests-and-mcp-verification/mcp-verification-results.md](../09-tests-and-mcp-verification/mcp-verification-results.md).