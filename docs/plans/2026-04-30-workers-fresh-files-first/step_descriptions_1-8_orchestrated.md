# Детализация шагов 1–8 (orchestrator_tactical_debug)

Сгенерировано по результатам субагентов: шаги 1–5 (первая пачка), шаги 6–8 (вторая пачка). Для каждого шага — чтение целевого файла, разбор кода, связей и влияний. Исходный план: [README.md](./README.md).

**Актуализация плана (аудит репозитория):** шаги **1–7** в коде уже приведены к целевой семантике; разделы ниже — **справка и чеклист верификации**, а не обязательный бэклог новых правок. **Остаётся по плану:** шаг **0**, шаг **1a** и шаг **8** в [README.md](./README.md) (раздел «Статус» и блоки шагов). Подзадачи «для реализации» в шагах 1–5 не переоткрывать без повторного аудита расхождений.

---

## Шаг 0 — верификация `project_id` (обязательно перед правками через сервер)

1. Вызвать **`list_projects`** на code-analysis-server (MCP: `call_server`, `command: list_projects`, `params: {}`).
2. Убедиться, что UUID целевого проекта репозитория присутствует в ответе. При отсутствии — **стоп**, не выполнять `cst_*` / file replace с предполагаемым UUID.
3. Все последующие `project_id` в параметрах команд брать из этого подтверждения.

---

## Шаг 1 — подробное описание (`indexing_worker_pkg/processing.py`)

Подробнее о намерении реализации см. **шаг 1** в [README.md](./README.md).

### Контекст и цель

- Индексатор отдаёт приоритет **более свежим** строкам **`files.updated_at`** и упорядочивает список проектов для обхода по **максимальной** свежести файлов в проекте.
- **Батч** файлов с `needs_chunking = 1`: **`ORDER BY updated_at DESC, id DESC LIMIT ?`** — сначала больший `updated_at`, затем стабильный tie-break по `id`.
- **`INDEXING_PROJECT_DISCOVERY_SQL`** — **неотъемлемая часть шага 1** (README): **`GROUP BY f.project_id`** и **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`** (вместо `DISTINCT project_id` без определённого порядка). Порядок батча внутри проекта задаётся отдельной выборкой (см. bullet выше).

### Что в файле и что проверить в коде

- **Целевая семантика** — как в bullets выше; при аудите дерева сравнивать константы с [README.md](./README.md).
- Исторически до плана встречались: **`DISTINCT`** в discovery без **`ORDER BY`** и **`ORDER BY updated_at ASC`** в батче — это не целевое состояние.
- Импорт **`sql_portable`**: `WHERE_FILES_*`, `sql_julian_timestamp_now_expr` — на ключ сортировки напрямую не влияют, условия `WHERE` должны остаться эквивалентными.
- Докстринг **`process_cycle`** и комментарии к SQL должны описывать **DESC** и роль **`id`** / discovery, а не устаревший ASC-only текст.
- **`worker_project_activity`**: `try_acquire` / `heartbeat` / `release` вокруг батча по проекту.

### Связи (кто вызывает / что вызывает)

- **`process_cycle`** привязан к классу в **`indexing_worker_pkg/__init__.py`**.
- Запуск: **`indexing_worker_pkg/runner.py`** — `asyncio.run(worker.process_cycle(...))`.
- Тесты: **`tests/test_indexing_worker.py`**.
- **`INDEXING_PROJECT_DISCOVERY_SQL`** также импортируется в **`tests/test_processing_paused_projects.py`** (проверки текста SQL).

### Влияния и риски

- Меняется очередность индексации **внутри проекта** при ограниченном `batch_size`.
- **`updated_at`**: в схеме обычно REAL (Julian); **`ASC`/`DESC`** корректны в SQLite и PostgreSQL.
- **`ORDER BY id DESC`**: стабилизирует tie-break; для UUID как строки — не порядок по времени создания.
- Моки в **`test_indexing_worker`** могут не отражать реальный `ORDER BY` без доработки.
- **`test_process_cycle_respects_project_order`**: при изменении discovery-SQL — проверить мок/ожидания.
- Упорядочивание проектов в discovery задаётся явно через **`GROUP BY`** и **`MAX(f.updated_at)`** (см. README), а не через «первый попавшийся» `DISTINCT` без сортировки.

### Подзадачи для реализации

1. Батч: **`ORDER BY updated_at DESC, id DESC`** (совместимо с SQLite и PostgreSQL).
2. Discovery: **`GROUP BY f.project_id`**, **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`**, сохранив условия активности файлов и `needs_chunking = 1`; корректно собрать список **`project_ids`**.
3. Обновить докстринг **`process_cycle`** и комментарии к константам SQL под DESC и GROUP BY discovery.
4. При необходимости скорректировать **`tests/test_indexing_worker.py`** и **`tests/test_processing_paused_projects.py`** (**шаг 1a** README — assert’ы подстрок SQL).
5. Прогнать pytest по затронутым тестам; при наличии — smoke на PostgreSQL.

