# Documentation change notes (шаг 10)

**Цель:** перечень пользовательских и инженерных документов, которые должны отражать фичу `docs_indexing` после реализации.

## Обязательные утверждения в тексте

1. Индексация доков — **только Markdown** (`.md`).
2. **`enabled=false`** и **`vectorize=false`** по умолчанию.
3. Секция конфига: **`code_analysis.docs_indexing`** в основном server config; **`projectid` не используется**.
4. Чанки и векторы — существующие **`files` / `code_chunks`** и опциональный векторный пайплайн; отдельного стека хранения для доков нет.
5. **`semantic_search`** возвращает доки только при **`vectorize=true`** и успешном создании FAISS/`vector_id` для доковых чанков.
6. Non-markdown форматы вне scope этой фичи.

## Файлы для проверки/обновления (из [index.md](index.md))

- [docs/METADATA_SCHEMA_STANDARD.md](../../../METADATA_SCHEMA_STANDARD.md) — если появились новые/изменённые MCP-команды или метаданные, затрагивающие поиск/индексацию доков.
- [docs/COMMANDS_GUIDE.md](../../../COMMANDS_GUIDE.md) — кратко: конфиг, defaults, связь fulltext vs semantic для `.md`.
- [docs/PROJECT_RULES.md](../../../PROJECT_RULES.md) — при необходимости правило про расположение доков и ограничение настройки только main config.
- [docs/commands/*/README.md](../../../commands/) — при изменении или добавлении команд, видимых пользователю.

## Плановые артефакты шага 08 (при наличии)

Сверка с фактическим поведением: `semantic-search-docs-behavior.md`, `fulltext-docs-behavior.md`, диагностика — по [../08-search-and-diagnostics/index.md](../08-search-and-diagnostics/index.md).

## Этот каталог

- [rollout-notes.md](rollout-notes.md), [compatibility-notes.md](compatibility-notes.md), [final-implementation-report.md](final-implementation-report.md)
- Сводка rollout: [../00-index/rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md)
