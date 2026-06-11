# Rollout и совместимость: `code_analysis.docs_indexing`

**Область:** индексация Markdown-документации через существующий пайплайн `files` → `code_chunks` → (опционально) векторы.  
**Источники:** [01-task-spec.md](../01-task-spec.md), [implementation-decisions.md](implementation-decisions.md), [parallelization-map.md](parallelization-map.md), шаги [05](../05-watcher-integration/index.md)–[09](../09-tests-and-mcp-verification/index.md).

---

## Значения по умолчанию

Секция `code_analysis.docs_indexing` **опциональна**. Если её нет, конфиг остаётся валидным; поведение как до фичи.

Явные/генерируемые по умолчанию значения (контракт ТЗ):

| Поле        | По умолчанию |
|------------|----------------|
| `enabled`  | `false` — watcher и связанные пути **не** рассматривают docs indexing. |
| `vectorize`| `false` — даже при ручном `enabled=true` векторизация по умолчанию выключена. |
| `roots`    | `["docs"]` |
| `include`  | `["docs/**/*.md", "README.md"]` |
| `exclude`  | `["docs/plans/**", "docs/ai_reports/**"]` |

Настройки только в **основном server config**, не в `projectid`.

---

## Миграция существующих конфигов

1. **Без секции `docs_indexing`** — валидно; индексация кода и семантика `semantic_search` не меняются (нет доков в пайплайне).
2. **Добавление секции** — через генератор/CLI или ручное дописание JSON; после изменения конфигурации и кода сервера нужен **restart** демона, чтобы подтянуть конфиг ([шаг 10](../10-docs-and-rollout/index.md)).
3. **Включение `enabled=true`** — только `.md`, только eligible пути (`roots` / `include` / `exclude`, приоритет exclude над include).
4. **Включение `vectorize=true`** — допускается только осознанно: включает существующий embedding/FAISS-пайплайн для доковых чанков; до этого `semantic_search` по докам не возвращает результаты.

---

## Краткое поведение по контуру

**Watcher (шаг 05):** при `enabled=false` поведение как раньше; при `enabled=true` в общий поток попадают только eligible Markdown-файлы, с логируемыми причинами пропуска (disabled / non-md / вне roots / не include / exclude).

**Чанки (шаг 06):** те же таблицы `files` и `code_chunks`, без `docs_chunks` / `docs_vectors`. Тип чанка для Markdown по плану: `ChunkType.DOC_BLOCK` / строка `"DocBlock"` ([ТЗ](../01-task-spec.md)). Отдельное поле вроде `source_type=docs_markdown` в пользовательской документации этим планом не фиксируется; если оно появляется в реализации или метаданных команд, сверяйте с фактическим кодом и [METADATA_SCHEMA_STANDARD.md](../../../METADATA_SCHEMA_STANDARD.md).

**Fulltext / зеркало к `code_content` / FTS (шаги 06–08):** keyword/fulltext в продукте опирается на слой вида **`code_content` / FTS** ([implementation-decisions.md](implementation-decisions.md)). Целевое ТЗ: при `vectorize=false` чanking и полнотекстовый поиск по проиндексированным Markdown **должны** сохраняться, а FAISS/semantic — нет ([01-task-spec.md](../01-task-spec.md), [parallelization-map.md](parallelization-map.md)). Фактическая привязка fulltext к чанкам vs сырому файлу — проверять после интеграции ([08](../08-search-and-diagnostics/index.md)).

**Semantic + `vectorize` (шаги 07–08):** `semantic_search` идёт из FAISS по `vector_id` в `code_chunks`. Доки в выдаче **только** если `vectorize=true` и чанки прошли векторизацию; при `vectorize=false` документы в `semantic_search` не ожидаются.

---

## Гарантии совместимости

- Конфиг без `docs_indexing` остаётся валидным.
- При отключённой фиче индексация кода не меняется.
- Форма ответа существующих команд (в т.ч. `semantic_search`) не меняется на уровне контракта; меняется только наполнение при включённой векторизации доков.
- Отдельные таблицы только для доков не вводятся.

---

## FTS, `rowid` и UUID (оговорка)

В репозитории отдельно зафиксировано: очистка/FTS в ветке SQLite может опираться на **`rowid`**, тогда как идентификаторы строк в универсальной модели — **UUID TEXT**; PostgreSQL и универсальный драйверный код не должны наследовать предположения SQLite FTS/`rowid` ([docs/ERRORS.md](../../../ERRORS.md), планы миграции UUID в `docs/plans/2026-04-27-full-uuid-db-migration/`). Для fulltext по докам учитывайте выбранный backend драйвера.

---

## См. также

- Операционный чеклист: [../10-docs-and-rollout/rollout-notes.md](../10-docs-and-rollout/rollout-notes.md)
- Деталь совместимости (дублирующий срез): [../10-docs-and-rollout/compatibility-notes.md](../10-docs-and-rollout/compatibility-notes.md)
- Ограничения: [../09-tests-and-mcp-verification/known-limitations.md](../09-tests-and-mcp-verification/known-limitations.md)
- Итоговый отчёт (в т.ч. MCP): [../10-docs-and-rollout/final-implementation-report.md](../10-docs-and-rollout/final-implementation-report.md)
