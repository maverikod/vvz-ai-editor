# Ревью task-файлов: готовность к исполнению Qwen 2.5 Coder 32B (Q4_K_M)

## Инвентарь файлов в corrections/

| # | Файл | Целевой код | Статус |
|---|------|------------|--------|
| 1 | `task-rpc_protocol.md` | `protocol/rpc_protocol.py` | ✅ Чисто, шаг 1 done |
| 2 | `task-rpc_dispatch.md` | `rpc_dispatch.py` | ✅ Чисто, парадигма ok |
| 3 | `task-in_process_rpc_client.md` | `in_process_rpc_client.py` | ✅ Шаг 2a done |
| 4 | `task-postgres_execute_lane.md` | `postgres_execute_lane.py` | ✅ Чисто |
| 5 | `task-postgres.md` | `postgres.py` | ⚠️ Нужна доработка |
| 6 | `task-postgres_1.md` | `postgres.py` | ❌ ДУБЛИКАТ task-postgres.md |
| 7 | `task-postgres_connection_pool_4.md` | `postgres_connection_pool.py` | ❌ УСТАРЕЛ — описывает проблемы уже решённые в коде |
| 8 | `task-batch_processor.md` | `batch_processor.py` | ⚠️ Нужна доработка |
| 9 | `task-processing_cycle.md` | `processing_cycle.py` | ❌ УСТАРЕЛ — описывает magic numbers, уже исправлены |
| 10 | `task-processing_cycle_projects.md` | `processing_cycle_projects.py` | ❌ ЧАСТИЧНО УСТАРЕЛ |
| 11 | `task-client_operations.md` | `client_operations.py` | ⚠️ Нужна доработка |
| 12 | `task-get_database_status_build.md` | `get_database_status_build.py` | ❌ УСТАРЕЛ — idle/waiters уже экспортируются |
| 13 | `task-indexing_processing.md` | `processing.py` (indexing) | ⚠️ Нужна доработка |

---

## Детальный разбор по каждому файлу

### 1. `task-rpc_protocol.md` — OK ✅
Корректно: шаг 1 выполнен. Нет действий.

### 2. `task-rpc_dispatch.md` — OK ✅
Корректно: парадигма соблюдена. Нет действий.

### 3. `task-in_process_rpc_client.md` — OK ✅
Корректно: шаг 2a выполнен. Мелкое замечание про race в `disconnect()` — low priority, корректно описано.

### 4. `task-postgres_execute_lane.md` — OK ✅
Корректно: файл чистый. Замечания про PREPARE/EXECUTE — информационные, верные.

### 5. `task-postgres.md` — НУЖНА ДОРАБОТКА ⚠️

**Проблемы для Qwen:**
- Не объясняет архитектуру: PostgreSQL = многопоточный доступ через пул, SQLite = subprocess. Qwen 32B Q4 не выведет это из контекста.
- Пункт 4 ("self.conn is 6th connection") описывает «проблему», но план README явно говорит: «пять именно в **пуле**; основное `self.conn` и транзакции — вне пула». Это не баг, а задокументированное поведение. Task-файл должен говорить «документировать», а не «исправить».
- Нет указания на F-02 из моего аудита (pool destroyed under active threads без graceful drain).
- Нет указания на F-03 (stale pool connections).

**Рекомендации:**
1. Добавить секцию «Architecture context» в начало
2. Убрать «concern» про 6-ю коннекцию — план это явно разрешает
3. Добавить F-02 (reconnect_main + active threads)
4. Добавить F-03 (stale pool conn health check)
5. Дать точные номера строк в ТЕКУЩЕМ коде (539 строк, не 516)

### 6. `task-postgres_1.md` — УДАЛИТЬ ❌
Полный дубликат `task-postgres.md`. Qwen получит противоречивые инструкции.

### 7. `task-postgres_connection_pool_4.md` — УСТАРЕЛ ❌

**Критические ошибки:**
- Пункт 1 «No timeout on acquire() — potential deadlock»: **НЕВЕРНО**. В текущем коде (186 строк) `max_wait_seconds=30` реализован с `deadline` и `DriverOperationError` на таймаут. Линии ~108-170.
- Пункт 2 «No waiter count in snapshot()»: **НЕВЕРНО**. `self._write_waiters` и `self._read_waiters` уже есть, `snapshot()` их возвращает.
- Пункт 4 «No logging inside acquire()»: **НЕВЕРНО**. Логи уже есть: `logger.debug("Pool acquire(%s) waiting...")` и `logger.debug("Pool acquire(%s) got slot %d in %.3fs...")`.
- Пункт 3 (health check) — единственный валидный пункт.
- Файл говорит «Lines: 141» — фактически 186.

