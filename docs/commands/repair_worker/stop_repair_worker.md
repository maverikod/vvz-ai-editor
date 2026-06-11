# stop_repair_worker

**Command name:** `stop_repair_worker`  
**Class:** `StopRepairWorkerMCPCommand`  
**Source:** `code_analysis/commands/repair_worker_mcp_commands.py`  
**Category:** repair_worker

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The stop_repair_worker command stops running repair worker processes gracefully or forcefully. It finds all repair worker processes and terminates them using SIGTERM (graceful) or SIGKILL (force).

Operation flow:
1. Searches for all repair worker processes
2. If no processes found, returns success immediately
3. For each process:
   - If force=True: Immediately sends SIGKILL
   - If force=False: Sends SIGTERM and waits for graceful shutdown
   - If timeout exceeded: Sends SIGKILL
4. Verifies processes are terminated
5. Returns summary of stopped processes

Stop Methods:
- Graceful (force=False): Sends SIGTERM, waits for process to exit
  - Allows worker to finish current batch
  - Clean shutdown with proper cleanup
  - Uses timeout to prevent hanging
- Force (force=True): Immediately sends SIGKILL
  - Immediate termination
  - No cleanup, may leave incomplete operations
  - Use only when graceful stop fails

Timeout Behavior:
- If force=False, waits up to timeout seconds for graceful shutdown
- If process doesn't exit within timeout, sends SIGKILL
- Default timeout is 10 seconds
- Timeout prevents hanging if process is unresponsive

Process Discovery:
- Searches for processes with 'repair_worker' or 'run_repair_worker' in cmdline
- Uses psutil to find and manage processes
- Handles multiple worker processes if present

Use cases:
- Stop repair worker when no longer needed
- Stop worker before maintenance operations
- Force stop unresponsive worker
- Clean shutdown before system restart
- Stop worker to change configuration

Important notes:
- Graceful stop is preferred (allows cleanup)
- Force stop should be used only when necessary
- Multiple processes may be stopped if found
- Process discovery requires psutil library
- Worker is automatically unregistered from WorkerManager

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `timeout` | integer | No | Timeout in seconds before force kill (default: 10) Default: `10`. |
| `force` | boolean | No | If True, immediately kill with SIGKILL (default: False) Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: True if all processes stopped, False if any failed
- `message`: Human-readable status message
- `killed`: List of successfully stopped processes. Each contains: pid
- `failed`: List of processes that failed to stop. Each contains: pid, error

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** STOP_REPAIR_WORKER_ERROR (and others).

---

## Examples

### Correct usage

**Stop worker gracefully**
```json
{
  "timeout": 10,
  "force": false
}
```

Stops repair worker gracefully with 10 second timeout. Allows worker to finish current batch.

**Force stop worker immediately**
```json
{
  "force": true
}
```

Immediately kills repair worker with SIGKILL. Use only when graceful stop fails.

**Stop with longer timeout**
```json
{
  "timeout": 30,
  "force": false
}
```

Stops worker gracefully with 30 second timeout. Gives worker more time to finish current operations.

### Incorrect usage

- **STOP_REPAIR_WORKER_ERROR**: Error stopping repair worker. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `STOP_REPAIR_WORKER_ERROR` | Error stopping repair worker |  |

## Best practices

- Use graceful stop (force=False) when possible
- Set appropriate timeout based on batch processing time
- Use force=True only when graceful stop fails
- Check repair_worker_status after stop to verify
- Monitor killed and failed lists in response
- Retry stop if process is still running
- Stop worker before database maintenance operations
- Stop worker before system restart or shutdown

---
