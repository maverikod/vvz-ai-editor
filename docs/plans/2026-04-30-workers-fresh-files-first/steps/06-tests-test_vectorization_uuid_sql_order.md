# Шаг 6: `tests/test_vectorization_uuid_sql_order.py`

**Один файл = один шаг.**

## Статус (аудит плана)

По [README.md](../README.md): шаг **6** **закрыт в коде**; ниже — верификация и контекст.

## Цель

Регрессия порядка SQL для **рабочих** путей **`batch_processor`**: **`ORDER BY cc.created_at DESC, cc.id DESC`** (через **`inspect.getsource`** или эквивалентные проверки, согласованные с фактическим f-string/пробелами в коде).

## Не ломать канон rebuild

- Существующие assert’ы на **ASC** для **`faiss_manager_rebuild`** / **`base_chunks`** / **`ROW_NUMBER() OVER (ORDER BY created_at, id)`** **не менять**, пока в тех модулях не меняется канон полной пересборки.

## Связи

- Логически после шага **4** (целевой DESC в **`batch_processor`**); шаг **5** желателен до финальной проверки упаковки; см. [PARALLELIZATION_MAP.md](../PARALLELIZATION_MAP.md).

## Проверки

- **`pytest tests/test_vectorization_uuid_sql_order.py -v`** — зелёный.

## См. также

- [step_descriptions_1-8_orchestrated.md](../step_descriptions_1-8_orchestrated.md) — «Шаг 6».
