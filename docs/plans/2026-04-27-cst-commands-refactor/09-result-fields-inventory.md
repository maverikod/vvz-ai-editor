# Step 09 -- CST edit commands result fields inventory

## Goal
Найти node_id мест где формируется результат каждой CST-команды.
Вернуть node_id + verbatim код execute. Без анализа.

## Коннектор и проект
- Коннектор: code-analysis-server (MCP-proxy)
- Проект: 8772a086-688d-4198-a0c4-f03817cc0e6c

## Шаг 1: найти файлы через search_ast_nodes

```
query="CSTModifyTreeCommand" node_type="class"
query="CSTSaveTreeCommand" node_type="class"
query="ComposeCSTModuleCommand" node_type="class"  (path из шага 05 Q1)
query="QueryCSTCommand" node_type="class"         (path из шага 06 Q1)
```

Q1. Путь + node_id execute для CSTModifyTreeCommand
Формат: path : node_id_execute : номер_строки

Q2. Путь + node_id execute для CSTSaveTreeCommand
Формат: path : node_id_execute : номер_строки

Q3. Путь + node_id execute для ComposeCSTModuleCommand
Формат: path : node_id_execute : номер_строки

Q4. Путь + node_id execute для QueryCSTCommand
Формат: path : node_id_execute : номер_строки

## Шаг 2: для каждой команды

cst_load_file + cst_get_node_info(node_id=execute, include_code=true)

Для каждой команды N (1=CSTModifyTree, 2=CSTSaveTree, 3=ComposeCSTModule, 4=QueryCST):

Q(N).a. Есть ли строка с словом file_written в execute?
Формат: Да/Нет. Если Да -- номер_строки : verbatim

Q(N).b. Есть ли строка с словом preview_only в execute?
Формат: Да/Нет. Если Да -- номер_строки : verbatim

Q(N).c. Есть ли строка с словом backup_uuid в execute?
Формат: Да/Нет. Если Да -- номер_строки : verbatim

Q(N).d. Есть ли строка с словом diff в execute?
Формат: Да/Нет. Если Да -- номер_строки : verbatim

Аналогично применить для N=1,2,3,4.
Выгрузить деревья после каждого файла.

## Формат итогового ответа
Таблица:

```
команда | node_id_execute | file_written | preview_only | backup_uuid | diff
```

Плюс для каждого поля Да -- verbatim строка.
Никаких пояснений, выводов, анализа.