### Проверки после правки

- Проходят **`test_indexing_worker`**, **`test_processing_paused_projects`**.
- На данных с разными **`updated_at`** первыми в батче — наибольший `updated_at` (и ожидаемый tie по **`id DESC`**).
- Нет регрессий по lease индексатора.
- Discovery-SQL выполняется на SQLite и при использовании — на PostgreSQL.

---

## Шаг 1a — подробное описание (`tests/test_processing_paused_projects.py`)

Отдельный шаг [README.md](./README.md): только этот файл; правки **только через CST** на стороне сервера (см. [docs/AI_TOOL_USAGE_RULES.md](../../AI_TOOL_USAGE_RULES.md)), не через `write_project_text_lines` / прямой patch Python с диска агентом.

### Цель

Два новых теста фиксируют подстроки DESC / свежести в константах **`INDEXING_PROJECT_DISCOVERY_SQL`** и **`PROJECTS_PENDING_SQL`**:

- **`test_indexing_discovery_sql_orders_by_freshness`**: `GROUP BY`, `ORDER BY`, `MAX(`, `updated_at`.
- **`test_projects_pending_sql_orders_by_freshness`**: `max_file_updated_at`, `ORDER BY`, `updated_at`.

### Вставка в дерево (не по номеру строки исходника)

1. **`cst_load_file`** → `tree_id`.
2. **`cst_find_node`**: `search_type: simple`, имя **`test_indexing_discovery_sql_filters_processing_paused`** → `node_id` функции.
3. **`cst_modify_tree`**: `action: insert`, вставка **после** (`position: after`) этой функции; тело двух новых функций в **`code_lines`**.
4. **`cst_save_tree`**: `validate`, `backup` по политике репозитория.

### Проверки качества и прогон

- **`lint_code`** → **`format_code`** → **`type_check_code`** для `tests/test_processing_paused_projects.py`.
- **`run_project_module`**: `pytest tests/test_processing_paused_projects.py -v` с **`timeout_seconds`** (рекомендуется **120**).
- **Ожидание:** **8** пройденных тестов (**6** прежних + **2** новых). Не путать с «6 тестов, включая 2 новых».

---

## Шаг 2 — подробное описание (`vectorization_worker_pkg/processing_cycle.py`)

Подробнее см. **шаг 2** в [README.md](./README.md) — там зафиксирована **одна** формула сортировки проектов, без альтернатив.

### Контекст и цель

