# План: воркеры — сначала самые свежие файлы

Сводный отчёт (очереди, SQL, цепочка до СУБД):  
[docs/reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md](../../reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md)

**Связанный план (ортогонально):** приоритет MCP vs воркеров на **in-process** RPC к БД — две полосы очереди, без второго DB-процесса:  
[../2026-04-30-mcp-db-rpc-priority-lanes/README.md](../2026-04-30-mcp-db-rpc-priority-lanes/README.md)

**Детализация шагов 1–8** (orchestrator_tactical_debug: субагенты по файлу → код → связи → влияния → подзадачи → проверки):  
[step_descriptions_1-8_orchestrated.md](./step_descriptions_1-8_orchestrated.md)

**Файлы шагов (1 шаг = 1 целевой путь = 1 файл описания):** каталог [steps/](./steps/) — по одному Markdown на шаги **0**, **1**, **1a**, **2–8** с целями, статусом, проверками и перекрёстными ссылками.

**Карта параллелизации** (волны шагов 1–8, матрица PR, рантайм процессов):  
[PARALLELIZATION_MAP.md](./PARALLELIZATION_MAP.md)

---

## Статус (аудит кода, не задача на переписывание 1–7)

По прямому чтению репозитория зафиксировано: **шаги 1–7 уже реализованы** в целевом виде (батч и discovery индексатора, `PROJECTS_PENDING_SQL`, порядок файлов на чанкинг, оба `ORDER BY` в `batch_processor`, вторичный ключ по `updated_at` в `file_batch_packing`, тесты в шагах 6–7). **Не оформлять** шаги 1–7 как новые обязательные правки кода, пока повторный аудит не показал расхождение с этим README.

**Остаётся по плану:** **шаг 0** (верификация `project_id` проекта в БД сервера), **шаг 1a** (assert’ы на подстроки SQL в `tests/test_processing_paused_projects.py`) и **шаг 8** (обновить отчёт [docs/reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md](../../reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md): убрать описание старого ASC/FIFO как «текущего» для горячих путей воркеров).

Нумерация и блоки ниже — **контекст и регрессия**; для нового захода исполнителю достаточно **0**, **1a**, **8** и критериев готовности в конце.

---

## Правило структуры плана

**1 файл кода = 1 шаг.**

- Под «файлом кода» имеется в виду один путь в репозитории (`code_analysis/...` или `tests/...`), который меняется в рамках этой задачи.
- В описании одного шага не смешивать правки двух файлов: если нужны изменения в двух местах — это **два шага**.
- Порядок шагов ниже отражает зависимости (сначала логика воркеров, затем тесты, затем документация); независимые шаги по разным файлам можно делать параллельно, если нет конфликтов по ветке.

---

## Цель (два уровня — совесть)

1. **Уровень файла (`files.updated_at`):** индексатор и векторизатор выбирают **файлы** и порядок **проектов в индексаторе** так, чтобы в приоритете были **более недавно обновлённые** строки в таблице `files` (семантика поля — как в схеме для SQLite и PostgreSQL).
2. **Уровень чанка (`code_chunks.created_at`):** в **`batch_processor`** очередь **чанков** в рабочем батче — по **убыванию** `created_at` (и стабильный ключ по `id`); это **отдельная** ось приоритета от даты изменения файла. Канон **ASC** для полной пересборки FAISS / `base_chunks` **не меняется** без отдельного решения (см. шаг 6).

---

## Шаги реализации

### Шаг 0 — верификация контекста (**к выполнению перед правками**)

- Вызвать **`list_projects`** на **code-analysis-server** (через MCP proxy: `call_server`, команда `list_projects`, пустые `params`).
- Убедиться, что **`project_id`** целевого проекта репозитория (UUID из `projectid` в корне или из списка проектов) **присутствует** в ответе. Если проект не зарегистрирован — **остановиться** и зарегистрировать/исправить конфиг; **не** править файлы через сервер с неверным UUID.
- Дальнейшие команды `cst_load_file`, `read_project_text_file`, `universal_file_replace` и т.п. выполнять только с этим подтверждённым **`project_id`**.

### Шаг 1 — `code_analysis/core/indexing_worker_pkg/processing.py` (**закрыт в коде**)

