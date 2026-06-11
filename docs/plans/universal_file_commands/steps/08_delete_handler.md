# Step 08: universal_file_delete_command.py — проверка backup+rollback

Status: TODO  
Depends on: Step 03  
File: `code_analysis/commands/universal_file_delete_command.py` (726 строк)

## Текущее состояние (factual)

Mechanics `_run_text_delete` (строки 597—726) уже полные:

```
1. file_lock(absolute_path)                               ✔ есть
2. валидация range перед backup (для DELETE_MODE_RANGE) ✔ есть
3. create_backup() если exists + !dry_run + backup         ✔ есть
4. abort BACKUP_REQUIRED если backup_uuid falsy            ✔ есть
5. TextFileHandler().delete(req)                          ✔ есть
6a. DELETE_MODE_FILE: вернуть без DB-упдейта             ✔ есть
6b. DELETE_MODE_RANGE: persist_plain_text_file_metadata() ✔ есть
7. rollback bm.restore_file() при DB-ошибке              ✔ есть
8. backup_uuid в out                                     ✔ есть
```

## Что сделать

Прочитать файл целиком, подтвердить по чек-листу.
Особое внимание: проверить что ветвь `DELETE_MODE_FILE` правильно обходит persist.

## Прочитайте перед проверкой

```text
read_project_text_file code_analysis/commands/universal_file_delete_command.py start_line=597 end_line=726
```

## Критерии проверки

| Условие | Что искать в коде |
|----------|-------------------|
| `DELETE_MODE_FILE` в extra | `extra["delete_full_file"] = True` |
| backup guard | `if not backup_uuid: return ..., code="BACKUP_REQUIRED"` |
| FILE-ветвь обходит persist | `if dm == DELETE_MODE_FILE or not absolute_path.exists(): return без persist` |
| rollback | `if not meta.get("success"): if backup_uuid: _restore(rel, backup_uuid)` |
| backup_uuid в data | `if backup_uuid: out["backup_uuid"] = backup_uuid` |

## Особые случаи

- **`DELETE_MODE_FILE`**: после `TextFileHandler().delete(req)` файл удаляется. `persist_plain_text_file_metadata` нельзя — нечего читать.
- **`DELETE_MODE_RANGE`**: файл остаётся, нужен DB-упдейт через `persist`.
- Проверить: `if dm == DELETE_MODE_FILE or not absolute_path.exists()` — оба условия необходимы.

## Инструменты MCP

```python
read_project_text_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_delete_command.py",
    start_line=597, end_line=726
)
```

## Проверка выполнения

- [ ] `_run_text_delete` вызывает `_validate_text_delete_local()` до backup
- [ ] `BACKUP_REQUIRED` guard есть
- [ ] `DELETE_MODE_FILE` правильно обходит persist
- [ ] rollback `bm.restore_file()` при `UPDATE_FILE_DATA_ERROR` есть
- [ ] `backup_uuid` возвращается в data
- [ ] если правки были — `lint_code` 0 ошибок