# Шаг 7: `tests/test_indexing_worker.py`

**Один файл = один шаг.**

## Статус (аудит плана)

По [README.md](../README.md): шаг **7** **закрыт в коде**; ниже — верификация и контекст.

## Цель

Моки и ожидания **`process_cycle`** согласованы с целевой семантикой шага **1** (`code_analysis/core/indexing_worker_pkg/processing.py`; см. [01-code_analysis-core-indexing_worker_pkg-processing.md](./01-code_analysis-core-indexing_worker_pkg-processing.md)):

- Батч: **`ORDER BY updated_at DESC, id DESC`**.
- Discovery: **`GROUP BY f.project_id`**, **`ORDER BY MAX(f.updated_at) DESC, f.project_id DESC`**.

При необходимости: мок **`execute`** сортирует кандидатов в памяти по **`updated_at`** / **`id`** перед **`[:limit]`**; в фикстурах задать явные **`updated_at`**; проверять порядок вызовов **`index_file`**, а не только множество путей.

## Проверки

- **`pytest tests/test_indexing_worker.py`** после шага 1 и правок этого файла.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 7».
- [PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md) — шаг 7 может идти параллельно векторизационной цепочке при разнесении по PR.
