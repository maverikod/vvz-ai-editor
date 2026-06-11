# Known limitations — Markdown docs indexing

**Шаг:** [index.md](index.md).  
**Потребители:** [../10-docs-and-rollout/index.md](../10-docs-and-rollout/index.md), [../00-index/rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md).

Краткий список ограничений и краевых случаев (по ТЗ, индексу плана и шагам 05–09):

- **Только `.md`:** `.txt`, `.rst`, `.adoc`, JSON/YAML, код и прочие расширения не индексируются этой фичей.
- **Семантика паттернов `include`/`exclude`:** контракт — fnmatch/glob-стиль относительно корня проекта; поведение `**` и граничные случаи (например, покрыт ли `docs/guide.md` шаблоном `docs/**/*.md`) должны совпадать между валидатором и runtime; при расхождении сверять тесты и [02-config-contract](../02-config-contract/index.md).
- **Fulltext vs чанки:** keyword слой завязан на `code_content`/FTS; полнотекстовая выдача и фильтры (в т.ч. по `entity_type` или аналогам) могут отражать исторически «кодовые» категории — уточнять по фактической схеме и шагу 08.
- **Semantic только с векторами:** без `vectorize=true` и FAISS/`vector_id` доки в `semantic_search` не ожидаются, даже если чанки в БД есть.
- **MCP и очереди:** для фоновых задач не полагаться только на `status=completed` / `progress=100`; проверять вложенный успех, например `result.command.result.success` ([шаг 09](index.md)).
- **FTS и идентификаторы:** в SQLite-ветке возможны особенности FTS/`rowid`; в универсальной/PostgreSQL-модели — UUID; не переносить предположения между backend (см. [rollout-and-compatibility.md](../00-index/rollout-and-compatibility.md)).
- **Метаданные чанка:** план фиксирует тип чанка `DocBlock` для Markdown; отдельные поля вроде `source_type=docs_markdown` в этом плане не нормированы — при появлении в коде сверять с реализацией и командной схемой.
