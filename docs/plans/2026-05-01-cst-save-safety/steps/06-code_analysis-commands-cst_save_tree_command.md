# Шаг 06 — `code_analysis/commands/cst_save_tree_command.py`

**Исполнитель:** модель кода. Пробросить коды ошибок верификации к клиенту MCP и обновить схему/help при необходимости.

---

## 0. Ссылки (обязательный контекст)

| Что | Ссылка |
|-----|--------|
| Индекс плана | [../README.md](../README.md) |
| Таблица шагов | [README.md](./README.md) |
| Исключения / коды | [03](./03-code_analysis-core-cst_tree-tree_save_verification.md) |
| Saver | [04](./04-code_analysis-core-cst_tree-tree_saver.md) |
| Параллельная ветка modify+save | [05](./05-code_analysis-commands-cst_modify_tree_command.md) |
| Тесты | [07](./07-tests-test_cst_save_verification.md) |
| Команда | [`cst_save_tree_command.py`](../../../../code_analysis/commands/cst_save_tree_command.py) |
| Metadata для AI | В том же файле: метод `metadata` ([~454+](../../../../code_analysis/commands/cst_save_tree_command.py)) — словарь с `detailed_description`; обновить текст при добавлении кодов ошибок. |

---

## 1. Цель шага

1. В `execute` команды `cst_save_tree`: перехватить `SaveVerificationError` из `save_tree_to_file`. **Зафиксировано: стиль ошибок = исключения** (saver бросает `SaveVerificationError`, команда ловит).

2. Возвращать клиенту **`ErrorResult`** с:
   - `code` = строка кода (`FILE_CHANGED_SINCE_LOAD`, `CST_REPLAY_MISMATCH`, `WRITE_VERIFY_FAILED`),
   - `details` с `tree_id`, `file_path`, при необходимости `expected_sha` / `actual_sha` (без огромных тел файлов).

3. Обновить **`get_schema`** в этом же файле: краткое описание новых ошибок в `description` блока команды или в описании поля `validate` — не дублировать простыню; ссылка на поведение «файл изменён с момента load».

4. Если в проекте для команды есть **metadata** для AI — синхронизировать тексты с `get_schema`.

---

## 2. Особенность `cst_modify_tree`

Там при ошибке save часто возвращается **`SuccessResult` с `save_error`** ([см. modify](../../../../code_analysis/commands/cst_modify_tree_command.py)). В шаге 05 уже добавляют код. В этом шаге для **`cst_save_tree`** предпочтительно **`ErrorResult`** для verification errors — единообразие с другими фатальными сбоями.

---

## 3. Критерии готовности

- [ ] Клиент MCP по `call_server` получает структурированный `code` для трёх сценариев верификации.
- [ ] Нет регрессии retry DB ([`transient`](../../../../code_analysis/core/database_client/transient.py)) — не трогать блоки retry без необходимости.
- [ ] `flake8` / `mypy` на изменённых файлах.

---

## 4. Зависимости

- **Требует:** [04](./04-code_analysis-core-cst_tree-tree_saver.md) (контракт ошибок), желательно [05](./05-code_analysis-commands-cst_modify_tree_command.md) для согласования имён полей с modify.  
- **Параллельно с:** [07](./07-tests-test_cst_save_verification.md).