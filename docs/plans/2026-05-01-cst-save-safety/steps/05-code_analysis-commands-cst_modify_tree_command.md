# Шаг 05 — `code_analysis/commands/cst_modify_tree_command.py`

**Исполнитель:** модель кода. Передать в `save_tree_to_file` список операций для replay и обработать новые коды ошибок без порчи файла.

---

## 0. Ссылки (обязательный контекст)

| Что | Ссылка |
|-----|--------|
| Индекс плана | [../README.md](../README.md) |
| Таблица шагов | [README.md](./README.md) |
| Saver с replay-параметром | [04](./04-code_analysis-core-cst_tree-tree_saver.md) |
| Следующий шаг (MCP ответы) | [06](./06-code_analysis-commands-cst_save_tree_command.md) |
| Текущая ветка save | [`cst_modify_tree_command.py` — метод `execute`](../../../../code_analysis/commands/cst_modify_tree_command.py) (grep `save_tree_to_file` в `execute`) |
| Сигнатура save | [`tree_saver.py` — `save_tree_to_file`](../../../../code_analysis/core/cst_tree/tree_saver.py) |
| Откат дерева | [`rollback_tree_to_code`](../../../../code_analysis/core/cst_tree/tree_builder.py) |

---

## 1. Цель шага

В месте вызова `await asyncio.to_thread(save_tree_to_file, ...)`:

- Передать **`tree_operations=tree_operations`** (список уже собранных `TreeOperation` после `build_tree_operations`), если [шаг 04](./04-code_analysis-core-cst_tree-tree_saver.md) добавил этот аргумент.

Обработка ошибок:

- Сейчас при исключении из `save_tree_to_file` делается `rollback_tree_to_code` и возвращается `SuccessResult` с `save_error` ([фрагмент ~248–255](../../../../code_analysis/commands/cst_modify_tree_command.py)).
- Для **`SaveVerificationError`** (из шага 03): извлечь `code` и `details`, по-прежнему откатить дерево, в `data` положить **`save_error_code`** (или использовать единое поле по соглашению с шагом 06), чтобы клиент отличал `FILE_CHANGED_SINCE_LOAD` / `CST_REPLAY_MISMATCH` / `WRITE_VERIFY_FAILED` от обычной валидации.

**Не менять** поведение ветки `preview=True`: там уже `rollback_tree_to_code` в `finally` ([~174–178](../../../../code_analysis/commands/cst_modify_tree_command.py)).

---

## 2. Импорты

- Импортировать `SaveVerificationError` из `..core.cst_tree.tree_save_verification` (имя класса согласовать с шагом 03).

---

## 3. Критерии готовности

- [ ] Один вызов `save_tree_to_file` передаёт `tree_operations` при `project_id` + `file_path` + не preview.
- [ ] При verification failure файл на диске не новее по смыслу изменения дерева (откат в памяти выполнен).
- [ ] `flake8` / `mypy` на файле команды.

---

## 4. Ручная проверка (опционально)

Сценарий: `cst_load_file` → внешне изменить файл → `cst_modify_tree` с save → ожидается отказ с `FILE_CHANGED_SINCE_LOAD` (через MCP или интеграционный тест в шаге 07).

---

## 5. Зависимости

- **Требует:** [шаг 04](./04-code_analysis-core-cst_tree-tree_saver.md).  
- **Разблокирует:** [шаг 06](./06-code_analysis-commands-cst_save_tree_command.md) для унификации кодов в ответах.