- В выборке pending-проектов добавляется столбец **`max_file_updated_at`**: скалярный подзапрос вида **`SELECT MAX(f2.updated_at) FROM files f2 WHERE f2.project_id = p.id AND …`** по **активным** файлам (те же ограничения по обработке, что и для учёта «хвоста» работы — согласовать с фактическим `WHERE` в SQL).
- **Фиксированный порядок (README и код):** **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`** — сначала проект с более свежим максимумом по файлам; при равенстве **`max_file_updated_at`** — меньший backlog (**`pending_count`**); затем стабильный tie-break по **`p.id`**.
- Старое поведение «только **`ORDER BY pending_count ASC`**» не является целевым после согласования с README.

### Текущая логика SQL и цикла

- **`pending_count`**: сумма трёх скалярных подзапросов (файлы без чанков с докстрингами; чанки с embedding и без `vector_id`; чанки без embedding и не skipped).
- **`WHERE`**: та же сумма > 0.
- **`run_one_cycle`**: статистика → `execute(PROJECTS_PENDING_SQL)` → при непустом списке **`process_projects_in_cycle(..., projects, ...)`** в порядке SQL → **FAISS** по **`list_projects()`** (не по списку pending). После внедрения формулы выше результат `execute` должен выдавать строки уже в нужном порядке.

### Связи

- Вызов **`run_one_cycle`**: **`vectorization_worker_pkg/processing.py`**.
- **`PROJECTS_PENDING_SQL`**: только этот файл + тест **`test_processing_paused_projects.py`** (подстрока `processing_paused`).
- **`process_projects_in_cycle`**: минимально ожидает **`project_id`**, **`root_path`**, **`pending_count`**; **`max_file_updated_at`** участвует в **`ORDER BY`** в SQL и не обязан попадать в контракт распаковки строк в Python, если цикл к нему не обращается.

### Влияния и риски (в т.ч. PostgreSQL)

- Меняется только **порядок** обработки проектов в цикле.
- **FAISS**: порядок rebuild **не** от `PROJECTS_PENDING_SQL`.
- Логи и косвенно метрики по проектам; прогресс в **`process_projects_in_cycle`** от глобального `chunks_total_at_start`, не от порядка проектов.
- Риски: тяжёлый запрос; новые подзапросы по **`MAX(updated_at)`**; согласование типов времени; **tie-break** (`project_id`); при необходимости портативности — не только статическая строка-константа.

### Подзадачи для реализации

1. Добавить в **`SELECT`** выражение **`max_file_updated_at`**: подзапрос **`SELECT MAX(f2.updated_at) FROM files f2 WHERE f2.project_id = p.id AND …`** по активным файлам; условие **`WHERE`** согласовать с тем же набором «учитываемых» файлов, что и доменная логика pending.
2. Задать финальный ключ сортировки одной формулой: **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`** ([README.md](./README.md), шаг 2).
3. Проверить переносимость SQL (**SQLite и PostgreSQL**): типы времени, алиасы, при необходимости средства **`sql_portable`** — без изменения семантики **`execute(PROJECTS_PENDING_SQL)`**.
4. Обновить **`tests/test_processing_paused_projects.py`**: подстроки **`ORDER BY`**, **`max_file_updated_at`**, **`processing_paused`** (**шаг 1a** README при любой смене текста этого SQL).
5. Учесть продуктовый компромисс **starvation** крупных старых хвостов — см. критерий готовности в [README.md](./README.md).

### Проверки

- **`test_processing_paused_projects.py`** и тесты векторизационного воркера.
- Два+ проекта с pending и разной свежестью — порядок в логах и вызовах.
- SQLite и PostgreSQL: одинаковый набор `project_id`, нет ошибок типов.
- **`processing_paused`** по-прежнему исключает проекты.

---

## Шаг 3 — подробное описание (`vectorization_worker_pkg/processing_cycle_projects.py`)

### Контекст и цель

- Шаг 1 векторизации по проекту: SELECT файлов на docstring-чанкинг с **`LIMIT` без `ORDER BY`**.
- Цель: **`ORDER BY f.updated_at DESC, f.id DESC`** перед **`LIMIT`** — свежие файлы первыми, стабильный tie-break.

### Текущее поведение (целевое после шага 3 README)

- **`database.execute`** с большим `WHERE`, **`ORDER BY f.updated_at DESC, f.id DESC`** и **`LIMIT ?`** (`max_files_per_pass`). Исторически в отчёте фиксировался только **`LIMIT`** — при обновлении отчёта (шаг 8) цитата должна включать сортировку.
- Непустой список → **`worker._request_chunking_for_files`** (`chunking.py`: чтение диска, `DocstringChunker`, **`UPDATE files SET needs_chunking = 0`**, при успехе может вызываться **`process_embedding_ready_chunks`**).

