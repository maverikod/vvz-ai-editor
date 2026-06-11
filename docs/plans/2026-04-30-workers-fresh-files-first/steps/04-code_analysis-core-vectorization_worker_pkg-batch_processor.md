# Шаг 4: `code_analysis/core/vectorization_worker_pkg/batch_processor.py`

**Один файл = один шаг.**

## Статус (аудит плана)

По [README.md](../README.md): шаг **4** **закрыт в коде**; ниже — верификация и контекст.

## Цель

В **`chunk_select_sql`** и в выборке embedding-ready: **`ORDER BY cc.created_at DESC, cc.id DESC`** — в рабочем батче сначала более новые чанки.

## Связи

- **`processing_cycle_projects.py`**: после чанкинга — **`process_embedding_ready_chunks`**.
- **`file_batch_packing.py`** (шаг 5): при необходимости проброс **`updated_at`** в **`file_table`** из SQL этого файла.

## Важно не смешивать оси

- Канон **ASC** для полной пересборки FAISS / **`base_chunks`** **не менять** без отдельного решения (см. цель плана в README: два уровня приоритета).
- **NULL `created_at`:** поведение **`ORDER BY … DESC`** зависит от СУБД (**NULLS FIRST/LAST**).

## Проверки

- **`tests/test_vectorization_uuid_sql_order.py`** (шаг 6) — assert’ы на **`batch_processor`** после целевого DESC.
- **`test_postgres_dml_adapt.py`** — не про ORDER BY стадий; регрессия по своим темам.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 4».
- [PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md) — шаг 4 блокирует шаг 5.
