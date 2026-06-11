# rotate_worker_logs

**Command name:** `rotate_worker_logs`  
**Class:** `RotateWorkerLogsMCPCommand`  
**Source:** `code_analysis/commands/log_viewer_mcp_commands.py`  
**Category:** log_viewer

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The rotate_worker_logs command manually rotates a worker log file: the current log is renamed to .1, .1 to .2, etc. (same as RotatingFileHandler), then a new empty log file is created. Use when you want to archive logs without waiting for size-based rotation. The running worker may continue writing to the previous file (now .1) until it restarts or reopens the log.

Parameters: log_path (optional if worker_type set), worker_type, backup_count (default 5).

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `log_path` | string | No | Path to log file to rotate (optional if worker_type given) |
| `worker_type` | string | No | Worker type to resolve default log path (optional) |
| `backup_count` | integer | No | Number of backup files to keep (default 5) Default: `5`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `log_path`: Path that was rotated
- `backup_count`: Number of backups kept
- `rotated_paths`: List of paths after rotation (e.g. [log.1, log.2])
- `message`: Human-readable summary

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** MISSING_LOG_PATH, ROTATE_LOG_ERROR (and others).

---

## Examples

### Correct usage

**Rotate file_watcher log**
```json
{
  "worker_type": "file_watcher"
}
```

Rotates the default file_watcher log (e.g. logs/file_watcher.log -> .1, new empty log).

**Rotate by path with 3 backups**
```json
{
  "log_path": "logs/vectorization_worker.log",
  "backup_count": 3
}
```

Rotates the given log file and keeps 3 backup copies.

### Incorrect usage

- **MISSING_LOG_PATH**: Neither log_path nor worker_type provided or path could not be resolved. Provide log_path or worker_type and ensure server config is available.

- **ROTATE_LOG_ERROR**: OS error during rotation (permission, disk, etc.). Check file permissions and disk space.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `MISSING_LOG_PATH` | Neither log_path nor worker_type provided or path could not  | Provide log_path or worker_type and ensure server  |
| `ROTATE_LOG_ERROR` | OS error during rotation (permission, disk, etc.) | Check file permissions and disk space. |

---