### Связи

- Вызывающий: **`processing_cycle.run_one_cycle`**.
- Тесты: **`test_vectorization_project_cycle_stages.py`**, **`test_vectorization_chunking_without_svo.py`**, интеграции с **`_request_chunking_for_files`**.

### Влияния и риски

- **`needs_chunking` / `code_chunks`**: семантика та же, меняется **порядок** под лимитом.
- Риск «старого хвоста» при потоке свежих правок — осознанный продуктовый эффект.
- Индексы: **`idx_files_needs_indexing`**, **`idx_files_updated_at`** — влияние на план запроса.
- **SQLite / PostgreSQL**: сортировка по `updated_at` + `id DESC` согласована со схемой.

### Подзадачи для реализации

1. Вставить **`ORDER BY f.updated_at DESC, f.id DESC`** перед **`LIMIT ?`** (параметры не менять).
2. При расхождении диалекта — **`sql_portable`** (пока не требуется).
3. При жёстких assert на SQL в тестах — отдельный шаг по файлу теста.
4. После merge — отчёт плана (шаг 8 README).

### Проверки

- Несколько кандидатов с разными **`updated_at`** и малым **`max_files_per_pass`** — сначала максимальный `updated_at`, tie по **`id DESC`**.
- Прогон **`test_vectorization_project_cycle_stages.py`**, **`test_vectorization_chunking_without_svo.py`**.
- black / flake8 / mypy; при матрице — оба драйвера.

---

## Шаг 4 — подробное описание (`vectorization_worker_pkg/batch_processor.py`)

Единая целевая формула сортировки чанков в этом файле — [README.md](./README.md), **шаг 4**: **`ORDER BY cc.created_at DESC, cc.id DESC`** в обоих участках выборки (`chunk_select_sql` и embedding-ready SELECT).

### Контекст и цель

- **`ORDER BY cc.created_at, cc.id`** (ASC) в **`process_chunks_missing_embedding_params`** (`chunk_select_sql`) и **`process_embedding_ready_chunks`**.
- Цель: **`ORDER BY cc.created_at DESC, cc.id DESC`** — сначала **новые** чанки в рамках `LIMIT` / батча.

### Текущее поведение

- **Re-embed**: агрегат по файлам → **`pack_files_into_packets`** → по файлу **`chunk_select_sql`** + **`get_chunks_batch`** → **`_apply_chunker_results_to_db`**.
- **Embedding-ready**: один SELECT + цикл **`faiss_manager.add_vector`** + **`UPDATE vector_id`**.

### Связи

- **`processing_cycle_projects.py`**: STEP 0 и STEP 2; после чанкинга — **`chunking.py`** вызывает **`process_embedding_ready_chunks`**.
- **SVO**: порядок `rows` = порядок ответов батча.

### Влияния и риски

- Сознательный сдвиг приоритета между свежими и старыми «висяками».
- Порядок инкрементальных **`vector_id`** в батче следует порядку обхода (DESC → другой порядок id в батче vs ASC); на поиск обычно не влияет.
- **Rebuild FAISS** в других модулях остаётся **ASC** (`ROW_NUMBER`, `_fetch_chunks_for_rebuild`) — канон при полной пересборке; инкрементальный DESC в воркере может расходиться до следующего rebuild.
- **NULL `created_at`**: учесть различие NULLS FIRST/LAST между СУБД при приёмке.

### Подзадачи для реализации

1. В **`chunk_select_sql`**: заменить **`ORDER BY`** на DESC.
2. В **`process_embedding_ready_chunks`**: то же.
3. Согласовать README плана при необходимости.
4. При необходимости — отдельный тест на подстроку в **`batch_processor`**.
5. **Не менять** без отдельного решения **`ORDER BY`** в **`faiss_manager` rebuild** / **`base_chunks`**.

### Проверки

