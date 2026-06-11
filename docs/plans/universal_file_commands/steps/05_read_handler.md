# Step 05: text_handler.py — read guard + .log suffix

Status: TODO  
Depends on: Step 04  
File: `code_analysis/core/file_handlers/text_handler.py` (617 строк)

## Что делать

1. Добавить `.log` в `TEXT_SUFFIXES` (синхронизация с registry.py Step 04)
2. `TextFileHandler.read()` возвращает `FileHandlerResult` через
   `FileHandlerResult.data["lines"]` и `FileHandlerResult.data["total_lines"]` —
   проверить что `changed=False` (ред read не меняет файл)

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/core/file_handlers/text_handler.py start_line=1 end_line=120
```

## Текущее состояние (factual)

```python
# text_handler.py строка 31
TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc"})

# text_handler.py строка 34
def ensure_text_suffix(file_path: str) -> None:
    suf = Path(file_path).suffix.lower()
    if suf not in TEXT_SUFFIXES:
        raise ValueError(f"Not a configured plain-text suffix: {suf}")

# read_lines_range_ok() вызывает ensure_text_suffix() —
# если .log нет в TEXT_SUFFIXES, ValueError вылетит в execute()
```

## Изменение 1: Добавить `.log` в TEXT_SUFFIXES

```python
# Было:
TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc"})

# Станет:
TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc", ".log"})
```

**Предупреждение**: выполнять **только после** Step 04 (добавление `.log` в registry.py),
иначе `resolve_handler("file.log", "read")` бросит `RegistryError`
до того как `ensure_text_suffix` успеет проверить.

## Изменение 2: проверить что `TextFileHandler.read()` возвращает `changed=False`

```text
read_project_text_file code_analysis/core/file_handlers/text_handler.py start_line=120 end_line=200
```

`TextFileHandler.read()` должен построить `FileHandlerResult` с `changed=False`.
Если `changed` не выставляется явно — проверить и добавить явно (`changed=False`).

## Инструменты MCP

```python
# 1. Загрузить файл
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/core/file_handlers/text_handler.py"
)

# 2. Найти TEXT_SUFFIXES
cst_find_node(tree_id=..., search_type="simple", name="TEXT_SUFFIXES")

# 3. Заменить
cst_modify_tree(tree_id=..., operations=[{
    "action": "replace",
    "node_id": "...",
    "code_lines": [
        'TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc", ".log"})'
    ]
}])

# 4. Сохранить
cst_save_tree(tree_id=..., project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
              file_path="code_analysis/core/file_handlers/text_handler.py")
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/core/file_handlers/text_handler.py")
```

## Проверка выполнения

- [ ] `".log"` есть в `TEXT_SUFFIXES`
- [ ] `resolve_handler("test.log", "read")` → `"text"` (проверка через `run_project_module`)
- [ ] `TextFileHandler.read()` возвращает `FileHandlerResult` с `changed=False`
- [ ] `lint_code` вернул 0 ошибок