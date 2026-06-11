# Шаг 2: `code_analysis/core/vectorization_worker_pkg/processing_cycle.py`

**Один файл = один шаг.**

## Статус (аудит плана)

По [README.md](../README.md): шаг **2** **закрыт в коде**; ниже — верификация и контекст.

## Цель

- В выборке pending-проектов — столбец **`max_file_updated_at`** (подзапрос **`MAX(f2.updated_at)`** по активным файлам проекта, согласованный с тем же набором ограничений, что и доменная логика pending).
- **Фиксированный порядок:** **`ORDER BY max_file_updated_at DESC, pending_count ASC, p.id DESC`**.

## Связи

- Вызов **`run_one_cycle`**: **`vectorization_worker_pkg/processing.py`**.
- **`PROJECTS_PENDING_SQL`**: этот файл + **`tests/test_processing_paused_projects.py`** (шаг 1a).

## Риски

- Тяжесть запроса; типы времени SQLite/PostgreSQL; **`processing_paused`** по-прежнему исключает проекты.

## Проверки

- **`test_processing_paused_projects.py`**, тесты векторизационного воркера.
- Два+ проекта с pending и разной свежестью — согласованный порядок `project_id`.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 2».
- [PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md) — волна 1 (параллельно с шагами 1 и 3 по файлам).