- **`tests/test_vectorization_uuid_sql_order.py`**: проверяет **другие** модули (rebuild ASC); после правки только **`batch_processor`** эти тесты **не обязаны** падать — но контраст «canonical ASC vs worker DESC» зафиксировать.
- **`test_postgres_dml_adapt.py`**: про **`HAVING`**, не про ORDER BY стадий.
- По плану шаг 6 — обновить тесты, если появятся assert на строку в **`batch_processor`**.

---

## Шаг 5 — подробное описание (`vectorization_worker_pkg/file_batch_packing.py`)

### Контекст и цель

- Сейчас сортировка только по **числу чанков** (DESC по count).
- Цель: вторичный ключ по **дате изменения файла DESC** при равном count; данные **`updated_at`** должны прийти из шага 4 (**`batch_processor.py`**).

### Текущее поведение

- **`FileCountRow = Tuple[str, str, int]`** — `(file_id, file_path, count)`.
- **`pack_files_into_packets`**: сортировка по `x[2]` DESC; **`_form_one_packet`** тоже сортирует по count; выход — списки троек с **`take_count`**.

### Связи

| Что | Где |
|-----|-----|
| Алгоритм | **`file_batch_packing.py`** |
| Единственный продакшн-caller | **`batch_processor.process_chunks_missing_embedding_params`** |
| Тесты | **`tests/test_file_batch_packing.py`** |

### Влияния и риски (включая зависимость от шага 4)

- Без расширения **`file_table`** в шаге 4 нечего сортировать по времени.
- Расширение API: кортеж **`(file_id, path, count, updated_at)`**; внутренние сортировки **`(-count, comparable_time)`** или явный **`key`** с двумя полями; при **остатке** после частичного съёма — сохранять тот же **`updated_at`**.
- Внешний контракт пакета можно оставить **тройками** `(file_id, path, take_count)`, чтобы не менять распаковку в **`batch_processor`** — тогда внутри только **`remaining`** как четвёрки.
- **Tie** по count и `updated_at` — третичный ключ (**`file_id`**).
- **SQL в шаге 4**: при `GROUP BY f.id, f.path` добавить однозначный **`f.updated_at`** (или **`MAX`** при необходимости).

### Подзадачи для реализации

1. После шага 4: включить **`updated_at`** в выборку и в строки **`file_table`**.
2. В **`file_batch_packing.py`**: тип, сортировки, **`_form_one_packet`**, сохранение времени на остатках.
3. Решить: пакеты наружу тройками или четвёрками (четвёрки потребуют правки распаковки в **`batch_processor`** — тогда это уже два файла в двух шагах).
4. Тесты: равный count, разный **`updated_at`**; при равенстве — третичный ключ.
5. При необходимости — **`docs/VECTORIZATION_BATCHING_ALGORITHM.md`**.

### Проверки

- **`pytest tests/test_file_batch_packing.py`**.
- Интеграционно: несколько файлов с одинаковым **`cnt`** и разным **`updated_at`** — порядок в пакетах / логах.
- Согласованность типов **`updated_at`** между драйвером и Python-сортировкой.

---

## Шаг 6 — подробное описание (`tests/test_vectorization_uuid_sql_order.py`)

### Контекст и цель

Семантика [README.md](./README.md): **шаг 4** задаёт **`ORDER BY cc.created_at DESC, cc.id DESC`** в **`batch_processor`**; **шаг 6** **добавляет** регрессионные **`assert`** через **`inspect.getsource`** именно для этого порядка. Канон **ASC** для полной пересборки FAISS и **`base_chunks`** **не затрагивается** без отдельного решения (см. цель плана README, два уровня приоритета).

После шага 4 порядок выборки чанков в **`batch_processor.py`** целевой — **`ORDER BY cc.created_at DESC, cc.id DESC`** (оба участка SQL). Жёсткие проверки подстрок в тестах не должны расходиться с кодом.

Файл изначально про миграцию UUID: лексический порядок **`id`** не равен порядку появления чанков, поэтому важен явный порядок по **`created_at`** и вторичный ключ по **`id`**.

### Что проверяет файл сейчас

Все три теста используют **`inspect.getsource`** без БД:

