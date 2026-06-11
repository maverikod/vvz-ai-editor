# Шаг 3: `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py`

**Один файл = один шаг.**

## Статус (аудит плана)

По [README.md](../README.md): шаг **3** **закрыт в коде**; ниже — верификация и контекст.

## Цель

Перед **`LIMIT ?`** в выборке файлов на docstring-чанкинг: **`ORDER BY f.updated_at DESC, f.id DESC`** — свежие файлы первыми, стабильный tie-break.

## Связи

- Вызывающий: **`processing_cycle.run_one_cycle`**.
- Тесты (при падениях после изменений): **`test_vectorization_project_cycle_stages.py`**, **`test_vectorization_chunking_without_svo.py`** — отдельные шаги только если понадобятся правки в этих файлах.

## Риски

- **Starvation** старых хвостов при потоке свежих правок.
- Индексы: **`idx_files_needs_indexing`**, **`idx_files_updated_at`** — влияние на план запроса.

## Проверки

- Несколько кандидатов с разными **`updated_at`** и малым **`max_files_per_pass`** — ожидаемый порядок.
- black / flake8 / mypy; при матрице — оба драйвера.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 3».
- Шаг **8** — актуализировать цитату SQL в отчёте с **`ORDER BY`** перед **`LIMIT`**.
