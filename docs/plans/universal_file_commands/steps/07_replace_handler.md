# Step 07: universal_file_replace_command.py — проверка backup+rollback

Status: TODO  
Depends on: Step 03  
File: `code_analysis/commands/universal_file_replace_command.py` (701 строк)

## Текущее состояние (factual)

Mechanics `_run_text_replace` (строки 606—701) уже полные:

```
1. file_lock(absolute_path)                            ✔ есть
2. _validate_text_replace_local() перед backup        ✔ есть
3. create_backup() если exists + !dry_run + backup      ✔ есть
4. abort BACKUP_REQUIRED если backup_uuid falsy         ✔ есть
5. TextFileHandler().replace(req)                      ✔ есть
6. persist_plain_text_file_metadata()                  ✔ есть
7. rollback bm.restore_file() при DB-ошибке           ✔ есть
8. backup_uuid в out                                  ✔ есть
```

## Что сделать

Прочитать файл целиком и подтвердить что все пункты выполнены.

## Прочитайте перед проверкой

```text
read_project_text_file code_analysis/commands/universal_file_replace_command.py start_line=606 end_line=701
```

## Критерии проверки

### Чек-лист чтения

| Условие | Что искать в коде |
|----------|-------------------|
| pre-validation до backup | `_validate_text_replace_local()` вызывается до `if not dry_run and backup` |
| backup guard | `if not backup_uuid: return FileHandlerResult(..., code="BACKUP_REQUIRED")` |
| rollback при DB-ошибке | `if not meta.get("success"): if backup_uuid: _restore(rel, backup_uuid)` |
| backup_uuid в data | `if backup_uuid: out["backup_uuid"] = backup_uuid` |

Если какой-либо из этих пунктов отсутствует — добавить по образцу `_run_text_save`.

## Инструменты MCP

```python
# Чтение _run_text_replace
read_project_text_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_replace_command.py",
    start_line=606, end_line=701
)

# Если нужна правка — CST путь
cst_load_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_replace_command.py"
)
# затем cst_find_node, cst_modify_tree, cst_save_tree
```

## Проверка выполнения

- [ ] `_run_text_replace` содержит `_validate_text_replace_local()` до backup
- [ ] `BACKUP_REQUIRED` guard есть
- [ ] rollback `bm.restore_file()` при `UPDATE_FILE_DATA_ERROR` есть
- [ ] `backup_uuid` возвращается в data
- [ ] если правки были — `lint_code` 0 ошибок