1. **`test_faiss_rebuild_row_number_sorts_by_created_at_then_id`** — в **`faiss_manager_rebuild.rebuild_from_database_impl`**: не менее четырёх вхождений **`ROW_NUMBER() OVER (ORDER BY created_at, id)`**.
2. **`test_faiss_fetch_chunks_orders_by_created_at`** — в **`_fetch_chunks_for_rebuild`**: подстрока **`ORDER BY cc.created_at, cc.id`**.
3. **`test_base_chunks_queries_use_created_at_order`** — в **`base_chunks.get_all_chunks_for_faiss_rebuild`** и **`get_non_vectorized_chunks`**: та же подстрока.

Итого: закреплён **восходящий** порядок в **FAISS rebuild** и **`base_chunks`**; **`batch_processor.py` этим файлом не проверяется**.

### Связь со шагом 4

В **`batch_processor`** два места с тем же паттерном **`ORDER BY cc.created_at, cc.id`**: **`chunk_select_sql`** (re-embed) и SELECT в **`process_embedding_ready_chunks`**. Шаг 4 меняет их на **DESC**. Существующие тесты шага 6 **не падают** от одной только правки **`batch_processor`**, пока не менялись rebuild / **`base_chunks`**.

### Влияния: когда менять этот файл

- **Только DESC в `batch_processor`:** имеет смысл **дополнить** тесты проверками исходника **`batch_processor`** (две функции / два фрагмента SQL) с ожидаемой подстрокой **`ORDER BY ... DESC`** — это и есть содержание шага 6 в README.
- **Менять существующие assert’ы на ASC** нужно **только если** в той же инициативе меняется порядок в **`faiss_manager_rebuild._fetch_chunks_for_rebuild`** или в **`base_chunks`** — иначе тесты перестанут отражать канон rebuild.

### Подзадачи для реализации

1. Зафиксировать целевую подстроку строго по [README.md](./README.md) шаг 4 и фактическому коду (пробелы, f-string).
2. **Добавить** (не заменяя три существующих теста выше) проверки исходника **`batch_processor`**: **`inspect.getsource`** по **`process_chunks_missing_embedding_params`** и **`process_embedding_ready_chunks`** с **`assert`** на подстроку **`ORDER BY cc.created_at DESC, cc.id DESC`** (или эквивалент с теми же **`DESC`**, что в коде после шага 4 — учитывать пробелы и f-string).
3. **Не менять** существующие **`assert`** на **`ORDER BY cc.created_at, cc.id`** (без DESC) для **`faiss_manager_rebuild`** / **`base_chunks`**, пока в этих модулях не меняется канон полной пересборки — иначе теряется смысл регрессии UUID vs времени.
4. При смене семантики в FAISS / **`base_chunks`** в **той же** инициативе — тогда обновить три существующих теста (включая **`ROW_NUMBER`**, если там вводится DESC).
5. Избегать ложных совпадений в комментариях при поиске подстроки.

### Проверки

- **`pytest tests/test_vectorization_uuid_sql_order.py`** зелёный после шага 4 и правок шага 6.
- В **`batch_processor`** в целевых запросах нет оставшегося **`ORDER BY cc.created_at, cc.id`** без **`DESC`**, если именно его заменили.
- Формулировка в [README.md](./README.md) шага 4 и ожидания в тестах совпадают.

---

## Шаг 7 — подробное описание (`tests/test_indexing_worker.py`)

### Контекст и цель