- **В коде:** батч файлов с `needs_chunking = 1`: **`ORDER BY updated_at DESC, id DESC LIMIT ?`**.
- **В коде:** discovery проектов — **`GROUP BY f.project_id`** и **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`**.

### Шаг 1a — `tests/test_processing_paused_projects.py` (**к выполнению**)

- Добавить **два** новых теста (имена зафиксированы): **`test_indexing_discovery_sql_orders_by_freshness`**, **`test_projects_pending_sql_orders_by_freshness`** — проверка подстрок **`GROUP BY`**, **`ORDER BY`**, **`MAX(`**, **`updated_at`** в **`INDEXING_PROJECT_DISCOVERY_SQL`**; **`max_file_updated_at`**, **`ORDER BY`**, **`updated_at`** в **`PROJECTS_PENDING_SQL`** (существующие тесты на **`processing_paused`** / **`INNER JOIN`** не удалять).
- **Точка вставки в AST, не по номеру строки файла:** после тела функции **`test_indexing_discovery_sql_filters_processing_paused`** — найти её узел через **`cst_find_node`** (`search_type: simple`, имя функции), затем **`cst_modify_tree`** с **`action: insert`**, **`position: after`**, целевой узел — найденная функция; многострочный код передавать **`code_lines`**.
- **Один файл = один шаг:** в этой операции не смешивать правки других путей.
- После **`cst_save_tree`** (validate + backup по правилам репозитория): **`lint_code`** → **`format_code`** → **`type_check_code`** для этого файла (см. [docs/AI_TOOL_USAGE_RULES.md](../../AI_TOOL_USAGE_RULES.md)).
- **`run_project_module`:** `pytest tests/test_processing_paused_projects.py -v` с **`timeout_seconds`** (например **120**). **Ожидание:** **8** зелёных тестов (**6** существующих + **2** новых), не «6 с двумя новыми» и не путаница с общим числом строк файла.

### Шаг 2 — `code_analysis/core/vectorization_worker_pkg/processing_cycle.py` (**закрыт в коде**)

- **В коде:** столбец **`max_file_updated_at`**, порядок **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`**.

### Шаг 3 — `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py` (**закрыт в коде**)

- **В коде:** перед **`LIMIT`** — **`ORDER BY f.updated_at DESC, f.id DESC`**.

### Шаг 4 — `code_analysis/core/vectorization_worker_pkg/batch_processor.py` (**закрыт в коде**)

- **В коде:** **`chunk_select_sql`** и выборка embedding-ready — **`ORDER BY cc.created_at DESC, cc.id DESC`**.

### Шаг 5 — `code_analysis/core/vectorization_worker_pkg/file_batch_packing.py` (**закрыт в коде**)

- **В коде:** вторичный ключ по **`updated_at DESC`** (и согласованная передача из `batch_processor`).

### Шаг 6 — `tests/test_vectorization_uuid_sql_order.py` (**закрыт в коде**)

- Проверки на **`DESC`** для рабочих путей **`batch_processor`**; канон **ASC** для **`faiss_manager_rebuild`** / **`base_chunks`** — без изменений.

### Шаг 7 — `tests/test_indexing_worker.py` (**закрыт в коде**)

- Моки/ожидания согласованы с **`updated_at DESC`**.

### Шаг 8 — `docs/reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md` (**к выполнению**)

- Синхронизировать отчёт с уже внедрённой семантикой: формулировки «текущее поведение», цитаты SQL и сводная таблица раздела 5 — без описания ASC/FIFO для горячих путей воркеров как актуального состояния.
- **Инструмент записи:** предпочтительно **`universal_file_replace`** с массивом **`replacements`** (несколько непересекающихся диапазонов); сначала **`dry_run: true`**, затем **`dry_run: false`**. Если обработчик `.md` или контракт **`replacements`** недоступен — **`universal_file_save`** с полным текстом (также preview через **`dry_run`**). Для legacy-пути по строкам — **`write_project_text_lines`** только при отсутствии альтернатив; при множественных диапазонах **обрабатывать с конца файла к началу**, чтобы не сдвигать номера строк.
- Перед каждой заменой сверять фактический текст через **`read_project_text_file`** (или полное чтение отчёта): номера строк в отчёте и в блоках **````start:end:path````** пересверить с текущими файлами **`processing.py`**, **`processing_cycle.py`**, **`processing_cycle_projects.py`**, **`batch_processor.py`**.
- Полный чеклист правок отчёта — **16 замен** (§2.2–2.3, цитата индексатора, §2.3 «реализовано», §3.2 цитата + семантика + «реализовано», §3.3 `ORDER BY` в цитате, §3.4 чанки, §3.5 packing, §5 таблица из **трёх** колонок «текущее / предлагаемое» в **четыре**: **Место / Было / Стало / Статус**, §8 заключение). Детализация по абзацам — в [step_descriptions_1-8_orchestrated.md](./step_descriptions_1-8_orchestrated.md) (раздел «Шаг 8», приложение к плану).

---

## Файлы контекста без отдельного шага

Изменение порядка очереди **не требуется** в (пока достаточно правок выше):

- `code_analysis/core/indexing_worker_pkg/base.py`, `runner.py`
- `code_analysis/core/vectorization_worker_pkg/base.py`, `processing.py`, `runner.py`

Остальные тесты под векторизацию (`test_vectorization_project_cycle_stages.py`, `test_vectorization_chunking_without_svo.py`, …): отдельный шаг на каждый файл **только если** после шагов 1–6 тест начинает падать.

---

## Вне scope (отдельное решение)

Смена **семантики записи** поля **`updated_at`** в БД (кто и когда проставляет); очереди file watcher; правки **`docs/VECTORIZATION_BATCHING_ALGORITHM.md`** — **только отдельным шагом плана**, если нужно обновить описание алгоритма упаковки.

---

## Критерий готовности

- Выполнен **шаг 0** (`list_projects` → целевой **`project_id`** подтверждён).
- Закрыты **шаг 1a** (два новых теста + assert’ы; **8** тестов в `tests/test_processing_paused_projects.py` зелёные; black / flake8 / mypy на этом файле) и **шаг 8** (отчёт без устаревшего ASC для горячих путей; цитаты SQL и таблица §5 соответствуют коду).
- Регрессия: **`pytest tests/test_vectorization_uuid_sql_order.py -v`** (канон **ASC** для FAISS rebuild / `base_chunks` не ломался); **`pytest tests/test_file_batch_packing.py`**; **`pytest tests/test_indexing_worker.py`** — зелёные.
- Для набора файлов с разными **`updated_at`** первыми в батче оказываются файлы с **более поздней** датой (индексатор и выборка на чанкинг векторизатора).
- **Starvation (осознанный риск):** при постоянном потоке «свежих» правок старые большие хвосты **могут дольше** не попадать в лимит батча — это приёмлемый компромисс, пока явно не введён смешанный ключ (например лимит «голода» по времени ожидания); при продуктовом решении — отдельная задача.
- **NULL в сортировках:** если в данных встречаются **`NULL`** в **`updated_at`** / **`created_at`**, поведение **`ORDER BY … DESC`** зависит от СУБД (**NULLS FIRST/LAST**); приёмка должна включать сценарий с NULL или гарантировать отсутствие NULL в рабочих строках.
- Поведение согласовано для **SQLite и PostgreSQL** (портируемый SQL / `sql_portable` при необходимости).
- CI: black / flake8 / mypy на затронутых путях; pytest зелёный.

---

## Приложение: исправления по сравнению с ранней формулировкой задания

| # | Проблема | Было | Стало |
|---|-----------|------|--------|
| 1 | Точка вставки тестов | «после строки N» | После **AST-узла** функции **`test_indexing_discovery_sql_filters_processing_paused`**, найденного через **`cst_find_node`** |
| 2 | Ожидаемое число тестов | Путаница «6 зелёных, в т.ч. 2 новых» | **8** зелёных (**6** существующих + **2** новых) |
| 3 | Старт работ | Без проверки проекта | **Шаг 0:** **`list_projects`**, подтверждение UUID / **`project_id`** |
| 4 | Прогон pytest из сервера | `run_project_module` без таймаута | Указать **`timeout_seconds`** (например **120**) |
| 5 | Замены в `.md` | «Приблизительные» номера строк | Сверка с **`read_project_text_file`** и с актуальными **`start:end`** в цитатах кода |
| 6 | Запись отчёта | Только legacy `write_project_text_lines` | Предпочтительно **`universal_file_replace`** / при необходимости **`universal_file_save`** |
| 7 | Объём правок отчёта | Неполный набор замен | **16** согласованных замен (в т.ч. §2.3, §3.2, §3.4, §8) |
| 8 | Fenced citations | Устаревшие `287:292`, `137:138` | Пересверить с текущими файлами после диффов |
| 9 | Таблица §5 | Три колонки «текущее / предлагаемое» | Четыре: **Место / Было / Стало / Статус** |
