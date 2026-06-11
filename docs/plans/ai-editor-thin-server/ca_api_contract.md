# Контракт API Code Analysis Server для thin AI Editor

Привязка: HRS `{a1c4}`, MRS **C-023**. Документ-сводка; при cascade правится после `source_spec.md`.

## Разделение ответственности

| Действие | Кто | MCP для модели |
|----------|-----|----------------|
| session_create / delete | Агент → СА | на СА |
| open / edit / write / close / preview | Редактор | universal_file_* |
| lock / unlock / transfer | СА | только upstream внутри редактора |

## Команды C-023 (upstream only)

| Команда | Назначение |
|---------|------------|
| `session_list_file_locks` | Touch + валидация session_id |
| `session_open_file` | Lock |
| `session_close_file` | Unlock |
| `project_file_transfer_download_begin` (+ chunks) | Download с lock |
| `download_without_lock` (обёртка) | Download **без** lock — one-shot preview |
| `project_file_transfer_upload_save` | Upload / create file |
| `list_project_files` | file_path → file_id |
| `list_projects` | резолв project (internal) |

### create=true ({c4f2})

`upload_save` → `list_project_files` → `session_open_file` → локальный origin в workspace.

### Вне контракта

`session_view`, `subordinate_session_*`, `get_project_root` для file workflow.

## Session Guard (C-024)

Единая точка перед universal_file_*: normal (open/edit/preview) vs terminating (write/close).

## Порядок реализации G

```
G-001 ║ G-002 → G-007 → G-003 → G-004 → G-005 → G-010
              └→ G-006 → G-008 → G-009
```