**Рекомендация:** Полностью переписать. Оставить только F-03 (health check) и F-04 (autocommit=False на read pool).

### 8. `task-batch_processor.md` — НУЖНА ДОРАБОТКА ⚠️

**Проблемы:**
- Пункт 2 «Magic number priority=1»: **УСТАРЕЛ**. Текущий код (строка 25) делает `from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY`. Нужно проверить, все ли вхождения заменены.
- Пункт 1 (split 635→400) — актуален.
- Пункт 3 (f-string logging) — актуален.
- Пункт 4 (FAISS error handling) — актуален.

**Рекомендации:**
1. Убрать или переформулировать пункт 2 — проверить, не осталось ли literal `priority=1`
2. Уточнить текущий размер файла (640 строк, не 635)
3. Добавить архитектурный контекст для Qwen

### 9. `task-processing_cycle.md` — УСТАРЕЛ ❌

**Критическая ошибка:**
- Пункт 1 «Magic number priority=1 instead of named constant»: **НЕВЕРНО**. Текущий код (строка 19) импортирует `BACKGROUND_WORKER_DB_RPC_PRIORITY`. Все вызовы `database.execute()` используют эту константу.
- Файл описывает несуществующую проблему.

**Рекомендация:** Переписать. Если остались реальные проблемы (размер файла 402 строки — пограничный), оставить. Если нет — убрать или отметить «no action needed».

### 10. `task-processing_cycle_projects.md` — ЧАСТИЧНО УСТАРЕЛ ❌

**Проблемы:**
- Пункт 2 «Magic number priority=1»: **УСТАРЕЛ**. Строка 17 импортирует `BACKGROUND_WORKER_DB_RPC_PRIORITY`.
- Пункт 1 (file size 428→400) — актуален.

**Рекомендация:** Убрать пункт 2. Оставить пункт 1 (split).

### 11. `task-client_operations.md` — НУЖНА ДОРАБОТКА ⚠️

В целом корректен:
- Пункт 1 (split to <400 lines) — актуален.
- Пункт 2 (priority in execute/execute_batch) — корректно ✅.
- Пункт 3 (add_code_chunk без priority) — low priority, корректно.

**Для Qwen:** Добавить конкретный пример кода для извлечения мixin-а.

### 12. `task-get_database_status_build.md` — УСТАРЕЛ ❌

**Критические ошибки:**
- Пункт 2 утверждает «fields pg_write_pool_idle and pg_read_pool_idle are NOT exported — only in_use is»: **НЕВЕРНО**. Текущий код (строки 207-219) экспортирует idle И waiters для обоих пулов.
- Пункт 1 (split) — актуален.
- Пункт 3 (STATUS_OPS hardcoded) — актуален, нужно проверить.

**Главная нерешённая проблема (F-05 из моего аудита):** функция `_postgres_pool_observability_fields` пробивает абстракцию через `db.rpc_client.handlers.driver`. Это НЕ упомянуто в текущем task-файле!

**Рекомендация:** Переписать. Добавить F-05. Убрать устаревший пункт 2.

### 13. `task-indexing_processing.md` — НУЖНА ДОРАБОТКА ⚠️

В целом корректен:
- Пункт 1 (split 622→400) — актуален.
- Пункт 2 (priority tagging done ✅) — корректно.
- Пункт 3 (SELECT 1 without priority) — корректно, no fix needed.
- Пункт 4 (julianday) — **важная находка**, актуальна.

**Для Qwen:** Добавить конкретные строки с `julianday('now')` и замену на `sql_julian_timestamp_now_expr()`.

---

## Отсутствующие task-файлы (из моего аудита)

| Что отсутствует | Finding | Важность |
|----------------|---------|----------|
| `task-rpc_server.md` | F-06: `_priority_for_request` не читает `RPCRequest.priority` | Phase 2 — не критично сейчас |
| `task-integration_test.md` | F-08: нет интеграционного теста MCP+workers под PG | Step 7 не закрыт |
| `task-rpc_protocol.md` update | F-01: priority — мёртвый код, нужен docstring | Low |

