# list_worker_logs

**Command name:** `list_worker_logs`  
**Class:** `ListWorkerLogsMCPCommand`  
**Source:** `code_analysis/commands/log_viewer_mcp_commands.py`  
**Category:** log_viewer

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_worker_logs command lists available worker log files in specified directories. It scans configured log directories and returns available log files for workers (file_watcher, vectorization, analysis) and server logs.

Operation flow:
1. If log_dirs provided, uses those directories
2. If log_dirs not provided, defaults to ['logs'] directory
3. Scans directories for log files
4. If worker_type specified, filters by worker type:
   - file_watcher: Finds file_watcher*.log files
   - vectorization: Finds vectorization*.log files
   - analysis: Finds analysis*.log files
   - server: Finds server*.log, mcp*.log files
5. If worker_type not specified, returns all log files
6. Returns list of log files with metadata (path, size, modified time)

Worker Types:
- file_watcher: File watcher worker logs
- vectorization: Vectorization worker logs
- analysis: Analysis worker logs
- server: Server logs (MCP proxy, etc.)

Use cases:
- Discover available log files
- Find log files for specific workers
- Get log file metadata (size, modified time)
- List all logs before viewing specific ones

Important notes:
- Default log directory is 'logs' if not specified
- Can scan multiple directories if log_dirs provided
- Returns file metadata including path, size, and modified time
- Filter by worker_type to find specific worker logs

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `log_dirs` | array | No | List of directories to scan for log files (optional, defaults to ['logs']) |
| `worker_type` | string | No | Filter by worker type (optional) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `log_files`: List of log files. Each entry contains:
- path: Full path to log file
- name: Log file name
- size: File size in bytes
- modified_time: Last modified timestamp
- worker_type: Detected worker type (if applicable)
- `total_files`: Total number of log files found
- `scanned_dirs`: List of directories that were scanned

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** LOG_LIST_ERROR (and others).

---

## Examples

### Correct usage

**List file_watcher logs**
```json
{
  "worker_type": "file_watcher"
}
```

Lists only file_watcher log files.

**List logs from custom directories**
```json
{
  "log_dirs": [
    "logs",
    "custom_logs",
    "/var/log/code_analysis"
  ]
}
```

Scans multiple directories for log files.

**List server logs**
```json
{
  "worker_type": "server"
}
```

Lists server log files (MCP proxy, etc.).

### Incorrect usage

- **LOG_LIST_ERROR**: Directory not found, permission denied, or scan error. Verify log directories exist and are accessible. Check file permissions. Ensure directories are readable.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `LOG_LIST_ERROR` | General error during log listing | Verify log directories exist and are accessible. C |

## Best practices

- Use this command first to discover available log files
- Filter by worker_type to find specific worker logs
- Specify custom log_dirs if logs are in non-standard locations
- Use returned log file paths with view_worker_logs command
- Check file sizes to identify large log files that may need rotation

---
