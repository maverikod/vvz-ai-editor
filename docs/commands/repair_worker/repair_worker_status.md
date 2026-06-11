# repair_worker_status

**Command name:** `repair_worker_status`  
**Class:** `RepairWorkerStatusMCPCommand`  
**Source:** `code_analysis/commands/repair_worker_mcp_commands.py`  
**Category:** repair_worker

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The repair_worker_status command monitors repair worker process status, resource usage, and recent activity. It provides comprehensive information about running repair worker processes including CPU/memory usage, uptime, and log activity.

Operation flow:
1. If root_dir provided, resolves worker log path
2. Creates RepairWorkerManager with minimal config
3. Searches for repair worker processes by name pattern
4. Gets process details (PID, CPU, memory, uptime) for each process
5. Analyzes recent log activity if log file exists
6. Calculates summary statistics
7. Returns comprehensive status report

Process Discovery:
- Searches for processes with 'repair_worker' or 'run_repair_worker' in cmdline
- Uses psutil to find and query processes
- Handles multiple worker processes if present

Resource Monitoring:
- CPU usage: Percentage of CPU time used (per process and total)
- Memory usage: Resident Set Size (RSS) in megabytes
- Uptime: Process uptime in seconds
- Process status: Running state (running, sleeping, etc.)

Log Activity:
- Analyzes recent log entries (last 10 lines by default)
- Extracts timestamp from log entries
- Calculates age of last entry
- Provides file size information
- Only available if root_dir provided and log file exists

Summary Statistics:
- process_count: Number of worker processes found
- is_running: True if any processes are running
- total_cpu_percent: Total CPU usage across all processes
- total_memory_mb: Total memory usage in megabytes
- oldest_process_uptime_seconds: Uptime of oldest process

Use cases:
- Monitor worker health and resource usage
- Check if worker is running
- Troubleshoot worker issues
- Monitor worker performance
- Verify worker activity from logs
- Debug worker startup problems

Important notes:
- Requires psutil library for process information
- Process discovery may find multiple workers
- Log activity requires root_dir to locate log file
- If no processes found, is_running will be False
- Log file path: root_dir/logs/repair_worker.log

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `worker_type`: Always 'repair'
- `is_running`: True if any processes are running
- `processes`: List of process information. Each contains:
- pid: Process ID
- cpu_percent: CPU usage percentage
- memory_mb: Memory usage in megabytes
- create_time: Process creation timestamp
- uptime_seconds: Process uptime in seconds
- status: Process status (running, sleeping, etc.)
- `log_activity`: Recent log activity information (if root_dir provided). Contains:
- available: Whether log file is available
- file_size_mb: Log file size in megabytes
- last_entry: Last log entry with timestamp and age
- recent_lines_count: Number of recent lines analyzed
- `summary`: (see example)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** REPAIR_WORKER_STATUS_ERROR (and others).

---

## Examples

### Correct usage

**Check worker status with log activity**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Checks repair worker status and analyzes log activity. Provides comprehensive monitoring information.

### Incorrect usage

- **REPAIR_WORKER_STATUS_ERROR**: Error during status check. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `REPAIR_WORKER_STATUS_ERROR` | Error during status check |  |

## Best practices

- Use root_dir parameter to enable log activity monitoring
- Check summary.is_running to quickly see if worker is active
- Monitor total_cpu_percent and total_memory_mb for resource usage
- Check log_activity.last_entry.age_seconds to verify recent activity
- Use process_count to detect multiple workers (may indicate issues)
- Check oldest_process_uptime_seconds to see worker stability
- If processes list is empty, worker is not running
- Monitor regularly to ensure worker is functioning correctly

---
