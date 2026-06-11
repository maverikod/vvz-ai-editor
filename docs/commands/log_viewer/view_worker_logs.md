# view_worker_logs

**Command name:** `view_worker_logs`  
**Class:** `ViewWorkerLogsMCPCommand`  
**Source:** `code_analysis/commands/log_viewer_mcp_commands.py`  
**Category:** log_viewer

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The view_worker_logs command views worker logs with advanced filtering capabilities. It supports filtering by time range, event types, log levels, and text search patterns. The command parses log files and returns structured log entries.

Operation flow:
1. Resolves path: if log_id given, from config (same as rotate_all_logs); else log_path or worker_type
2. Reads current log and rotated files (.1, .2, ... and .gz) in chronological order
3. Parses time filters (from_time, to_time) if provided
4. Selects event patterns based on worker_type (or derived from log_id)
5. Parses each log line (unified or legacy format) to extract timestamp, level, importance (0-10), and message
6. Applies filters:
   - Time range filter (from_time to to_time; partial interval supported)
   - Event type filter (matches event patterns)
   - Log level filter (INFO, ERROR, WARNING, etc.)
   - Importance filter (importance_min, importance_max 0-10)
   - Search pattern filter (regex on message)
7. If tail specified, returns last N lines (ignores time filters)
8. Limits results to specified limit
9. Returns structured log entries

Worker Types:
- file_watcher: File watcher worker logs with events like new_file, changed_file, deleted_file
- vectorization: Vectorization worker logs with events like processed, cycle, circuit_breaker
- analysis: Analysis worker logs

Event Types (file_watcher):
- new_file: New file detected
- changed_file: File changed
- deleted_file: File deleted
- cycle: Scan cycle
- scan_start: Scan started
- scan_end: Scan ended
- queue: Queue operations
- error: Error events
- info: Info events
- warning: Warning events

Event Types (vectorization):
- cycle: Processing cycle
- processed: File processed/vectorized
- error: Error events
- info: Info events
- warning: Warning events
- circuit_breaker: Circuit breaker events

Use cases:
- Debug worker issues by viewing recent logs
- Filter logs by time range to find specific events
- Search for specific error patterns
- Monitor worker activity
- Analyze worker performance

Important notes:
- Time format: ISO format ('2025-01-26T10:30:00') or 'YYYY-MM-DD HH:MM:SS'
- If tail is specified, time filters are ignored
- Search pattern supports regex (case-insensitive)
- Default limit is 1000 lines to prevent large responses
- Log lines are parsed to extract timestamp, level, importance (0-10), and message
- importance_min/importance_max are filters only (they select which lines are returned); importance is assigned when logs are written. As logs gradually fill up, filtering by importance becomes more useful (e.g. importance_min=6 for warnings and above).

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `log_id` | string | No | Log identifier (preferred over path). Resolves path from config; reading includes rotated files (.1, .2, .gz). |
| `log_path` | string | No | Path to log file (optional if log_id or worker_type set) |
| `worker_type` | string | No | Type of worker (file_watcher, vectorization, indexing, database_driver, or analysis) Default: `"file_watcher"`. |
| `from_time` | string | No | Start time filter (ISO format or 'YYYY-MM-DD HH:MM:SS') |
| `to_time` | string | No | End time filter (ISO format or 'YYYY-MM-DD HH:MM:SS') |
| `event_types` | array | No | List of event types to filter (e.g., ['new_file', 'changed_file', 'deleted_file', 'cycle', 'error']) |
| `log_levels` | array | No | List of log levels to filter (e.g., ['INFO', 'ERROR']) |
| `search_pattern` | string | No | Text pattern to search for (regex supported) |
| `importance_min` | integer | No | Minimum importance 0-10 (inclusive) |
| `importance_max` | integer | No | Maximum importance 0-10 (inclusive) |
| `tail` | integer | No | Return last N lines (if specified, ignores time filters) |
| `limit` | integer | No | Maximum number of lines to return Default: `1000`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `entries`: List of log entries. Each entry contains:
- timestamp: Log timestamp (ISO format)
- level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- importance: Importance 0-10 (see LOG_IMPORTANCE_CRITERIA.md)
- message: Log message
- raw: Original log line
- `total_lines`: Total number of lines read from log file
- `filtered_lines`: Number of lines after filtering
- `limit`: Limit applied

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** LOG_VIEW_ERROR (and others).

---

## Examples

### Correct usage

**View last 100 lines of log**
```json
{
  "log_path": "logs/file_watcher.log",
  "tail": 100
}
```

Returns last 100 lines from file_watcher.log, ignoring time filters.

**View logs for specific time range**
```json
{
  "log_path": "logs/file_watcher.log",
  "from_time": "2025-01-26 10:00:00",
  "to_time": "2025-01-26 11:00:00"
}
```

Returns logs between 10:00 and 11:00 on January 26, 2025.

**Filter by event types**
```json
{
  "log_path": "logs/file_watcher.log",
  "event_types": [
    "new_file",
    "changed_file",
    "deleted_file"
  ]
}
```

Returns only logs for new_file, changed_file, and deleted_file events.

**Search for errors**
```json
{
  "log_path": "logs/vectorization.log",
  "worker_type": "vectorization",
  "log_levels": [
    "ERROR"
  ],
  "search_pattern": "failed"
}
```

Returns ERROR level logs containing 'failed' in vectorization.log.

**Filter by importance (errors and above)**
```json
{
  "worker_type": "file_watcher",
  "importance_min": 8
}
```

Returns log entries with importance >= 8 (errors and critical).

### Incorrect usage

- **LOG_VIEW_ERROR**: File not found, permission denied, or parsing error. Verify log_path exists and is readable. Check file permissions. Ensure log file format is correct.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `LOG_VIEW_ERROR` | General error during log viewing | Verify log_path exists and is readable. Check file |

## Best practices

- Use tail parameter to view recent logs quickly
- Use time filters to narrow down to specific time periods
- Combine event_types and log_levels for precise filtering
- Use search_pattern for regex search on message
- Use importance_min/importance_max to filter by severity (0-10)
- Set appropriate limit to prevent large responses
- Use list_logs to get log identifiers (log_id), then view_worker_logs with log_id to avoid paths
- Use list_worker_logs to find log files by path if needed

---