---

## Рекомендации для доведения до 100% готовности для Qwen 2.5 Coder 32B Q4_K_M

### Ключевые ограничения Qwen 32B Q4:
1. **Контекст ~8-16K токенов** (эффективный) — task-файл должен быть самодостаточным
2. **Нет удержания контекста между файлами** — каждый task = одна атомарная задача
3. **Слабое абстрактное мышление** — нужны конкретные: пути, строки, код «до/после»
4. **Склонность к hallucination** при неточных описаниях — устаревшие данные = ошибки
5. **Хорошо следует шаблонам** — единый формат task-файлов критичен

### Что нужно сделать:

#### A. Структурные исправления
1. **Удалить `task-postgres_1.md`** — дубликат
2. **Переписать `task-postgres_connection_pool_4.md`** — 3 из 4 пунктов устарели
3. **Переписать `task-processing_cycle.md`** — основной пункт устарел
4. **Переписать `task-get_database_status_build.md`** — пункт 2 устарел, не упомянут F-05
5. **Обновить `task-processing_cycle_projects.md`** — убрать пункт 2
6. **Обновить `task-batch_processor.md`** — проверить пункт 2

#### B. Формат каждого task-файла (шаблон для Qwen)
Каждый файл должен содержать:

```markdown
# Task: <filename>

## Architecture context
<2-3 предложения: что делает файл, в каком слое, PostgreSQL multi-thread vs SQLite subprocess>

## File location
- Path: `code_analysis/...`
- Current lines: <N>
- Line limit: 400

## What works (DO NOT CHANGE)
<список того, что уже правильно — чтобы Qwen не сломал>

## Changes required
### Change 1: <название>
- **Problem:** <конкретно>
- **Current code (lines X-Y):**
```python
<текущий код>
```
- **Required code:**
```python
<точный новый код>
```
- **Why:** <1 предложение>

## Validation
1. <конкретная команда>
2. <конкретная команда>

## Constraints
- DO NOT modify <что не трогать>
- File MUST be ≤400 lines after changes
```

#### C. Каждый task-файл должен:
1. **Содержать текущие номера строк** (не из момента первого аудита)
2. **Не содержать устаревших данных** — Qwen поверит и будет «исправлять» уже исправленное
3. **Давать код «до» и «после»** дословно, без «например» — Qwen лучше копирует, чем придумывает
4. **Явно перечислять «DO NOT CHANGE»** — иначе Qwen может «улучшить» рабочий код
5. **Один файл = одна атомарная задача** — не «split file + fix magic numbers + fix logging»

#### D. Разбить сложные задачи на подзадачи
- `task-batch_processor.md` (3 изменения) → 3 файла:
  - `task-batch_processor-split.md` (split to <400)
  - `task-batch_processor-logging.md` (f-string → %-format)
  - `task-batch_processor-faiss-error.md` (document error handling)
- `task-indexing_processing.md` (2 изменения) → 2 файла:
  - `task-indexing_processing-split.md`
  - `task-indexing_processing-julianday.md`

#### E. Добавить отсутствующие task-файлы
1. `task-integration_test.md` — из моего архива (F-08)
2. `task-rpc_server.md` — из моего архива (F-06, Phase 2 scope)

---

## Итого: минимальный список действий

| # | Действие | Приоритет |
|---|---------|-----------|
| 1 | Удалить `task-postgres_1.md` (дубликат) | Критично |
| 2 | Переписать `task-postgres_connection_pool_4.md` (3/4 устарело) | Критично |
| 3 | Переписать `task-processing_cycle.md` (основной пункт устарел) | Критично |
| 4 | Переписать `task-get_database_status_build.md` (пункт 2 устарел + F-05 не упомянут) | Критично |
| 5 | Обновить `task-processing_cycle_projects.md` (убрать пункт 2) | Высокий |
| 6 | Обновить `task-batch_processor.md` (проверить пункт 2 на актуальность) | Высокий |
| 7 | Обновить `task-postgres.md` (добавить F-02, F-03, убрать ложный concern про 6-й conn) | Высокий |
| 8 | Привести все файлы к единому шаблону с кодом «до/после» | Высокий |
| 9 | Разбить сложные tasks на атомарные подзадачи | Средний |
| 10 | Добавить `task-integration_test.md` | Средний |
| 11 | Добавить `task-rpc_server.md` (Phase 2) | Низкий |
