# Audit: Plan execution status — mcp-db-rpc-priority-lanes

**Date:** 2026-05-01 (обновление сводки кода: 2026-05-01)
**Plan:** `docs/plans/2026-04-30-mcp-db-rpc-priority-lanes/README.md`
**Сверка с task-файлами:** `corrections/REVIEW_TASKS_VS_PLAN.md` — там разобрано, какие `task-*.md` устарели относительно текущего кода.

---

## Согласованность: план README ↔ этот аудит

Таблица «Статус после аудита corrections/» в [README.md](../README.md) по шагам **1–7** фазы 1 **согласована с текущим кодом**. Ниже — детализация и остатки вне «закрытых шагов».

---

## Phase 1 step completion status (код)

| Step | Description | Status | Notes |
|------|-------------|--------|-------|
| 1 | `priority` in `RPCRequest` | ✅ DONE | `rpc_protocol.py`: поле, `to_dict` / `from_dict`; тесты round-trip |
| 2 | Pool 3W+2R in `PostgreSQLDriver` | ✅ DONE | `postgres_connection_pool.py`: `max_wait_seconds` (дефолт 30), `snapshot()` с `in_use` / `idle` / `waiters`; таймаут ожидания слота → `DriverOperationError` |
| 2a | In-process lock narrowed | ✅ DONE | `in_process_rpc_client.py`: под lock только проверка `_closed`; `process_rpc_request` вне lock |
| 3 | Tag indexing_worker | ✅ DONE | `BACKGROUND_WORKER_DB_RPC_PRIORITY` из `worker_db_rpc_priority.py`; `execute` / `execute_batch` / `index_file` / health `SELECT 1` |
| 4 | Tag vectorization_worker | ✅ DONE | Тот же импорт константы; литералов `priority=1` в пакете нет |
| 4b | (доп. к плану) file watcher | ✅ DONE | Фоновые `execute` / `execute_batch` / `select` вочера помечены той же константой (`processor_queue`, `multi_project_worker*`, и т.д.) |
| 5 | Transactions vs pool | ✅ DONE | Явные RPC-транзакции на выделенном `conn`; self-managed — пул |
| 6 | Observability | ✅ DONE | `get_database_status_build._postgres_pool_observability_fields`: `pg_*_in_use`, `pg_*_idle`, `pg_*_waiters`; драйвер: `pool_max_wait_seconds` |
| 7 | Tests | ⚠️ MOSTLY | Юнит: пул (в т.ч. waiters, read при занятых write), протокол `priority`, `test_get_database_status_pool_observability.py`. Опционально: live `test_live_pg_pool_*` при `CODE_ANALYSIS_POSTGRES_TEST_DSN`. **Нет** отдельного автоматического интеграционного теста «полный MCP + оба воркера под нагрузкой + list_projects &lt; 2s» (критерий приёмки п.1–2 — продуктовая/CI проверка, не закрыта одним pytest в репо). |

---

## Paradigm compliance

| Rule | Status |
|------|--------|
| Pool in `PostgreSQLDriver`, not `DatabaseClient` | ✅ |
| Universal layer: no queues / artificial delays | ✅ |
| Read/write lane in driver (`postgres_execute_lane.py`) | ✅ |
| No priority logic in `rpc_dispatch.py` | ✅ |
| SQLite subprocess unchanged in phase 1 | ✅ |

---

## Code quality (вне scope закрытия фазы 1 по README)

| File | Approx. lines | Limit 400 | Note |
|------|---------------|-----------|------|
| `batch_processor.py`, indexing `processing.py`, `postgres.py`, `client_operations.py`, `get_database_status_build.py`, … | >400 | 400 | Техдолг: дробление отдельными задачами; см. `REVIEW_TASKS_VS_PLAN.md` |

---

## Остаточные риски / не в «шагах 1–7»

1. **`_reconnect_main` и пул** — при потере основного `conn` пул пересоздаётся; ожидающие в `acquire()` получают ошибки. Задокументировано в плане как ожидаемая сложность; улучшения (graceful drain, F-02 в ревью) — отдельно.
2. **`julianday('now')` в SQL вочера/индексатора** — для чистого PostgreSQL часть запросов должна идти через портable выражения (`sql_julian_timestamp_now_expr` и аналоги); отдельный аудит в `task-indexing_processing.md` / циклы вочера.
3. **Приёмка плана п.1–3** (`list_projects` &lt; 2s, нет таймаута при нормальной нагрузке, throughput индексирования) — не заменяются юнит-тестами; нужны прогон на стенде / CI с PG.
4. **`RPCRequest.priority` на in-process PG** — в основном телеметрия / заготовка; выбор пула по SQL, не по полю. Ок для фазы 1; фаза 2 (SQLite wire) — отдельно.
5. **Task-файлы `task-*.md`** — часть содержит устаревшие формулировки (см. **REVIEW_TASKS_VS_PLAN.md**); на статус **кода** это не влияет.

---

## Task files (исполнителю)

| Task file | Назначение | Примечание |
|-----------|------------|------------|
| `REVIEW_TASKS_VS_PLAN.md` | Актуальность corrections относительно кода | Читать перед запуском Qwen по старым task |
| `task-*.md` | Были черновиками под построчные правки | Часть **устарела**; не использовать как единственный источник правды |

---

## История правок этой сводки

- Ранее в `AUDIT_SUMMARY_1.md` ошибочно значилось: нет таймаута в пуле, нет waiters/idle в observability, vectorization с «магической единицей». По текущему репозиторию это **исправлено в коде**.
- Детальный разбор расхожений task-файлов ↔ кода: **`REVIEW_TASKS_VS_PLAN.md`**.
