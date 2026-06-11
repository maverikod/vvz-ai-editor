# Шаг 07 — `tests/test_cst_save_verification.py` (**новый файл**)

**Исполнитель:** модель кода. Закрепить поведение [шага 03](./03-code_analysis-core-cst_tree-tree_save_verification.md) и интеграцию с [04](./04-code_analysis-core-cst_tree-tree_saver.md) там, где возможно без тяжёлого MCP.

---

## 0. Ссылки (обязательный контекст)

| Что | Ссылка |
|-----|--------|
| Индекс плана | [../README.md](../README.md) |
| Таблица шагов | [README.md](./README.md) |
| Модуль проверок | [03](./03-code_analysis-core-cst_tree-tree_save_verification.md) |
| Saver | [04](./04-code_analysis-core-cst_tree-tree_saver.md) |
| Примеры тестов CST | [`tests/test_cst_load_file_command.py`](../../../../tests/test_cst_load_file_command.py); grep `save_tree_to_file` в [`tests/`](../../../../tests/) |
| Правила тестов | [docs/PROJECT_RULES.md](../../../PROJECT_RULES.md) |

---

## 1. Цель шага

Новый файл: `tests/test_cst_save_verification.py`.

Минимальный набор кейсов:

| # | Тест | Ожидание |
|---|------|----------|
| 1 | `disk_matches_tree_snapshot` — файл совпадает с хэшем на дереве | `True` |
| 2 | Файл на диске изменён после снимка | `assert_disk_matches...` кидает / возвращает ошибку с кодом `FILE_CHANGED_SINCE_LOAD` |
| 3 | Replay: валидные ops на простом модуле | результат replay **равен** `tree.module.code` после `modify_tree` на основном дереве (см. шаг 03: аккуратно с `remove_tree` для временного id) |
| 4 | Replay: намеренно несовместимые ops (или мок) | `CST_REPLAY_MISMATCH` |
| 5 | После успешного `os.replace` в изолированном `tmp_path` | readback совпадает (если saver тестируется через thin wrapper — мок `database` как в других тестах проекта) |
| 6 | **Save → повторный save без reload** | Второй save **успешен** (снимок обновлён в шаге 04 после первого save); если нет — регрессия A1 из REVIEW |
**База:** `pytest`, `tmp_path`, без обращения к `test_data` через read_file (если не нужен реальный проект).

---

## 2. Моки БД для `save_tree_to_file`

Смотреть существующие тесты, вызывающие `save_tree_to_file` или `CSTSaveTreeCommand` с `MagicMock` для `database` — скопировать **паттерн** из репозитория (grep `save_tree_to_file` в `tests/`).

---

## 3. Критерии готовности

- [ ] `pytest tests/test_cst_save_verification.py -q` зелёный.
- [ ] `flake8` / `mypy` на новом файле (если mypy на тестах включён в репо).

---

## 4. Зависимости

- **Требует:** шаги **03–04** (код существует). Шаги 05–06 могут завершаться параллельно; при изменении контракта ошибок — обновить assert’ы.

---

## 5. Не входит в шаг

Полный E2E через MCP Proxy — вне объёма; при необходимости отдельная ручная проверка по [индексу](../README.md).