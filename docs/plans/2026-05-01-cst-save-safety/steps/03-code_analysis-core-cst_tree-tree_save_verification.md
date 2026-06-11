# Шаг 03 — `code_analysis/core/cst_tree/tree_save_verification.py` (**новый файл**)

**Исполнитель:** модель кода. Создать модуль с **чистыми** функциями проверок (минимум зависимостей от MCP/БД).

---

## 0. Ссылки (обязательный контекст)

| Что | Ссылка |
|-----|--------|
| Индекс плана | [../README.md](../README.md) |
| Таблица шагов | [README.md](./README.md) |
| Поля снимка на дереве | [01](./01-code_analysis-core-cst_tree-models.md) + [02](./02-code_analysis-core-cst_tree-tree_builder.md) |
| Следующий шаг (вызов из saver) | [04-code_analysis-core-cst_tree-tree_saver.md](./04-code_analysis-core-cst_tree-tree_saver.md) |
| Применение операций к дереву | [`tree_modifier.py` — `modify_tree`](../../../../code_analysis/core/cst_tree/tree_modifier.py) |
| Модели операций | [`models.py` — `TreeOperation`](../../../../code_analysis/core/cst_tree/models.py) |
| Построение дерева из кода | [`tree_builder.py` — `create_tree_from_code`](../../../../code_analysis/core/cst_tree/tree_builder.py) |

---

## 1. Цель шага

Один новый файл с функциями:

1. **Проверка диска vs снимок** перед записью.  
2. **Replay:** повторное применение того же списка `TreeOperation` к исходному тексту и сравнение сериализации с рабочим деревом.  
3. **Пост-проверка записи:** прочитанный с диска файл равен ожидаемой строке.

Исключить циклические импорты: этот модуль **не** должен импортировать `tree_saver.py`.

---

## 2. Создаваемый путь

`code_analysis/core/cst_tree/tree_save_verification.py`

**Не** обязательно добавлять экспорт в [`__init__.py`](../../../../code_analysis/core/cst_tree/__init__.py) — достаточно импорта из `tree_saver` / команд.

---

## 3. Публичный API (зафиксировать имена)

Рекомендуемые сигнатуры (уточнить типы по стилю репо):

```python
def disk_matches_tree_snapshot(target_path: Path, tree: "CSTTree") -> bool:
    """False if tree has no snapshot or file missing. True if sha matches."""

def assert_disk_matches_tree_snapshot(target_path: Path, tree: "CSTTree") -> None:
    """Raise SaveVerificationError(code=FILE_CHANGED_SINCE_LOAD, ...) if mismatch."""

def replay_operations_produce_code(
    original_source: str,
    tree_operations: Sequence["TreeOperation"],
) -> str:
    """Parse original_source, modify_tree on NEW tree_id, return module.code."""

def assert_replay_matches(
    *,
    original_source: str,
    target_path: Path,
    tree: "CSTTree",
    tree_operations: Sequence["TreeOperation"],
) -> None:
    """
    original_source is the verified disk text (from disk snapshot check).
    replay_operations_produce_code(original_source, ops) must equal tree.module.code
    (after normalizing line endings if policy says so — default: strict equality).
    Raise SaveVerificationError(code=CST_REPLAY_MISMATCH, ...).
    Uses try/finally to ensure temporary replay tree is always removed from _trees.
    """

def assert_file_bytes_match(*, target_path: Path, expected: str) -> None:
    """After os.replace: read_text must equal expected; else WRITE_VERIFY_FAILED."""
```

Класс исключения (в этом же файле), например `SaveVerificationError(Exception)` с полями `code: str`, `details: dict`.

**Коды строк** (согласовать с [шагом 06](./06-code_analysis-commands-cst_save_tree_command.md)):

- `FILE_CHANGED_SINCE_LOAD`
- `CST_REPLAY_MISMATCH`
- `WRITE_VERIFY_FAILED`

---

## 4. Реализация replay (важно)

- Взять **текст**: передан `original_source: str` (шаг 04 читает файл один раз при disk snapshot check и передаёт сюда; **не** читать диск повторно, чтобы не замедлять критический участок под lock).
- Создать дерево: `create_tree_from_code(str(target_path), original_source, ...)` — получится новый `tree_id` в глобальном реестре `_trees`.
- **Обязательно обернуть replay в `try/finally`** с `remove_tree(new_id)` в `finally`-блоке, чтобы временное дерево всегда удалялось из `_trees`, даже при исключении в `modify_tree`.
- Применить: `modify_tree(new_tree_id, list(tree_operations))` — как в [команде modify](../../../../code_analysis/commands/cst_modify_tree_command.py).
- Сравнить `get_tree(new_id).module.code` с **рабочим** `tree.module.code` (рабочее дерево — то, что уже мутировало в запросе).

**Альтернатива без второго tree_id:** парсить `cst.parse_module(original_source)` и вызывать нижний слой модификатора — только если это меньше кода и не дублирует логику; иначе придерживаться `create_tree_from_code` + `modify_tree` + `remove_tree`.

---

## 5. Критерии готовности

- [ ] Файл создан, нет циклических импортов с `tree_saver`.
- [ ] Юнит-тесты будут в [шаге 07](./07-tests-test_cst_save_verification.md); в этом шаге можно оставить `# pragma` только если репо запрещает — лучше без pragma.
- [ ] `flake8` / `mypy` на новом файле.

---

## 6. Зависимости

- **Требует:** [01](./01-code_analysis-core-cst_tree-models.md), [02](./02-code_analysis-core-cst_tree-tree_builder.md).  
- **Разблокирует:** [04](./04-code_analysis-core-cst_tree-tree_saver.md).