Модульные тесты цикла **`process_cycle`** (`indexing_worker_pkg/processing.py`): discovery проектов, батч файлов с **`LIMIT`**, вызовы **`index_file`**. **Целевая семантика ([README.md](./README.md), шаг 1):** батч **`ORDER BY updated_at DESC, id DESC`**, discovery **`GROUP BY f.project_id`**, **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`**. Тесты и моки должны отражать **«сначала свежее»** и порядок проектов из discovery, иначе остаются зелёными, но перестают моделировать БД.

### Текущие тесты и моки

**`_make_mock_database`**: ветка батча по подстрокам **`select id, path, project_id`** и **`params`** — возвращает **`(files_per_project[project_id] or [])[:limit]`** без учёта **`ORDER BY`**: порядок = порядок списка в данных теста.

| Тест | Суть |
|------|------|
| **`test_process_cycle_calls_index_file_for_files_with_needs_chunking`** | Два файла → два **`index_file`**, пути в множестве вызовов. |
| **`test_process_cycle_respects_batch_size`** | Три файла, **`batch_size=2`** → ожидаются **`a.py`** и **`b.py`** (первые два в списке). |
| **`test_process_cycle_respects_project_order`** | Два проекта, **`batch_size=1`** → порядок **`project_id`** **`["first", "second"]`**. |
| **`test_indexing_worker_one_cycle_integration`** | Реальная БД, один файл; порядок по нескольким файлам не проверяется. |

### Связь со шагом 1

В **`processing.py`** (план README): батч кандидатов — **`ORDER BY updated_at DESC, id DESC LIMIT ?`**; **`INDEXING_PROJECT_DISCOVERY_SQL`** — **`GROUP BY`** и **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`**. Докстринг **`process_cycle`** и ожидания тестов должны совпадать с этим, а не с устаревшим **`ORDER BY updated_at ASC`** или **`DISTINCT`** без порядка.

### Влияния и риски при сортировке DESC и явном discovery

1. Юнит-тесты с моком **формально** не ломаются, пока нет assert на текст SQL.
2. **Смысловой разрыв:** при **DESC** реальная БД отдаёт самые свежие строки первыми; если в тесте список «старые первые», ожидание «первые два = a и b» перестаёт соответствовать целевому SQL без переупорядочивания фикстур или явных **`updated_at`**.
3. Порядок проектов зависит от **MAX(updated_at)** по проекту — мок списка **`projects`** должен быть согласован с тем, как discovery упорядочивает **`project_id`**, если тест утверждает порядок обхода.
4. Интеграционный тест с одним файлом почти не чувствителен к порядку батча.

### Подзадачи для реализации

1. При необходимости: научить мок учитывать в SQL **`ORDER BY updated_at DESC, id DESC`** и сортировать кандидатов по **`updated_at`** (и при равенстве — по **`id`** DESC) в памяти перед **`[:limit]`**.
2. В фикстурах файлов задать **`updated_at`** явно; ожидать первые **`LIMIT`** путей по правилу DESC.
3. Явный assert **порядка** вызовов **`index_file`** (список пар path/project_id), а не только множество.
4. Учесть финальный **`INDEXING_PROJECT_DISCOVERY_SQL`** ([README.md](./README.md), шаг 1): при тестах порядка проектов согласовать ожидания с **`GROUP BY`** и **`ORDER BY MAX(f.updated_at) DESC`** (или оставить явный контроль через порядок в мок-списке **`projects`** — но тогда документировать, что именно моделируется).
5. Опционально: spy на **`execute`** с проверкой **`LIMIT`**.

### Проверки

- **`pytest tests/test_indexing_worker.py`** после шага 1 и правок шага 7.
- Для **`test_process_cycle_respects_batch_size`**: список файлов упорядовать как после **`ORDER BY updated_at DESC, id DESC`** (в БД первыми — наибольший **`updated_at`**, затем **`id`**), если проверяются «первые два» после **`LIMIT`**.
- Интеграционный тест: при расширении на несколько файлов — проверка порядка/набора после одного цикла.

---

## Шаг 8 — подробное описание (`docs/reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md`)

### Контекст и цель

После реализации шагов 1–7 отчёт должен описывать **фактическое** поведение и актуальные цитаты SQL, а не только «как было» и рекомендации. Иначе расходится с кодом и со ссылкой из [README.md](./README.md).

**Инструменты:** предпочтительно **`universal_file_replace`** с **`replacements`** и двухфазным применением (**`dry_run: true`** → preview, затем **`false`**). Fallback: **`universal_file_save`** полным текстом с тем же preview. При правке по диапазонам строк legacy-командой — **с конца файла к началу**, чтобы номера строк не «поехали» между вызовами.

