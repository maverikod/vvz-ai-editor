# stop_worker

**Command name:** `stop_worker`  
**Class:** `StopWorkerMCPCommand`  
**Source:** `code_analysis/commands/worker_management_mcp_commands.py`  
**Category:** worker_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The stop_worker command stops background worker processes by type. It stops all workers of the specified type that are registered in WorkerManager. The command attempts graceful shutdown first, then force kills if timeout is exceeded.

Operation flow:
1. Gets WorkerManager instance
2. Retrieves all workers of specified type from registry
3. For each worker:
   - Attempts graceful shutdown (sends termination signal)
   - Waits for process to terminate (up to timeout seconds)
   - If timeout exceeded, force kills the process
4. Unregisters workers from WorkerManager
5. Returns stop summary with counts

Shutdown Process:
- First attempts graceful shutdown (SIGTERM)
- Waits for process to terminate naturally
- If timeout exceeded, force kills (SIGKILL)
- Removes worker from registry

Worker Types:
- file_watcher: Stops all file watcher workers
- vectorization: Stops all vectorization workers

Use cases:
- Stop workers before restarting
- Stop workers for maintenance
- Clean up worker processes

Important notes:
- Stops ALL workers of the specified type
- Graceful shutdown is attempted first
- Force kill is used if timeout exceeded
- Workers are unregistered from WorkerManager
- Default timeout is 10 seconds

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `worker_type` | string | **Yes** | Type of worker to stop. |
| `timeout` | integer | No | Timeout in seconds before force kill. Default: `10`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `worker_type`: Type of workers that were stopped
- `stopped_count`: Number of workers stopped
- `failed_count`: Number of workers that failed to stop
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** WORKER_STOP_ERROR (and others).

---

## Examples

### Correct usage

**Stop file watcher workers**
```json
{
  "worker_type": "file_watcher",
  "timeout": 10
}
```

Stops all file watcher workers gracefully. Force kills if they don't stop within 10 seconds.

**Stop vectorization workers**
```json
{
  "worker_type": "vectorization",
  "timeout": 5
}
```

Stops all vectorization workers gracefully. Force kills if they don't stop within 5 seconds.

### Incorrect usage

- **WORKER_STOP_ERROR**: Process not found, permission denied, or kill failure. Check if workers are running, verify process permissions, ensure WorkerManager is accessible.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `WORKER_STOP_ERROR` | General error during worker stop | Check if workers are running, verify process permi |

## Best practices

- Use graceful shutdown timeout appropriate for worker workload
- Workers should handle SIGTERM for graceful shutdown
- Force kill is used as last resort if timeout exceeded
- Check worker status after stopping to verify shutdown
- Stop workers before restarting to avoid conflicts

---
