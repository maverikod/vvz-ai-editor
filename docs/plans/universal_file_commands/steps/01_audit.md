# Step 01: Audit — реальная архитектура

Status: ✅ DONE  
Date: 2026-05-01

## Что было прочитано

| Файл | Строк |
|------|--------|
| `code_analysis/core/file_handlers/base.py` | 254 |
| `code_analysis/core/file_handlers/registry.py` | 199 |
| `code_analysis/core/file_handlers/text_handler.py` | 617 |
| `code_analysis/commands/universal_file_read_command.py` | 304 |
| `code_analysis/commands/universal_file_save_command.py` | 415 |
| `code_analysis/commands/universal_file_replace_command.py` | 701 |
| `code_analysis/commands/universal_file_delete_command.py` | 726 |
| `code_analysis/core/backup_manager.py` | 502 |

## Архитектура (factual)

### registry.py
- `HANDLER_IDS = ("text", "json", "yaml", "python")`
- `OPERATIONS = frozenset({"read", "save", "replace", "delete"})`
- `_DEFAULT_SUFFIX_MAP`: `.md/.txt/.rst/.adoc` → text; `.json` → json; `.yaml/.yml` → yaml; `.py/.pyi/.pyw` → python
- `.toml` — **не отображён**, вернёт `UNSUPPORTED_FILE_EXTENSION`
- `resolve_handler(file_path, operation) -> str` — возвращает handler_id или бросает `RegistryError`
- `RegistryError(code: str, details: Dict)` — импортируется из registry.py

### base.py
- `FileHandlerRequest`: `project_id, file_path, handler_id, operation, dry_run, diff, backup, extra`
- `FileHandlerResult`: `success, handler_id, operation, file_path, project_id, dry_run, changed, message, code, details, data`
- `standard_error_result(*, code, message, request, changed=False, extra_details=None) -> FileHandlerResult`
- `validate_before_side_effects(request) -> Optional[FileHandlerResult]` — проверяет project_id, file_path, handler_id
- `BaseFileHandler.mutating_precheck(request) -> Optional[FileHandlerResult]` — unsupported_op + validation
- `STANDARD_HANDLER_ERROR_CODES = frozenset({"unsupported_operation", "unsupported_extension", "validation_failed", "side_effect_blocked", "INVALID_RANGE", "UNSUPPORTED_FILE_EXTENSION", "UNSUPPORTED_FILE_OPERATION"})`

### text_handler.py — ключевые функции
- `TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc"})`
- `read_lines_range_ok(absolute_path: Path, start_line: int, end_line: int) -> Dict`
- `compute_replace_lines_single_range(all_lines, start_line, end_line, new_lines)`
- `compute_replace_lines_multi(all_lines, triples: List[Tuple[int,int,List[str]]])`
- `lines_after_delete_range(all_lines, start_line, end_line) -> List[str]`
- `persist_plain_text_file_metadata(database, project_id, absolute_path, normalized_path, source_code) -> Dict`

### universal_file_save_command.py — уже реализовано
- `BackupManager(root_dir).create_backup(path, command, comment)` — **уже есть**
- если `create_backup()` вернёт falsy — abort с `code="BACKUP_REQUIRED"`
- `persist_plain_text_file_metadata()` + rollback через `bm.restore_file(rel, backup_uuid)` — **уже есть**
- `file_lock(absolute_path)` обёртывает всю логику записи — **уже есть**

## Найденные проблемы

| # | Проблема | Файл | Серьёзность | Шаг |
|---|---------|------|-----------|------|
| 1 | `backup_uuid: Optional[str]` внутри `_run_text_save` не передаётся в `SuccessResult.data` | save_command | LOW | 10 |
| 2 | `universal_file_replace_command`: backup вызывается в `_run_text_replace`, но rollback `bm.restore_file()` при ошибке DB упдейта в соответствующем месте не проверялся — нужно подтвердить | replace_command | HIGH | 11 |
| 3 | `universal_file_delete_command` `delete_mode=file` не вызывает `BackupManager` для text-файлов до удаления | delete_command | HIGH | 12 |
| 4 | `TEXT_SUFFIXES` в text_handler.py не включает `.log` / `.cfg` / `.ini`, хотя registry.py также не их отображает | registry + text_handler | LOW | 04 |
| 5 | `universal_file_read` schema не документирует что Python-файлы рутируются в `GetFileLinesCommand` | read_command | LOW | 09 |
| 6 | Базовые error-коды разбросаны по двум файлам (base.py + registry.py) без центрального глоссария | — | LOW | 02 |

## Вывод

Все четыре команды работают. План закрывает конкретные пробелы:
- **BACKUP_REQUIRED guard** отсутствует в replace/delete text-пути
- **DB rollback** при ошибке `persist_plain_text_file_metadata` не подтверждён в replace/delete
- `backup_uuid` не возвращается в ответе save