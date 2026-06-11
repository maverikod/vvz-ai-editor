# Step 02: Error-code glossary

Status: TODO  
Depends on: Step 01  
Files to read: none (создаём справочный файл, не редактируем код)

## Цель

Создать центральный справочный файл для модели: какие error-коды уже есть в коде, что из них возвращает каждая команда.

## Существующие error-коды (factual, из кода)

### Из `code_analysis/core/file_handlers/base.py`

```python
UNSUPPORTED_OPERATION = "unsupported_operation"  # handler не поддерживает operation
UNSUPPORTED_EXTENSION = "unsupported_extension"  # не используется
VALIDATION_FAILED = "validation_failed"           # общая валидация
SIDE_EFFECT_BLOCKED = "side_effect_blocked"        # dry_run заблокировал запись
```

### Из `code_analysis/core/file_handlers/registry.py`

```python
"UNSUPPORTED_FILE_EXTENSION"  # нет хэндлера для suffix
"UNSUPPORTED_FILE_OPERATION"  # operation не в OPERATIONS
```

### Из командных файлов (universal_file_*)

```python
"FILE_NOT_FOUND"          # файл не существует по absolute_path
"VALIDATION_ERROR"        # неверные параметры команды
"BACKUP_REQUIRED"         # create_backup() вернул фальши; запись отменена
"UPDATE_FILE_DATA_ERROR"  # persist_plain_text_file_metadata() не удалась
"INTERNAL_ERROR"          # handler_id прошёл resolve, но нет ветви if
"INVALID_RANGE"           # неверный start_line/end_line
"PROJECT_NOT_FOUND"       # project_id не найден в DB
"UNIVERSAL_FILE_SAVE_ERROR"    # непойманное исключение в save
"UNIVERSAL_FILE_REPLACE_ERROR" # то же в replace
"UNIVERSAL_FILE_DELETE_ERROR"  # то же в delete
```

### Дополнительные (delete_command)

```python
"UNSUPPORTED_FILE_EXTENSION"  # возвращает RegistryError
```

## Что нужно сделать в этом шаге

### 1. Создать `docs/plans/universal_file_commands/error_codes.md`

Справочная таблица для модели со всеми кодами, файлами-источниками, и details-полями.

Comd: `create_text_file` → `docs/plans/universal_file_commands/error_codes.md`

### 2. Код не меняется

Этот шаг только создаёт документацию. Никаких изменений в Python-файлах.

## Содержимое `error_codes.md` (полный текст)

Создайте файл со следующей таблицей:

| Code | Источник | Команды | details |
|------|---------|---------|---------- |
| `UNSUPPORTED_FILE_EXTENSION` | registry.py `RegistryError` | все | file_path, suffix, operation |
| `UNSUPPORTED_FILE_OPERATION` | registry.py `RegistryError` | все | file_path, handler_id, operation |
| `unsupported_operation` | base.py | handler-уровень | file_path, handler_id, operation |
| `validation_failed` | base.py | handler-уровень | file_path, handler_id, operation |
| `FILE_NOT_FOUND` | commands | read, save, replace, delete | project_id, file_path, handler_id, operation, resolved_path |
| `VALIDATION_ERROR` | commands | все | field или fields |
| `BACKUP_REQUIRED` | save_command._run_text_save | save, replace, delete | file_path, resolved_path |
| `UPDATE_FILE_DATA_ERROR` | save_command._run_text_save | save, replace, delete | (dict из persist_plain_text_file_metadata) |
| `INVALID_RANGE` | text_handler, replace_command | replace, delete | reason |
| `PROJECT_NOT_FOUND` | save_command | save, replace, delete | project_id |
| `INTERNAL_ERROR` | commands | все | handler_id, operation |
| `UNIVERSAL_FILE_SAVE_ERROR` | save_command except-ветка | save | — |
| `UNIVERSAL_FILE_REPLACE_ERROR` | replace_command except-ветка | replace | — |
| `UNIVERSAL_FILE_DELETE_ERROR` | delete_command except-ветка | delete | — |

## Проверка выполнения

- [ ] Файл `docs/plans/universal_file_commands/error_codes.md` создан
- [ ] Таблица полная (все коды, источники, details)
- [ ] Python-файлы не тронуты