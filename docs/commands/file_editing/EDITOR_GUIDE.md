# AI Editor — подробное руководство по редактированию файлов

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Три уровня документации

| Уровень | Где | Для чего |
|---------|-----|----------|
| **List** | карточка сервера в `list_servers` | одна строка: что это за сервер |
| **Help** | описание сервера / OpenAPI `tool_info` | быстрый старт: цепочка из 6 шагов |
| **Info** | команда `info` | полный гайд с примерами JSON, format groups, ошибки |

**Канонический источник подробного гайда:** команда `info` (исходник: `ai_editor/commands/editor_info_content.py`).

```
call_server(server_id="ai-editor-server", copy_number=1, command="info", params={})
```

Ответ содержит:

- `markdown` — полный текст руководства
- `lifecycle` — шаги в структурированном виде
- `format_groups` — sidecar / tree-temp / text
- `examples` — готовые JSON для open, preview, edit, write, close
- `docs` — ссылки на файлы в репозитории

## Краткая цепочка (help-уровень)

```
0. CA session_create → session_id
1. universal_file_open(project_id, file_path, session_id)
2. universal_file_preview(..., session_id)     — node_ref
3. universal_file_edit(..., operations)        — только draft
4. universal_file_write(..., write_mode=preview)
5. universal_file_write(..., write_mode=commit) — validate → CA upload
6. universal_file_close(project_id, session_id) — всегда
```

## Что должна делать модель при задании «отредактировать файл»

1. Получить `session_id` на CA (`session_create`) и `project_id` (`list_projects`).
2. Вызвать `info` **один раз**, если модель ещё не знает workflow (опционально, но рекомендуется).
3. `open` → `preview` (targets) → цикл `edit` + `preview` → `write preview` → `write commit` → `close`.
4. Не использовать прямой доступ к файлам на диске.
5. Не пропускать `write preview` перед commit.
6. При `VALIDATION_ERROR` — исправить через `edit` и повторить write.
7. `close` в любом случае (успех, ошибка, отмена).

## Связанные документы

- [WORKFLOW.md](WORKFLOW.md) — prose workflow
- [README.md](README.md) — индекс команд
- [standards/UNIVERSAL_FILE_EDIT_CODER.yaml](../../standards/UNIVERSAL_FILE_EDIT_CODER.yaml) — machine brief
- [standards/FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml) — правила для моделей

## Задание модели (чеклист)

- [ ] CA `session_create` → `session_id`
- [ ] `universal_file_open` с `session_id`
- [ ] `universal_file_preview` → `node_ref`
- [ ] `universal_file_edit` (повтор preview при text-форматах)
- [ ] `universal_file_write` preview
- [ ] `universal_file_write` commit
- [ ] `universal_file_close`

При multi-file session — `file_path` на edit/write/close.
