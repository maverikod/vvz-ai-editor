# start_repair_worker

**Command name:** `start_repair_worker`  
**Class:** `StartRepairWorkerMCPCommand`  
**Source:** `code_analysis/commands/repair_worker_mcp_commands.py`  
**Category:** repair_worker

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The start_repair_worker command starts a repair worker process that automatically restores database integrity by processing deleted files and restoring them from version directories. The worker runs in a separate process and operates continuously in the background.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Verifies project exists in database
5. Resolves version_dir path (relative to root_dir if not absolute)
6. Resolves shared database path from server config and worker log path
7. Checks if repair worker is already running
8. Starts worker process using multiprocessing
9. Registers worker in WorkerManager
10. Returns start result with PID

Repair Worker Functionality:
- Processes deleted files in batches
- Restores files from version directories
- Updates database to mark files as active
- Runs continuously with configurable poll interval
- Logs activity to repair_worker.log

Worker Configuration:
- batch_size: Number of files processed per batch (default: 10)
- poll_interval: Seconds between repair cycles (default: 30)
- version_dir: Directory containing file versions (default: data/versions)
- worker_log_path: Path to log file (default: logs/repair_worker.log)

Process Management:
- Worker runs as daemon process
- Process is registered in WorkerManager
- PID is returned for monitoring
- Worker can be stopped with stop_repair_worker

Use cases:
- Automatically restore deleted files
- Maintain database integrity
- Recover from accidental file deletions
- Continuous background repair operations
- Automated database maintenance

Important notes:
- Only one repair worker can run at a time
- Worker runs continuously until stopped
- Worker processes files in batches to avoid overload
- Log file is created automatically if it doesn't exist
- Worker is registered in WorkerManager for centralized management

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `version_dir` | string | No | Version directory for deleted files (default: data/versions) Default: `"data/versions"`. |
| `batch_size` | integer | No | Number of files to process per batch (default: 10) Default: `10`. |
| `poll_interval` | integer | No | Interval in seconds between repair cycles (default: 30) Default: `30`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True if worker started, False if already running or failed
- `message`: Human-readable status message
- `pid`: Process ID of started worker (if successful)
- `exit_code`: Exit code if process failed to start (if applicable)
- `error`: Error message if start failed (if applicable)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, START_REPAIR_WORKER_ERROR (and others).

---

## Examples

### Correct usage

**Start repair worker with defaults**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Starts repair worker with default settings: batch_size=10, poll_interval=30, version_dir=data/versions.

**Start with custom configuration**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "batch_size": 20,
  "poll_interval": 60,
  "version_dir": "/backups/versions"
}
```

Starts repair worker with custom batch size, poll interval, and version directory location.

**Start with explicit project ID**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

Starts repair worker for specific project ID. Useful when multiple projects share same root_dir.

### Incorrect usage

- **PROJECT_NOT_FOUND**: Project not found in database. Verify project_id is correct or ensure project is registered. Run update_indexes to register project if needed.

- **START_REPAIR_WORKER_ERROR**: Error starting repair worker. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct or ensure project is  |
| `START_REPAIR_WORKER_ERROR` | Error starting repair worker |  |

## Best practices

- Check repair_worker_status before starting to avoid duplicates
- Use appropriate batch_size based on system resources
- Set poll_interval based on repair urgency (lower = more frequent)
- Monitor worker logs (logs/repair_worker.log) for activity
- Use stop_repair_worker to stop worker when no longer needed
- Verify version_dir exists and contains file versions
- Start worker after database operations that may create deleted files
- Monitor worker with repair_worker_status regularly

---
