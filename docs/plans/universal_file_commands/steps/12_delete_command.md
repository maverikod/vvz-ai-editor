# Step 12: universal_file_delete_command.py — file-mode guard + schema

Status: TODO  
Depends on: Step 08  
File: `code_analysis/commands/universal_file_delete_command.py` (726 строк)

## Текущее состояние (factual)

### delete_mode константы (строки 61—68)

```python
DELETE_MODE_FILE = "file"
DELETE_MODE_RANGE = "range"
DELETE_MODE_NODE = "node"
DELETE_MODE_YAML_PATH = "yaml_path"
DELETE_MODE_JSON_POINTER = "json_pointer"
DELETE_MODE_CST_SELECTOR = "cst_selector"
DELETE_MODE_NODE_ID = "node_id"

_ALLOWED_TEXT = frozenset({"file", "range"})
_ALLOWED_JSON = frozenset({"file", "node", "json_pointer"})
_ALLOWED_YAML = frozenset({"file", "yaml_path"})
_ALLOWED_PYTHON = frozenset({"file", "cst_selector", "node_id"})
```

### Схема (строки ~260—380)

```python
"required": ["project_id", "file_path", "delete_mode"],
"additionalProperties": False,
```

### Логика `_run_text_delete` (строки 597—726)

```
DELETE_MODE_FILE: backup вызывается, после TextFileHandler().delete()
                  проверяется: if dm == DELETE_MODE_FILE or not absolute_path.exists()
                  если True — вернуть без persist
DELETE_MODE_RANGE: backup + persist + rollback
```

## Что сделать

### 1. Проверить rollback в `_run_text_delete`

```text
read_project_text_file code_analysis/commands/universal_file_delete_command.py start_line=690 end_line=726
```

Проверить что при `not meta.get("success")` в `DELETE_MODE_RANGE`-ветви:
- `if backup_uuid: _restore(rel, backup_uuid)` есть

### 2. Проверить что `backup_uuid` возвращается в data в обоих ветвях

Для FILE-ветви (~строка 658):
```python
out = dict(fr.data or {})
if backup_uuid:
    out["backup_uuid"] = backup_uuid  # проверить есть ли
```

Для RANGE-ветви (~строка 715):
```python
if backup_uuid:
    out["backup_uuid"] = backup_uuid  # проверить есть ли
```

### 3. Добавить в description пояснение FILE вс ранге в схеме

В `"delete_mode"` description (строка ~281) добавить:

```python
"For delete_mode=file: entire file is removed from filesystem; "
"backup is created before removal; persist_plain_text_file_metadata "
"is NOT called (file gone). For delete_mode=range: lines removed, "
"file remains, metadata updated, rollback on DB error."
```

### 4. Добавить `.log` в allowed-список TEXT (если Step 04-05 выполнены)

`.log` роутится в `HANDLER_TEXT`, поэтому `_ALLOWED_TEXT` уже покрывает `.log`.
Дополнительных изменений не требуется.

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/commands/universal_file_delete_command.py start_line=270 end_line=295
read_project_text_file code_analysis/commands/universal_file_delete_command.py start_line=640 end_line=726
```

## Инструменты MCP

```python
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_delete_command.py"
)
cst_find_node(tree_id=..., search_type="xpath",
              query="function[name='get_schema']")
cst_modify_tree(...)  # обновить delete_mode description
cst_save_tree(...)
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/commands/universal_file_delete_command.py")
```

## Проверка выполнения

- [ ] rollback `bm.restore_file()` в `_run_text_delete` при RANGE+DB-ошибке есть
- [ ] `backup_uuid` в data в FILE-ветви
- [ ] `backup_uuid` в data в RANGE-ветви
- [ ] delete_mode description поясняет FILE vs RANGE семантику
- [ ] `lint_code` вернул 0 ошибок