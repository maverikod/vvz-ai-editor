# Шаг 02 — `code_analysis/core/cst_tree/tree_builder.py`

**Исполнитель:** модель кода. Заполнять поля снимка диска на `CSTTree`, введённые в [шаге 01](./01-code_analysis-core-cst_tree-models.md).

---

## 0. Ссылки (обязательный контекст)

| Что | Ссылка |
|-----|--------|
| Индекс плана | [../README.md](../README.md) |
| Таблица шагов | [README.md](./README.md) |
| Предыдущий шаг (поля дерева) | [01-code_analysis-core-cst_tree-models.md](./01-code_analysis-core-cst_tree-models.md) |
| Следующий шаг (проверки) | [03-code_analysis-core-cst_tree-tree_save_verification.md](./03-code_analysis-core-cst_tree-tree_save_verification.md) |
| `load_file_to_tree` | [`tree_builder.py` ~36–75](../../../../code_analysis/core/cst_tree/tree_builder.py) |
| `create_tree_from_code` | [`tree_builder.py` ~78–113](../../../../code_analysis/core/cst_tree/tree_builder.py) |
| `reload_tree_from_file` | [`tree_builder.py` ~326–388](../../../../code_analysis/core/cst_tree/tree_builder.py) |
| `rollback_tree_to_code` | [`tree_builder.py` ~391+](../../../../code_analysis/core/cst_tree/tree_builder.py) (для контекста: откат не меняет снимок диска до успешного reload) |

---

## 1. Цель шага

При загрузке дерева **с файла** вычислять SHA-256 и длину текста и записывать в `CSTTree`. При создании дерева **без файла** — сбрасывать снимок. При **reload** из файла — пересчитывать снимок.

---

## 2. Единственный редактируемый файл

`code_analysis/core/cst_tree/tree_builder.py`

---

## 3. Алгоритм по функциям

### 3.1 `load_file_to_tree`

- Уже читает файл: `source = path.read_text(encoding="utf-8")` (см. [файл](../../../../code_analysis/core/cst_tree/tree_builder.py)).
- После успешного `CSTTree.create` и до/после `_build_tree_index` — вызвать вспомогательную **локальную** функцию в этом же модуле, например `_attach_disk_snapshot(tree, source: str) -> None`:
  - **Кэшировать encode:** `source_bytes = source.encode("utf-8")`
  - `tree.disk_source_sha256_hex = hashlib.sha256(source_bytes).hexdigest()`
  - `tree.disk_source_length = len(source_bytes)`
  - (НЕ вызывать `encode` дважды — это важно для производительности на больших файлах)
### 3.2 `reload_tree_from_file`

- После `source = path.read_text(...)` и успешного обновления `tree.module` / индекса — снова вызвать `_attach_disk_snapshot(tree, source)`.

### 3.3 `create_tree_from_code`

- Нет чтения с диска: установить `disk_source_sha256_hex = None`, `disk_source_length = 0` (или другое согласованное с [шагом 04](./04-code_analysis-core-cst_tree-tree_saver.md) «нет снимка» значение).

### 3.4 `rollback_tree_to_code` (по согласованию)

- Откат к `original_code` в памяти **не** отражает текущий диск. Варианты (выбрать один и описать в комментарии в коде):
  - **A (рекомендуется):** после `rollback_tree_to_code` сбрасывать снимок в `None`/`0`, чтобы следующий save **не** проходил disk-check до нового `reload_tree_from_file` / `cst_load_file`; или  
  - **B:** пересчитать снимок из переданной строки `code` как «виртуальный диск» — тогда disk-check сравнивает не с файлом (опасно).  
- Для минимального риска в первой итерации выбрать **A** и задокументировать в docstring `rollback_tree_to_code`.

---

## 4. Импорты

- `import hashlib` вверху файла (если ещё нет).

---

## 5. Критерии готовности

- [ ] `load_file_to_tree` + `reload_tree_from_file` задают одинаковый хэш для неизменённого файла при повторном reload.
- [ ] `create_tree_from_code` не оставляет «старый» хэш от предыдущего дерева (всегда новый объект `CSTTree` — ок; если переиспользование — обнулить явно).
- [ ] `flake8` / `mypy` на `tree_builder.py`.
- [ ] Существующие тесты `tree_builder` / `cst_load_file` не сломаны (прогон выборочно или полный `pytest` по времени).

---

## 6. Зависимости

- **Требует:** [шаг 01](./01-code_analysis-core-cst_tree-models.md) выполнен (поля на `CSTTree`).  
- **Разблокирует:** [шаг 03](./03-code_analysis-core-cst_tree-tree_save_verification.md).