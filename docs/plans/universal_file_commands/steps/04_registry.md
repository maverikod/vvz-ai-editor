# Step 04: registry.py — валидация и .log suffix

Status: TODO  
Depends on: Step 02  
File: `code_analysis/core/file_handlers/registry.py` (199 строк)

## Что делать

Две изолированные задачи:

1. Срешивание `TEXT_SUFFIXES` в `text_handler.py` и `_DEFAULT_SUFFIX_MAP` в `registry.py`
   (`.log` есть в `text_handler.TEXT_SUFFIXES`, но **нет** в `_DEFAULT_SUFFIX_MAP`)
2. `validate_supported()` не возвращает handler_id в details для `UNSUPPORTED_FILE_EXTENSION`

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/core/file_handlers/registry.py start_line=1 end_line=199
read_project_text_file code_analysis/core/file_handlers/text_handler.py start_line=1 end_line=35
```

## Текущее состояние (factual)

```python
# registry.py строки 22-33
_DEFAULT_SUFFIX_MAP: Dict[str, str] = {
    ".md": HANDLER_TEXT, ".txt": HANDLER_TEXT,
    ".rst": HANDLER_TEXT, ".adoc": HANDLER_TEXT,
    ".json": HANDLER_JSON,
    ".yaml": HANDLER_YAML, ".yml": HANDLER_YAML,
    ".py": HANDLER_PYTHON, ".pyi": HANDLER_PYTHON, ".pyw": HANDLER_PYTHON,
}

# text_handler.py строка 31
TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc"})
# ИТОГО: .log нигде не отображён
```

## Изменения в registry.py

### 1. Добавить `.log` в `_DEFAULT_SUFFIX_MAP`

Альтернатива A (добавить `.log`): получим поддержку `.log`-файлов через `universal_file_read`.
Альтернатива B (не добавлять): `.log` за пределами сцопа, не менять.

**Решение**: обсудить с владельцем и выбрать одну из альтернатив.

Если выбрана **Альтернатива A**:

```python
# Добавить после ".adoc": HANDLER_TEXT:
".log": HANDLER_TEXT,
```

NOTE: При добавлении `.log` в registry.py необходимо также добавить в `text_handler.TEXT_SUFFIXES`.

### 2. Добавить `handler_id` в details UNSUPPORTED_FILE_EXTENSION

Текущий код `validate_supported()` (строки 63–93) не включает `handler_id` в details при `UNSUPPORTED_FILE_EXTENSION`:

```python
# Текущее (hid ещё не разрешен, handler_id=""):
raise RegistryError("UNSUPPORTED_FILE_EXTENSION", {
    "message": f"No handler for suffix {suf!r}",
    "file_path": file_path,
    "suffix": suf,
    "operation": op,
})

# Нужно (добавить handler_id="" явно):
raise RegistryError("UNSUPPORTED_FILE_EXTENSION", {
    "message": f"No handler for suffix {suf!r}",
    "file_path": file_path,
    "suffix": suf,
    "operation": op,
    "handler_id": "",  # добавить
})
```

## Инструменты MCP

```python
# 1. Загрузить файл
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/core/file_handlers/registry.py"
)

# 2. Найти _DEFAULT_SUFFIX_MAP
cst_find_node(tree_id=..., search_type="simple", name="_DEFAULT_SUFFIX_MAP")

# 3. Заменить _DEFAULT_SUFFIX_MAP (добавить .log)
cst_modify_tree(tree_id=..., operations=[{
    "action": "replace",
    "node_id": "...",
    "code_lines": [
        "_DEFAULT_SUFFIX_MAP: Dict[str, str] = {",
        "    \".md\": HANDLER_TEXT,",
        "    \".txt\": HANDLER_TEXT,",
        "    \".rst\": HANDLER_TEXT,",
        "    \".adoc\": HANDLER_TEXT,",
        "    \".log\": HANDLER_TEXT,",  # добавлено
        "    \".json\": HANDLER_JSON,",
        "    \".yaml\": HANDLER_YAML,",
        "    \".yml\": HANDLER_YAML,",
        "    \".py\": HANDLER_PYTHON,",
        "    \".pyi\": HANDLER_PYTHON,",
        "    \".pyw\": HANDLER_PYTHON,",
        "}"
    ]
}])

# 4. Сохранить
cst_save_tree(tree_id=..., project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
              file_path="code_analysis/core/file_handlers/registry.py")
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/core/file_handlers/registry.py")
```

**Важно**: после добавления `.log` в registry.py — сразу сделать то же в Step 05 (добавить `.log` в `TEXT_SUFFIXES`).

## Проверка выполнения

- [ ] `.log` есть в `_DEFAULT_SUFFIX_MAP` (если выбрана Альт. A)
- [ ] `validate_supported()` включает `handler_id=""` в details
- [ ] `lint_code` вернул 0 ошибок