# Rollout notes — Markdown docs indexing

**Родительский шаг:** [index.md](index.md).

Сводный документ для читателей: [../00-index/rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md).

## Порядок выката

1. Убедиться, что в основном `config.json` (или генерируемом конфиге) присутствует секция `code_analysis.docs_indexing` с безопасными defaults (`enabled=false`, `vectorize=false`) или секция опущена.
2. Прогнать тесты валидатора/генератора конфигурации.
3. На отдельном тестовом проекте: watcher + indexing с `enabled=true`, затем сценарии `vectorize=false` и `vectorize=true`.
4. MCP-верификация по списку [09-tests-and-mcp-verification/index.md](../09-tests-and-mcp-verification/index.md); результаты зафиксировать в `mcp-verification-results.md`.
5. Обновить пользовательскую документацию ([documentation-change-notes.md](documentation-change-notes.md)).
6. Зафиксировать ограничения в [known-limitations.md](../09-tests-and-mcp-verification/known-limitations.md).
7. **Перезапуск сервера** после изменений конфига/кода, чтобы демон подхватил настройки.

## Ожидаемые проверки поведения

- Только `.md` в scope; non-md не идут путём docs indexing.
- `enabled=false`: markdown не обрабатывается фичей; кодовый watcher без изменений.
- `enabled=true`, `vectorize=false`: `files`/`code_chunks` для доков; fulltext по ТЗ должен находить совпадения; `semantic_search` не возвращает доки.
- `enabled=true`, `vectorize=true`: векторы/FAISS для доковых чанков; `semantic_search` может вернуть доки при успешном пайплайне.

## Артефакты шага

- [documentation-change-notes.md](documentation-change-notes.md)
- [compatibility-notes.md](compatibility-notes.md)
- [final-implementation-report.md](final-implementation-report.md)
