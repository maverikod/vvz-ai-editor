# Шаги плана «воркеры — сначала свежие файлы»

Один шаг — один целевой путь (или верификация без файла в шаге 0) — один файл описания ниже. Сводный контекст: [../README.md](../README.md), детализация 1–8: [../step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md).

| Шаг | Целевой путь / артефакт | Описание |
|-----|-------------------------|----------|
| 0 | (MCP, не файл репо) | [00-verification-list_projects.md](./00-verification-list_projects.md) |
| 1 | `code_analysis/core/indexing_worker_pkg/processing.py` | [01-code_analysis-core-indexing_worker_pkg-processing.md](./01-code_analysis-core-indexing_worker_pkg-processing.md) |
| 1a | `tests/test_processing_paused_projects.py` | [01a-tests-test_processing_paused_projects.md](./01a-tests-test_processing_paused_projects.md) |
| 2 | `code_analysis/core/vectorization_worker_pkg/processing_cycle.py` | [02-code_analysis-core-vectorization_worker_pkg-processing_cycle.md](./02-code_analysis-core-vectorization_worker_pkg-processing_cycle.md) |
| 3 | `code_analysis/core/vectorization_worker_pkg/processing_cycle_projects.py` | [03-code_analysis-core-vectorization_worker_pkg-processing_cycle_projects.md](./03-code_analysis-core-vectorization_worker_pkg-processing_cycle_projects.md) |
| 4 | `code_analysis/core/vectorization_worker_pkg/batch_processor.py` | [04-code_analysis-core-vectorization_worker_pkg-batch_processor.md](./04-code_analysis-core-vectorization_worker_pkg-batch_processor.md) |
| 5 | `code_analysis/core/vectorization_worker_pkg/file_batch_packing.py` | [05-code_analysis-core-vectorization_worker_pkg-file_batch_packing.md](./05-code_analysis-core-vectorization_worker_pkg-file_batch_packing.md) |
| 6 | `tests/test_vectorization_uuid_sql_order.py` | [06-tests-test_vectorization_uuid_sql_order.md](./06-tests-test_vectorization_uuid_sql_order.md) |
| 7 | `tests/test_indexing_worker.py` | [07-tests-test_indexing_worker.md](./07-tests-test_indexing_worker.md) |
| 8 | `docs/reports/2026-04-30-vectorizer-indexer-queue-priority-analysis.md` | [08-docs-reports-2026-04-30-vectorizer-indexer-queue-priority-analysis.md](./08-docs-reports-2026-04-30-vectorizer-indexer-queue-priority-analysis.md) |

Карта параллелизации: [../PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md).
