# Step 03 -- Replace in IndentedBlock investigation

## Goal
Найти node_id узлов связанных с REPLACE и INVALID_OPERATION.
Вернуть node_id + verbatim код ключевых блоков. Без анализа.

## Коннектор и проект
- Коннектор: code-analysis-server (MCP-proxy)
- Проект: 8772a086-688d-4198-a0c4-f03817cc0e6c

## Шаг 1: загрузить файлы

Загрузить через cst_load_file (return_format=declarative):
```
code_analysis/core/cst_tree/tree_modifier.py
code_analysis/core/mutable_cst/edits.py
```

## Шаг 2: найти узлы

Для каждого файла использовать cst_find_node с search_type=name.

### tree_modifier.py

Q1. node_id функции _apply_operation
Формат: node_id : номер_строки

Q2. Через cst_get_node_info(node_id=Q1, include_code=true) --
найди внутри кода все строки содержащие слово REPLACE.
Формат: номер_строки : verbatim

Q3. Через cst_get_node_info(node_id=Q1, include_code=true) --
найди все строки содержащие слово INVALID_OPERATION.
Формат: номер_строки : verbatim

Q4. Через cst_get_node_info(node_id=Q1, include_code=true) --
найди все строки с isinstance где проверяется тип целевого узла для REPLACE.
Формат: номер_строки : verbatim

### edits.py

Q5. node_id функции apply_operations
Формат: node_id : номер_строки

Q6. node_id функции _replace_node_source
Формат: node_id : номер_строки

Q7. Через cst_get_node_info(node_id=Q6, include_code=true) --
верни полный код функции verbatim.
Формат: номер_строки_начала : номер_строки_конца : verbatim

Q8. Через cst_get_node_info(node_id=Q5, include_code=true) --
найди все строки содержащие слово REPLACE или TreeOperationType.REPLACE.
Формат: номер_строки : verbatim

Q9. Через cst_get_node_info(node_id=Q5, include_code=true) --
найди все строки содержащие слово INVALID_OPERATION.
Формат: Да/Нет. Если Да -- номер_строки : verbatim

## Шаг 3: выгрузить деревья

cst_unload_tree для обоих загруженных деревьев.

## Формат итогового ответа
Только Q1...Q9 с ответами. Никаких пояснений, выводов, анализа.