### Структура отчёта (что обновить после кода)

Полный набор правок в актуальной версии плана — **16 замен** (абзацы + fenced blocks + одна замена внутри большой цитаты `processing_cycle_projects.py` — вставка **`ORDER BY ... LIMIT`**). Ниже — карта по разделам; перед применением каждой замены сверять текст через **`read_project_text_file`**.

| Раздел | Действие |
|--------|----------|
| **§1** | При желании явно: где введён LIFO по времени выборки. |
| **§2.2** | Замена абзаца про discovery: не «без глобального порядка», а **`GROUP BY` / `ORDER BY MAX(f.updated_at) DESC`**. |
| **§2.2** | Fenced цитата **`processing.py`**: **`ORDER BY updated_at DESC, id DESC`**; актуальные **`start:end`**. |
| **§2.3** | Заменить рекомендации «минимальное изменение» на формулировку **«реализовано»** (файлы + discovery). |
| **§3.2** | Fenced **`processing_cycle.py`**: **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`**; актуальные строки. |
| **§3.2** | Семантика абзацев + строка «реализовано» вместо альтернатив **`pending_count DESC`**. |
| **§3.3** | В цитате запроса — явный **`ORDER BY f.updated_at DESC, f.id DESC`** перед **`LIMIT`**. |
| **§3.3** | Абзац семантики: детерминированный порядок, не «недетерминировано». |
| **§3.4** | Обе цитаты **`ORDER BY cc.created_at DESC, cc.id DESC`**; абзац LIFO + «реализовано». |
| **§3.5** | Расширение модели и сортировка **`(count DESC, updated_at DESC, file_id)`** — как **реализовано**. |
| **§5 таблица** | Структура **четыре** колонки: **Место / Было / Стало / Статус** (см. [README.md](./README.md), приложение). |
| **§6** | Актуальные grep/тесты после шагов 6–7. |
| **§8 заключение** | Заменить заключение про «старые первыми» на описание DESC-политики и исключение канона ASC для FAISS rebuild / `base_chunks`. |
| **§4, §7** | Вычитка; прямых противоречий реализации мало. |
| **Все fenced citations** | Пересверить **`start:end:path`** с файлами после диффов. |

### Связи с шагами 1–7

- Шаги **1–5** → соответствующие §2–3 и строки §5.
- Шаги **6–7** → §6 и при желании фраза о покрытии тестами в §5/§8.

### Подзадачи правок по разделам

1. **§2**: актуальный порядок индексатора + citation **`processing.py`**.
2. **§3.2–3.5**: семантика и citation под фактический SQL.
3. **§5**: таблица под пост-реализацию.
4. **§6**: checklist и имена тестовых файлов.
5. **§8**: заключение под текущую политику и компромиссы (§6).
6. Пройти все **````start:end:path````** и выровнять с репозиторием.

### Проверки (консистентность)

- Каждый изменённый в шагах 1–5 файл: SQL в отчёте = SQL в коде.
- **§3.2:** одна политика как в [README.md](./README.md) шаг 2 и в **`PROJECTS_PENDING_SQL`**: **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`** — без «или **`pending_count DESC`**» и иных альтернатив из старого текста.
- **§3.5:** не описывать **`updated_at`** в packing, если шаг 5 ещё не пробросил данные из шага 4.
- **§1, §7:** модель «очередь = SQL, не RAM» остаётся верной.

### Согласование с README плана

Отчёт и [README.md](./README.md) должны описывать **одну** реализованную политику на шаг (**§3.2** ↔ **`PROJECTS_PENDING_SQL`** = **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`** без альтернатив). **Discovery в индексаторе** входит в **шаг 1** README (**`GROUP BY`**, **`ORDER BY MAX(f.updated_at) DESC`**), а не вынесено в отдельное «опциональное решение». Старый текст отчёта, допускавший другие противоречивые ключи (**например** **`pending_count DESC`** там, где в коде иначе), нужно заменить фактической цитатой из дерева после мержа.
