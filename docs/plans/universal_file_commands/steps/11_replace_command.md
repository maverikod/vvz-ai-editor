# Step 11: universal_file_replace_command.py — проверка backup guard

Status: TODO  
Depends on: Step 07  
File: `code_analysis/commands/universal_file_replace_command.py` (701 строк)

## Текущее состояние (factual)

### Схема (строки 295—410)

```python
"required": ["project_id", "file_path"],
"additionalProperties": False,
```

Параметры: `project_id`, `file_path`, `dry_run`, `diff`, `backup`,
`commit_message`, `diff_context_lines`, `validate_syntax_only`, `tree_id`,
`start_line`, `end_line`, `new_lines` (text), `replacements` (text multi),
`operations` (JSON), `yaml_path`, `value` (YAML), `ops` (Python).

### Текущая логика backup_for_handler (строки 563—566)

```python
backup_for_handler = bool(backup)
if handler_id == HANDLER_TEXT and (not dry_run) and backup_for_handler:
    backup_for_handler = False  # Text: backup делает _run_text_replace
```

## Что сделать

### 1. Проверить rollback в `_run_text_replace`

```text
read_project_text_file code_analysis/commands/universal_file_replace_command.py start_line=655 end_line=701
```

Проверить что при `not meta.get("success")` есть:
- `if backup_uuid: _restore(rel, backup_uuid)`
- `return FileHandlerResult(..., code="UPDATE_FILE_DATA_ERROR")`

### 2. Проверить что `backup_uuid` возвращается в data

Найти в `_run_text_replace` финальный `return FileHandlerResult(success=True, ...)` и
убедиться что `out["backup_uuid"] = backup_uuid` есть.

### 3. Дополнить description schema

В `"description"` `get_schema()` (строка ~297) добавить:

```python
"Response includes backup_uuid (str) and metadata_update when text handler "
"performed a successful write. dry_run=True skips backup, write, and DB."
```

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/commands/universal_file_replace_command.py start_line=295 end_line=310
read_project_text_file code_analysis/commands/universal_file_replace_command.py start_line=640 end_line=701
```

## Инструменты MCP

```python
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_replace_command.py"
)
# Найти get_schema description и обновить
cst_find_node(tree_id=..., search_type="xpath",
              query="function[name='get_schema']")
cst_modify_tree(...)
cst_save_tree(...)
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/commands/universal_file_replace_command.py")
```

## Проверка выполнения

- [ ] rollback `bm.restore_file()` в `_run_text_replace` при DB-ошибке есть
- [ ] `backup_uuid` возвращается в data при success
- [ ] description упоминает backup_uuid в ответе
- [ ] `lint_code` вернул 0 ошибок