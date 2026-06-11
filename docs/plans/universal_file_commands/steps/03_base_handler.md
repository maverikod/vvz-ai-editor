# Step 03: base.py — добавить error-коды и mutating guard

Status: TODO  
Depends on: Step 02  
File: `code_analysis/core/file_handlers/base.py` (254 строки)

## Что делать

Base.py уже содержит `validate_before_side_effects()` и `mutating_precheck()`.
Нужно добавить два новых error-кода в `STANDARD_HANDLER_ERROR_CODES` и документацию backup-контракта.

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/core/file_handlers/base.py start_line=1 end_line=254
```

## Текущий состав (factual)

```python
# В STANDARD_HANDLER_ERROR_CODES уже есть:
"unsupported_operation", "unsupported_extension", "validation_failed",
"side_effect_blocked", "INVALID_RANGE",
"UNSUPPORTED_FILE_EXTENSION", "UNSUPPORTED_FILE_OPERATION"
```

## Изменения

### 1. Добавить два кода в `STANDARD_HANDLER_ERROR_CODES`

```python
# Добавить в frozenset:
"BACKUP_REQUIRED",       # BackupManager.create_backup() вернул falsy
"UPDATE_FILE_DATA_ERROR", # persist_plain_text_file_metadata() не удалась
```

### 2. Добавить докстринг backup-контракта в docstring `BaseFileHandler`

Добавить в docstring `BaseFileHandler` (строка 142—151):

```text
Backup contract:
    Implementations that perform mutating I/O (save, replace, delete) MUST:
    1. Call mutating_precheck() and return on non-None result.
    2. Call BackupManager(root_dir).create_backup() before any write
       when the target file already exists and dry_run is False.
    3. Return code=BACKUP_REQUIRED if create_backup() is falsy.
    4. Call persist_plain_text_file_metadata() after write (text handler only).
    5. Restore backup via bm.restore_file(rel, uuid) if DB update fails.
```

## Инструменты MCP

```python
# 1. Просмотр текущего состояния base.py
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/core/file_handlers/base.py"
)

# 2. Найти STANDARD_HANDLER_ERROR_CODES
cst_find_node(tree_id=..., search_type="simple", name="STANDARD_HANDLER_ERROR_CODES")

# 3. Добавить два кода в frozenset через cst_modify_tree
cst_modify_tree(tree_id=..., operations=[{
    "action": "replace",
    "node_id": "...",  # node_id STANDARD_HANDLER_ERROR_CODES
    "code_lines": [
        "STANDARD_HANDLER_ERROR_CODES = frozenset(",
        "    {",
        "        UNSUPPORTED_OPERATION,",
        "        UNSUPPORTED_EXTENSION,",
        "        VALIDATION_FAILED,",
        "        SIDE_EFFECT_BLOCKED,",
        "        \"INVALID_RANGE\",",
        "        \"UNSUPPORTED_FILE_EXTENSION\",",
        "        \"UNSUPPORTED_FILE_OPERATION\",",
        "        \"BACKUP_REQUIRED\",",
        "        \"UPDATE_FILE_DATA_ERROR\",",
        "    },",
        ")"
    ]
}])

# 4. Сохранить + проверить
cst_save_tree(tree_id=..., project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
              file_path="code_analysis/core/file_handlers/base.py")
lint_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
          file_path="code_analysis/core/file_handlers/base.py")
type_check_code(project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
                file_path="code_analysis/core/file_handlers/base.py")
```

## Проверка выполнения

- [ ] `BACKUP_REQUIRED` есть в `STANDARD_HANDLER_ERROR_CODES`
- [ ] `UPDATE_FILE_DATA_ERROR` есть в `STANDARD_HANDLER_ERROR_CODES`
- [ ] docstring `BaseFileHandler` содержит backup contract
- [ ] `lint_code` вернул 0 ошибок
- [ ] `type_check_code` чистый