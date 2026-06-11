# Шаг 1a: `tests/test_processing_paused_projects.py`

**Один файл = один шаг.** Только этот путь; правки через сервер по политике репозитория (CST / backup / validate).

## Статус

По [README.md](../README.md): шаг **к выполнению** — два новых теста с фиксированными именами и assert’ами на подстроки SQL.

## Цель

Зафиксировать в тестах семантику «свежести» в константах **`INDEXING_PROJECT_DISCOVERY_SQL`** и **`PROJECTS_PENDING_SQL`**:

| Тест | Проверяемые подстроки (концептуально) |
|------|----------------------------------------|
| **`test_indexing_discovery_sql_orders_by_freshness`** | **`GROUP BY`**, **`ORDER BY`**, **`MAX(`**, **`updated_at`** в **`INDEXING_PROJECT_DISCOVERY_SQL`**. |
| **`test_projects_pending_sql_orders_by_freshness`** | **`max_file_updated_at`**, **`ORDER BY`**, **`updated_at`** в **`PROJECTS_PENDING_SQL`**. |

Существующие тесты на **`processing_paused`** / **`INNER JOIN`** **не удалять**.

## Вставка в AST (не по номеру строки)

1. **`cst_load_file`** → `tree_id`.
2. **`cst_find_node`**: `search_type: simple`, имя **`test_indexing_discovery_sql_filters_processing_paused`**.
3. **`cst_modify_tree`**: `action: insert`, **`position: after`** целевой функции; тело двух новых тестов в **`code_lines`**.
4. **`cst_save_tree`**: `validate`, `backup` по правилам репозитория.

## Качество и прогон

- **`lint_code`** → **`format_code`** → **`type_check_code`** для этого файла ([docs/AI_TOOL_USAGE_RULES.md](../../../AI_TOOL_USAGE_RULES.md)).
- **`run_project_module`**: `pytest tests/test_processing_paused_projects.py -v` с **`timeout_seconds`** (например **120**).

## Критерий готовности

- **8** зелёных тестов: **6** существующих + **2** новых (не формулировка «6, включая 2 новых»).

## Зависимости

- Логически после стабилизации текста **`INDEXING_PROJECT_DISCOVERY_SQL`** (шаг 1) и **`PROJECTS_PENDING_SQL`** (шаг 2); см. [PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md).

## См. также

- [README.md](../README.md) — приложение «исправления» (таблица: точка вставки AST, число тестов, таймаут `run_project_module`).
- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 1a».
