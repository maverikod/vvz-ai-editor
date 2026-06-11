# Step 10: universal_file_save_command.py — rollback path + schema

Status: TODO  
Depends on: Step 06  
File: `code_analysis/commands/universal_file_save_command.py` (415 строк)

## Текущее состояние (factual)

### Схема (строки 90—162)

```python
"required": ["project_id", "file_path", "content"],
"additionalProperties": False,
```

Параметры: `project_id`, `file_path`, `content` (str), `dry_run`, `diff`,
`backup` (default True), `commit_message`, `diff_context_lines`,
`validate_syntax_only` (Python), `tree_id` (Python).

### Текущая логика backup_for_handler (строки 267—273)

```python
backup_for_handler = bool(backup)
if handler_id == HANDLER_TEXT and (not dry_run) and backup_for_handler:
    backup_for_handler = False  # Тext: backup делает _run_text_save сам
```

Для TEXT handler backup передаётся в `_run_text_save`, не в req.
JSON/YAML/Python — backup через `req.backup`.

## Что сделать

### 1. Проверить что rollback в `_run_text_save` работает (Step 06)

```text
read_project_text_file code_analysis/commands/universal_file_save_command.py start_line=370 end_line=415
```

Проверить что при `not meta.get("success")` есть вызов `_restore(rel, backup_uuid)`.

### 2. Дополнить описание `content` в schema

Текущее (строка ~118):

```python
"content": {
    "type": "string",
    "description": (
        "Full file body: plain text for .md/.txt/.rst/.adoc/.log; ..."
    ),
},
```

Добавить `.log` в описание `content` (если `.log` добавлен в Step 04):

```python
"description": (
    "Full file body: plain text for .md/.txt/.rst/.adoc/.log; "
    "JSON or YAML text for .json / .yaml/.yml; Python source for .py/.pyi/.pyw."
),
```

### 3. Добавить в description упоминание backup_uuid в ответе

```python
"description": (
    "... Response includes backup_uuid when backup was created "
    "(text handler only, when overwriting existing file)."
),
```

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/commands/universal_file_save_command.py start_line=90 end_line=165
read_project_text_file code_analysis/commands/universal_file_save_command.py start_line=370 end_line=415
```

## Инструменты MCP

```python
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_save_command.py"
)
# Найти get_schema, обновить content.description
cst_find_node(tree_id=..., search_type="xpath",
              query="function[name='get_schema']")
cst_modify_tree(...)
cst_save_tree(...)
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/commands/universal_file_save_command.py")
```

## Проверка выполнения

- [ ] rollback в `_run_text_save` есть (чек Step 06)
- [ ] `.log` есть в description content (если Step 04 выполнен)
- [ ] `backup_uuid` упомянут в description
- [ ] `lint_code` вернул 0 ошибок