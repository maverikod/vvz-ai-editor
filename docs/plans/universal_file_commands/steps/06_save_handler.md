# Step 06: universal_file_save_command.py — проверка + backup_uuid в response

Status: TODO  
Depends on: Step 03  
File: `code_analysis/commands/universal_file_save_command.py` (415 строк)

## Текущее состояние (factual — прочитано в Step 01)

Mechanics `_run_text_save` (строки 298—415) уже полные:

```
1. file_lock(absolute_path)                        ✔ есть
2. create_backup() если exists + !dry_run + backup  ✔ есть
3. проверка backup_uuid, abort BACKUP_REQUIRED      ✔ есть
4. TextFileHandler().save(req)                     ✔ есть
5. persist_plain_text_file_metadata()              ✔ есть
6. rollback bm.restore_file() при DB-ошибке     ✔ есть
7. backup_uuid в out (возвращается в data)       ✔ есть
```

## Что сделать

Проверить однократно читая файл, что:

1. `backup_uuid` возвращается в `SuccessResult.data` пользователю
   (str UUID или отсутствует если файл был новым)
2. `metadata_update` возвращается в `SuccessResult.data`
3. `_run_text_save` вызывается только для `HANDLER_TEXT`
   (для JSON/YAML/Python хэндлеры вызываются напрямую)

## Прочитайте перед правкой

```text
read_project_text_file code_analysis/commands/universal_file_save_command.py start_line=290 end_line=415
```

Если `backup_uuid` не возвращается в `data` при `success=True` — добавить.

## Изменения (если backup_uuid не в data)

В `_run_text_save`, перед финальным `return FileHandlerResult(success=True, ...)` (строки 406—415):

```python
# Убедиться что out содержит backup_uuid:
out = dict(fr.data or {})
out["metadata_update"] = meta
if backup_uuid:
    out["backup_uuid"] = backup_uuid  # уже есть — верифицировать
```

Если `backup_uuid` в data уже есть — код не меняется.

## Инструменты MCP

```python
# Только read, не редактировать если всё верно
read_project_text_file(
    project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
    file_path="code_analysis/commands/universal_file_save_command.py",
    start_line=395, end_line=415
)
```

## Проверка выполнения

- [ ] `SuccessResult.data` содержит `backup_uuid` (если backup создавался)
- [ ] `SuccessResult.data` содержит `metadata_update`
- [ ] `_run_text_save` не вызывается для JSON/YAML/Python
- [ ] `lint_code` вернул 0 ошибок (если были изменения)