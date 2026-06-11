# start_worker

**Command name:** `start_worker`  
**Class:** `StartWorkerMCPCommand`  
**Source:** `code_analysis/commands/worker_management_mcp_commands.py`  
**Category:** worker_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The start_worker command starts a background worker process in a separate process. Supported worker types are 'file_watcher' and 'vectorization'. The worker is registered in WorkerManager and runs as a daemon process.

Operation flow:
1. Validates root_dir exists and is a directory
2. Loads config.json to get storage paths
3. Opens database connection
4. For file_watcher:
   - Projects are discovered automatically in watch_dirs
   - Resolves watch_dirs (defaults to [root_dir] if not provided)
   - Starts file watcher worker process
   - Registers worker in WorkerManager
5. For vectorization:
   - Gets base FAISS directory (project-scoped indexes: {faiss_dir}/{project_id}.bin)
   - Loads SVO config for embedding service
   - Starts universal vectorization worker process
   - Registers worker in WorkerManager
6. Returns worker start result with PID

File Watcher Worker:
- Monitors directories for file changes
- Discovers projects automatically by finding projectid files
- Scans at specified scan_interval
- Processes new, changed, and deleted files
- Uses lock files to prevent concurrent processing
- Stores deleted files in version directory

Vectorization Worker:
- Processes code chunks for vectorization
- Converts chunks to embeddings using embedding service
- Stores vectors in FAISS index
- Polls database at specified poll_interval
   - Processes chunks in batches
   - Uses project-scoped FAISS index ({faiss_dir}/{project_id}.bin)
   - Automatically discovers all projects from database
   - Processes projects sequentially, sorted by pending count

Use cases:
- Start file watcher to monitor project changes
- Start vectorization worker to process code chunks
- Run workers in background for continuous processing

Important notes:
- Workers run as daemon processes
- Workers are registered in WorkerManager
- File watcher discovers projects automatically
- Vectorization worker is universal - processes all projects from database automatically
- Vectorization worker uses project-scoped FAISS indexes (no dataset concept)
- Workers write logs to specified log path
- Use stop_worker to stop workers gracefully

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `worker_type` | string | **Yes** | Type of worker to start. |
| `project_id` | string | **Yes** | Project UUID (used to resolve project root and storage paths). |
| `watch_dirs` | array | No | Directories to watch (file_watcher only; default: project root). |
| `scan_interval` | integer | No | Scan interval seconds (file_watcher only). Default: `60`. |
| `poll_interval` | integer | No | Poll interval seconds (vectorization only). Default: `30`. |
| `batch_size` | integer | No | Batch size (vectorization only). Default: `10`. |
| `vector_dim` | integer | No | Vector dimension (vectorization only). Default: `384`. |
| `worker_log_path` | string | No | Optional log path for the worker process. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Whether worker was started successfully
- `worker_type`: Type of worker that was started
- `pid`: Process ID of the worker process
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** WORKER_START_ERROR (and others).

---

## Examples

### Correct usage

**Start file watcher worker**
```json
{
  "worker_type": "file_watcher",
  "root_dir": "/home/user/projects/my_project",
  "scan_interval": 60
}
```

Starts file watcher worker that monitors root_dir for file changes. Projects are discovered automatically.

**Start vectorization worker**
```json
{
  "worker_type": "vectorization",
  "root_dir": "/home/user/projects/my_project",
  "poll_interval": 30,
  "batch_size": 10
}
```

Starts universal vectorization worker that processes code chunks for embedding. Worker automatically discovers all projects from database and processes them sequentially.

**Start file watcher with custom watch directories**
```json
{
  "worker_type": "file_watcher",
  "root_dir": "/home/user/projects",
  "watch_dirs": [
    "/home/user/projects/proj1",
    "/home/user/projects/proj2"
  ]
}
```

Starts file watcher that monitors multiple directories. Projects are discovered in each directory.

### Incorrect usage

- **WORKER_START_ERROR**: Process start failure, database error, or config error. Check database integrity, verify config.json exists, ensure embedding service is configured (for vectorization), check file permissions.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `WORKER_START_ERROR` | General error during worker start | Check database integrity, verify config.json exist |

## Best practices

- Use stop_worker to stop workers gracefully before restarting
- File watcher discovers projects automatically - no need to specify project_id
- Vectorization requires embedding service to be configured
- Adjust scan_interval and poll_interval based on workload
- Monitor worker logs to ensure proper operation
- Workers run as daemon processes - they stop when parent process stops

---
