# Шаг 5: `code_analysis/core/vectorization_worker_pkg/file_batch_packing.py`

**Один файл = один шаг.**

## Статус (аудит плана)

По [README.md](../README.md): шаг **5** **закрыт в коде**; ниже — верификация и контекст.

## Цель

Вторичный ключ при упаковке: по **`updated_at DESC`** при равном числе чанков; данные **`updated_at`** согласованы с передачей из **`batch_processor`** (шаг 4).

## Связи

| Что | Где |
|-----|-----|
| Алгоритм | этот файл |
| Единственный продакшн-caller | **`batch_processor.process_chunks_missing_embedding_params`** |
| Тесты | **`tests/test_file_batch_packing.py`** |

## Риски

- Расширение типа строк (**четвёрки** с `updated_at` vs наружные тройки) — не смешивать с правками **`batch_processor`** в одном шаге; при смене контракта распаковки это два шага по двум файлам.

## Проверки

- **`pytest tests/test_file_batch_packing.py`**.
- Сценарии: равный count, разный **`updated_at`**; третичный tie-break при необходимости.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 5».
- При продуктовом обновлении описания алгоритма — отдельное решение по **`docs/VECTORIZATION_BATCHING_ALGORITHM.md`** (вне scope текущего README).
