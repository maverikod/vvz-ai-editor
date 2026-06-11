# Шаг 04 — `code_analysis/core/cst_tree/tree_saver.py`

**Исполнитель:** модель кода. Встроить проверки из [шага 03](./03-code_analysis-core-cst_tree-tree_save_verification.md) в единый путь **`save_tree_to_file`**.

---

## 0. Ссылки (обязательный контекст)

| Что | Ссылка |
|-----|--------|
| Индекс плана | [../README.md](../README.md) |
| Таблица шагов | [README.md](./README.md) |
| Модуль проверок | [03](./03-code_analysis-core-cst_tree-tree_save_verification.md) → файл `tree_save_verification.py` |
| Следующий шаг | [05](./05-code_analysis-commands-cst_modify_tree_command.md) |
| Текущая реализация save | [`tree_saver.py` — `save_tree_to_file`](../../../../code_analysis/core/cst_tree/tree_saver.py) (блок `with file_lock`, генерация `source_code`, `os.replace`) |
| Блокировка файла | [`file_lock`](../../../../code_analysis/core/file_lock.py) |
| Вызовы save из команды | [`cst_modify_tree_command.py` ~236–266](../../../../code_analysis/commands/cst_modify_tree_command.py) |

---

## 1. Цель шага

Внутри `save_tree_to_file`:

1. После `get_tree` и резолва `target_path`, **до** бэкапа: если у дерева задан снимок и `target_path.exists()` — вызвать `assert_disk_matches_tree_snapshot` из шага 03.  
2. После вычисления финальной строки `source_code` (уже с `append_persisted_node_ids`, как сейчас), **до** записи temp: опционально вызвать replay — см. раздел 2 (разведение ответственности с шагом 05).  
3. После `os.replace`: `assert_file_bytes_match(target_path=target_path, expected=source_code)` (или сравнивать с тем же байтовым представлением, что писали).

При любой ошибке проверки: **не** выполнять `os.replace`; поднять исключение с кодом из `SaveVerificationError`, чтобы [шаг 05](./05-code_analysis-commands-cst_modify_tree_command.md) сделал `rollback_tree_to_code`.

---

## 2. Replay: где вызывать (зафиксировать один вариант)

**Выбранная политика для плана (минимум дублирования):**

- **`save_tree_to_file`** расширить опциональным аргументом `tree_operations: Optional[Sequence[TreeOperation]] = None`.  
- Если `tree_operations is not None` и не пусто — внутри saver вызвать `assert_replay_matches(...)` из шага 03 (перед записью temp).  
- Если `None` — только disk-snapshot + post readback (совместимость с `cst_save_tree` без списка ops).

**Обязанность передавать ops:** [шаг 05](./05-code_analysis-commands-cst_modify_tree_command.md) при вызове `save_tree_to_file` из ветки modify+save передаёт тот же `tree_operations`, что уже применён к дереву.

**`cst_save_tree`** обычно вызывает save **без** ops → replay в saver пропускается; тогда целостность держащаяся на том, что дерево уже финальное (клиент сам отвечает за последовательность modify).

---

## 3. Порядок внутри `with file_lock(target_path)`

Уточнить на коде:

1. Disk snapshot check.  
2. Backup (как сейчас).  
3. Построить `source_code`.  
4. Replay (если ops переданы).  
5. Write `.tmp`, validate temp, `os.replace`.  
6. Readback verify.  
7. **Обновить снимок диска на дереве:** `_attach_disk_snapshot(tree, source_code)` (импорт из `tree_builder` или прямое присвоение `tree.disk_source_sha256_hex` / `tree.disk_source_length`). **Критично:** без этого повторный save без reload приведёт к ложному `FILE_CHANGED_SINCE_LOAD`.  
8. Остальная логика (DB, sync) — без изменения порядка, если возможно; при падении readback — использовать существующий механизм отката из бэкапа в этом же файле (если уже есть — следовать; если нет — добавить минимальный откат и лог `logger.critical`).

---

## 4. Критерии готовности
- [ ] Новый параметр `tree_operations` не ломает существующие вызовы (default `None`).
- [ ] При несовпадении диска исключение с кодом `FILE_CHANGED_SINCE_LOAD` до бэкапа/записи.
- [ ] После `os.replace` несовпадение readback → `WRITE_VERIFY_FAILED` + лог + откат из бэкапа по политике файла.
- [ ] После успешного readback: снимок диска на дереве обновлён на хэш записанного `source_code`.
- [ ] `flake8` / `mypy` на `tree_saver.py`.

---

## 5. Зависимости

- **Требует:** [шаг 03](./03-code_analysis-core-cst_tree-tree_save_verification.md).  
- **Разблокирует:** [шаг 05](./05-code_analysis-commands-cst_modify_tree_command.md) (передача `tree_operations`).