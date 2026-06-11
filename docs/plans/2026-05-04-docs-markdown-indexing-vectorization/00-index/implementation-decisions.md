# Зафиксированные решения для реализации

**Аудитория:** разработчики, подключающие план к коду.  
**Источники:** [../01-task-spec.md](../01-task-spec.md), [index.md](index.md), [parallelization-map.md](parallelization-map.md).  
**Назначение:** единая точка согласования до правок общего пайплайна; не заменяет ТЗ по деталям валидации и тестов.

---

## Область (Scope)

- В scope: только Markdown (`.md`), настройки только в основном server config под `code_analysis`, без отдельного стека хранилища для документации.
- Переиспользование существующего жизненного цикла `files` → chunk → (опционально) векторы, без `docs_chunks` / `docs_vectors` / отдельного семантического пути только для доков ([01-task-spec.md](../01-task-spec.md), ограничения в [index.md](index.md)).
- Не трогать `.venv`, `site-packages`, установленные копии зависимостей.

---

## Зафиксированные поля конфигурации

Секция: `code_analysis.docs_indexing`.

| Поле       | Роль |
|------------|------|
| `enabled`  | Включение фичи; при `false` watcher и связанные воркеры **полностью** игнорируют docs indexing. |
| `vectorize`| При `false` чанки доков могут индексироваться, но **не** отправляются в embeddings/FAISS; при `true` — существующий vectorization pipeline. |

Массивы:

| Поле      | Роль |
|-----------|------|
| `roots`   | Корни (только относительные пути проекта), под которыми могут рассматриваться markdown-кандидаты; без абсолютных путей и без `..`. |
| `include` | Паттерны включения (относительно проекта); **только** паттерны для Markdown (валидатор отклоняет non-md include). |
| `exclude` | Паттерны исключения; **исключение имеет приоритет над включением.** |

**Boolean defaults (жёстко):** `enabled=false`, `vectorize=false` (в том числе при ручном `enabled=true`, vectorize по умолчанию остаётся `false`, см. ТЗ).

**Defaults для массивов:** фиксируются контрактом шага `02-config-contract` ([02-config-contract/index.md](../02-config-contract/index.md): `roots=["docs"]`, `include=["docs/**/*.md", "README.md"]`, `exclude=["docs/plans/**", "docs/ai_reports/**"]`). Генератор и валидатор должны оставаться согласоваными с этими значениями после завершения Group B.

---

## Порядок пайплайна (frozen)

Из [parallelization-map.md](parallelization-map.md):

```text
config
  -> eligibility
  -> watcher
  -> files rows
  -> chunker file API
  -> code_chunks persistence
  -> fulltext/BM25
  -> optional FAISS/vectorization
  -> search verification
```

Параллелизм допустим только при стабильных границах и без одновременного редактирования одной и той же стыковочной точки пайплайна разными исполнителями.

---

## Глобальные решения (сводка)

Согласовано между ТЗ, индексом плана и картой параллелизации:

- Только `.md`; non-markdown типы файлов через эту фичу не индексируются.
- `enabled=false` и `vectorize=false` по умолчанию; настройки не в `projectid`.
- Chunker принимает Markdown как обычный текстовый ввод; маршрут — существующий file-based chunker API ([01-task-spec.md](../01-task-spec.md), resolved decisions).
- Семантический поиск опирается на **`code_chunks` + FAISS** и маппинг `vector_id`; при `vectorize=false` доковые чанки **не** должны быть видны через `semantic_search` (нет embeddings/FAISS).
- Отдельная diagnostics-команда для этой задачи **не требуется**; верификация — тестами и существующими MCP/командами (`fulltext_search`, `semantic_search`, `check_vectors` и др., см. ТЗ).

---

## Контракт чанков и поиска

**Хранение:** markdown-чанки живут в существующей таблице/модели `code_chunks`; отдельных `docs_chunks` / `docs_vectors` **нет**.

**Тип чанка:** `ChunkType.DOC_BLOCK` / строка `"DocBlock"` ([01-task-spec.md](../01-task-spec.md)); новый тип не вводится без расширения `chunk_metadata_adapter.ChunkType` и проверки всех потребителей.

**Semantic surface:** текущий контракт `semantic_search`: FAISS → строки `code_chunks`, join с `files` (см. SQL-образец в ТЗ). Документы попадают в выдачу только при наличии валидного vector-пути тем же способом, что и код.

**Fulltext / keyword surface (открытый момент):** семантика опирается на `code_chunks`+FAISS; **keyword/fulltext** в продукте завязана на представление вида **`code_content` / FTS**. Обеспечение предсказуемого keyword-поиска по проиндексированным Markdown-файлам **требует отдельного явного дизайна** после интеграции персистенции чанков — закрепить в рамках **Groups E–G** ([06](../06-indexing-chunker-integration/index.md), [07](../07-vectorization-gating/index.md), [08](../08-search-and-diagnostics/index.md)), без выдумывания деталей на Wave 1.

---

## Eligibility (Wave 1)

- Один переиспользуемый helper-модуль под `code_analysis/core/` (см. Group C в [parallelization-map.md](parallelization-map.md)).
- Приоритет **`exclude` над `include`**.
- Жёстко: только суффикс `.md`; пути только относительно корня проекта.
- Согласование семантики matcher’а со **listing-style globs** и контрактом `02-config-contract` (в т.ч. проверка `**` и краевых случаев), без расхождения между validator/runtime.

---

## Риски интеграции пайплайна

**Wave 3 (интеграция watcher/indexer):** текущее поведение watcher/indexer ориентировано на **`.py`** (и смежные code-расширения); типичное место — снятие `needs_chunking` для non-`.py` без постановки в тот же путь чанкинга, что и для Python. Подключение `.md` **обязано намеренно изменить** это поведение только для включённой фичи и только для eligible путей; иначе доки не дойдут до chunker/`code_chunks`. Риск считается **высоким** на этапе `06-indexing-chunker-integration` (Group E); уточнение фактического кода — по итогам `01-current-state-inventory`.

---

## Вне scope для Wave 2

По [parallelization-map.md](parallelization-map.md), **Wave 2** — параллельная подготовка: реализация validator/generator, helper eligibility, узкие unit-тесты, синхронизация формы конфига.

**Не входит в Wave 2:** правки общего пайплайна watcher → indexer → shared `code_chunks` persistence → vectorization (это Wave 3+), за исключением изолированных файлов validator/generator/eligibility, явно разрешённых картой.

---

## Сверка перед merge кода

Убедиться, что генератор совпадает с валидатором и eligibility принимает ту же форму `docs_indexing`; перед интеграцией пайплайна зафиксировать выводы inventory (Group A), чтобы решения этого файла не противоречили фактическому коду.
