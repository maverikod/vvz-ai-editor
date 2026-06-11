# get_worker_status

**Command name:** `get_worker_status`  
**Class:** `GetWorkerStatusMCPCommand`  
**Source:** `code_analysis/commands/worker_status_mcp_commands.py`  
**Category:** worker_status

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_worker_status command monitors worker process status, resource usage, and recent activity. It supports two types of workers: file_watcher and vectorization. The command provides comprehensive information about worker processes including CPU/memory usage, uptime, lock file status, and log activity.

Operation flow:
1. Validates worker_type parameter (file_watcher, vectorization, or indexing)
2. Attempts to get registered workers from WorkerManager
3. If no registered workers, searches for processes by name pattern
4. For file_watcher, checks lock file status if provided
5. Reads PID from PID file if log_path provided (fallback)
6. Collects process information (CPU, memory, uptime)
7. Analyzes recent log activity if log_path provided
8. Returns comprehensive status summary

Worker Types:
- file_watcher: Monitors file system changes and updates database
- vectorization: Processes code chunks and generates embeddings
- indexing: Indexes files with needs_chunking=1 (AST, CST, fulltext)

Process Discovery Methods:
1. WorkerManager: Gets registered workers (most reliable)
2. Process name search: Searches running processes by cmdline pattern
3. Lock file: For file_watcher, uses lock file PID
4. PID file: Reads PID from <worker>.pid file (if log_path provided)

Resource Monitoring:
- CPU usage: Percentage of CPU time used (per process and total)
- Memory usage: Resident Set Size (RSS) in megabytes
- Uptime: Process uptime in seconds
- Process status: Running state (running, sleeping, etc.)

Lock File (file_watcher only):
- Contains PID, creation timestamp, worker name, hostname
- Used to identify active file watcher process
- Validates that process is still alive

Log Activity:
- Analyzes recent log entries (last 10 lines by default)
- Extracts timestamp from log entries
- Calculates age of last entry
- Provides file size information

Use cases:
- Monitor worker health and resource usage
- Troubleshoot worker issues
- Check if workers are running
- Monitor worker performance
- Verify worker activity from logs
- Debug worker startup problems

Important notes:
- Requires psutil library for process information
- Process discovery may find multiple workers of same type
- Lock file is optional but recommended for file_watcher
- Log path is optional but enables activity monitoring
- PID file discovery works if log_path points to .log file

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `worker_type` | string | **Yes** | Type of worker to check |
| `log_path` | string | No | Path to worker log file (optional, for activity check) |
| `lock_file_path` | string | No | Path to lock file (optional, for file_watcher) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `worker_type`: Type of worker checked
- `timestamp`: ISO timestamp of status check
- `processes`: List of worker process information. Each contains:
- pid: Process ID
- status: Process status (running, sleeping, etc.)
- cpu_percent: CPU usage percentage
- memory_mb: Memory usage in megabytes
- create_time: Process creation timestamp
- uptime_seconds: Process uptime in seconds
- cmdline: Process command line (first 3 args)
- `lock_file`: Lock file information (file_watcher only). Contains:
- exists: Whether lock file exists
- pid: PID from lock file
- process_alive: Whether process is still running
- created_at: Lock file creation timestamp
- worker_name: Worker name
- hostname: Hostname where worker runs
- `log_activity`: Recent log activity information. Contains:
- available: Whether log file is available
- file_size_mb: Log file size in megabytes
- last_entry: Last log entry with timestamp and age
- recent_lines_count: Number of recent lines analyzed
- `summary`: (see example)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** WORKER_STATUS_ERROR (and others).

---

## Examples

### Correct usage

**Check file watcher status**
```json
{
  "worker_type": "file_watcher"
}
```

Checks status of file watcher workers. Searches for processes and returns status information.

**Check vectorization worker with log**
```json
{
  "worker_type": "vectorization",
  "log_path": "/home/user/projects/my_project/logs/vectorization.log"
}
```

Checks vectorization worker status and analyzes log activity. Also attempts PID file discovery from log path.

**Check file watcher with lock file**
```json
{
  "worker_type": "file_watcher",
  "lock_file_path": "/home/user/projects/my_project/data/file_watcher.lock",
  "log_path": "/home/user/projects/my_project/logs/file_watcher.log"
}
```

Checks file watcher using lock file for process identification and log file for activity monitoring.

### Incorrect usage

- **WORKER_STATUS_ERROR**: Error during worker status check. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `WORKER_STATUS_ERROR` | Error during worker status check |  |

## Best practices

- Use log_path to enable log activity monitoring
- Use lock_file_path for file_watcher to get accurate process identification
- Check summary.is_running to quickly see if workers are active
- Monitor total_cpu_percent and total_memory_mb for resource usage
- Check log_activity.last_entry.age_seconds to verify recent activity
- Use process_count to detect multiple workers (may indicate issues)
- Check oldest_process_uptime_seconds to see worker stability
- If processes list is empty, worker may not be running

---
