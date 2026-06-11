# Шаг 1: `code_analysis/core/indexing_worker_pkg/processing.py`

**Один файл = один шаг.** Правки других путей в рамках этого шага не смешивать.

## Статус (аудит плана)

По [README.md](../README.md): шаг **1** в целевом виде **уже реализован** в коде; файл ниже — **чеклист верификации и контекст**, а не обязательный бэклог правок, пока повторный аудит не покажет расхождение.

## Цель

1. **Уровень файла (`files.updated_at`):** батч файлов с `needs_chunking = 1` — **`ORDER BY updated_at DESC, id DESC LIMIT ?`** (сначала более свежие строки, стабильный tie-break по `id`).
2. **Discovery проектов (`INDEXING_PROJECT_DISCOVERY_SQL`):** **`GROUP BY f.project_id`** и **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`**.

## Что проверить в коде

- Константы SQL совпадают с формулировками в [README.md](../README.md).
- Докстринг **`process_cycle`** и комментарии к SQL описывают **DESC** и роль **`id`** / discovery, а не устаревший ASC-only текст.
- Условия **`WHERE`** (в т.ч. через **`sql_portable`**) эквивалентны прежней логике фильтрации.

## Связи

- Запуск: **`indexing_worker_pkg/runner.py`**.
- Тесты: **`tests/test_indexing_worker.py`** (шаг 7), **`tests/test_processing_paused_projects.py`** (шаг 1a — подстроки SQL).

## Риски

- Меняется очередность индексации при ограниченном `batch_size` (**starvation** старых хвостов — осознанный компромисс, см. README).
- **`ORDER BY id DESC`** для UUID — не порядок по времени создания записи.

## Проверки

- **`pytest tests/test_indexing_worker.py`**, **`pytest tests/test_processing_paused_projects.py`** (после шага 1a при добавлении assert’ов).
- SQLite и при использовании — PostgreSQL.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 1».
- [PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md) — волна 1.
