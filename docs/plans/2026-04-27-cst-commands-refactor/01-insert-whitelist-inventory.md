# Step 01 -- Insert whitelist inventory

## Goal
Собрать факты о whitelist в insert-коде. Без анализа и выводов.

## Коннектор и проект
- Коннектор: code-analysis-server (MCP-proxy)
- Проект: 8772a086-688d-4198-a0c4-f03817cc0e6c

## Файлы
Читать через read_project_text_file по 100 строк за раз:
```
code_analysis/core/cst_tree/tree_modifier_ops_insert.py
code_analysis/core/cst_tree/tree_modifier_ops_find.py
code_analysis/core/cst_tree/tree_modifier.py
```

## Вопросы -- отвечать строго в формате указанном для каждого вопроса

### Файл: tree_modifier_ops_insert.py

Q1. Перечисли все классы в файле.
Формат: ИмяКласса : номер_строки

Q2. Для каждого класса перечисли все методы.
Формат: ИмяКласса.имя_метода : номер_строки

Q3. Скопируй verbatim строки где есть isinstance с типами Module/FunctionDef/ClassDef.
Формат: номер_строки : verbatim

Q4. Есть ли метод on_leave в любом классе?
Формат: Да/Нет. Если Да -- ИмяКласса.on_leave : номер_строки

Q5. Если on_leave есть -- есть ли внутри него вызов super()?
Формат: Да/Нет. Если Да -- номер_строки : verbatim строки с super()

Q6. Есть ли метод leave_IndentedBlock в любом классе?
Формат: Да/Нет. Если Да -- ИмяКласса.leave_IndentedBlock : номер_строки

Q7. Скопируй verbatim строки 50-70.
Формат: номер_строки : verbatim

Q8. Скопируй verbatim строки 380-415.
Формат: номер_строки : verbatim

Q9. Скопируй verbatim текст raise ValueError (все вхождения).
Формат: номер_строки : verbatim

### Файл: tree_modifier_ops_find.py

Q10. Найди функцию find_parent_in_module_by_position.
Формат: номер_строки_начала : номер_строки_конца

Q11. Внутри этой функции -- скопируй verbatim все строки с isinstance.
Формат: номер_строки : verbatim

Q12. Скопируй verbatim тип возвращаемого значения функции find_parent_in_module_by_position.
Формат: verbatim аннотация возврата

### Файл: tree_modifier.py

Q13. Найди функцию _apply_operation.
Формат: номер_строки_начала : номер_строки_конца

Q14. Внутри _apply_operation -- какая функция вызывается для INSERT с parent_node_id?
Формат: имя_функции : номер_строки вызова

Q15. Внутри _apply_operation -- какая функция вызывается для INSERT с target_node_id?
Формат: имя_функции : номер_строки вызова

## Формат итогового ответа
Только Q1...Q15 с ответами. Никаких пояснений, выводов, анализа.
