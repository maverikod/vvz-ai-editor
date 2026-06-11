# analyze_timing_bottlenecks

**Command name:** `analyze_timing_bottlenecks`  
**Class:** `AnalyzeTimingBottlenecksMCPCommand`  
**Source:** `code_analysis/commands/log_viewer_mcp_commands.py`  
**Category:** log_viewer

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

SCOPE — This command is about THIS SERVER's own internal operations (the code-analysis server process: its workers, chunking, embedding, DB access, etc.). It does NOT analyze or time user projects that the server indexes or serves. Use it to find performance bottlenecks in the server implementation, not in client/watched project code.

The analyze_timing_bottlenecks command reads a worker log file produced by this server, collects every line that contains a [TIMING] entry (format: [TIMING] op_name duration=X.XXXs [key=value ...]), and aggregates them by operation name. It reports total time, average time, count, min, and max per operation, and returns two bottleneck lists: by total time (operations that consume the most time overall) and by average time (slowest per call).

Operation flow:
1. Resolve log file path: use log_path if provided, otherwise resolve from worker_type and server config (e.g. vectorization -> config_dir/logs/vectorization_worker.log).
2. Open log file for reading (UTF-8, errors replaced).
3. If tail is set: read only the last tail lines (and cap at limit).
4. Otherwise: read lines sequentially up to limit; optionally filter by from_time and to_time using the timestamp at the start of each line (YYYY-MM-DD HH:MM:SS).
5. For each line, detect [TIMING] and parse op_name and duration=X.XXXs with a regex.
6. Aggregate by op_name: collect all durations, then compute count, sum, avg, min, max.
7. Sort operations by total_sec descending; take first top_n as bottlenecks_by_total.
8. Sort operations by avg_sec descending; take first top_n as bottlenecks_by_avg.
9. Return all operations plus the two bottleneck lists and summary counts.

When to use:
- To optimize or debug THIS SERVER's performance (e.g. vectorization worker, indexing, chunking, embedding calls), enable log_all_operations_timing in code_analysis.worker config so that [TIMING] lines are written. Then run this command on the server's worker log to find which internal operations dominate total time or have the highest per-call latency.
- Use tail for the most recent activity; use from_time/to_time for a specific time window.

Log format:
Lines must contain the substring [TIMING] and the pattern 'op_name duration=X.XXXs' (op_name is any non-whitespace token, X.XXX is a float). Unified log format 'YYYY-MM-DD HH:MM:SS | LEVEL | importance | message' is supported; the message part is searched for [TIMING]. Other formats that contain [TIMING] and duration=...s are also accepted if the regex matches.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `log_path` | string | No | Path to log file (optional if worker_type is set and config available) |
| `worker_type` | string | No | Worker type to resolve default log path; default vectorization Default: `"vectorization"`. |
| `from_time` | string | No | Start time filter (ISO or YYYY-MM-DD HH:MM:SS); only lines on or after this time |
| `to_time` | string | No | End time filter (ISO or YYYY-MM-DD HH:MM:SS); only lines before this time |
| `tail` | integer | No | Analyze only last N lines of the log (ignores time filters when set) |
| `limit` | integer | No | Maximum number of log lines to scan (default 50000) Default: `50000`. |
| `top_n` | integer | No | Number of top bottlenecks to return by total and by average time (default 10) Default: `10`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `log_path`: Resolved path of the analyzed log file.
- `from_time`: from_time parameter (or null).
- `to_time`: to_time parameter (or null).
- `tail`: tail parameter (or null).
- `lines_scanned`: Number of log lines read.
- `timing_events`: Number of [TIMING] lines parsed and aggregated.
- `total_duration_sec`: Sum of all operation durations (seconds).
- `operations`: List of all operations, each with: op_name, count, total_sec, avg_sec, min_sec, max_sec. Sorted by total_sec descending.
- `bottlenecks_by_total`: First top_n operations when sorted by total_sec (biggest time consumers overall).
- `bottlenecks_by_avg`: First top_n operations when sorted by avg_sec (slowest per call).
- `message`: Human-readable summary.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** TIMING_DISABLED, MISSING_LOG_PATH, LOG_FILE_NOT_FOUND, LOG_READ_ERROR (and others).

---

## Examples

### Correct usage

**Analyze last 10k lines of vectorization log**
```json
{
  "worker_type": "vectorization",
  "tail": 10000
}
```

Reads last 10000 lines from default vectorization log and reports bottlenecks.

**Analyze by time window**
```json
{
  "log_path": "logs/vectorization_worker.log",
  "from_time": "2025-02-08 00:00:00",
  "to_time": "2025-02-08 23:59:59"
}
```

Analyzes only lines within the given day.

**Top 20 bottlenecks by total and average**
```json
{
  "worker_type": "vectorization",
  "tail": 50000,
  "top_n": 20
}
```

Last 50k lines, return top 20 operations by total time and by average time.

### Incorrect usage

- **TIMING_DISABLED**: log_all_operations_timing is false in code_analysis.worker config; server does not write [TIMING] lines. Set log_all_operations_timing to true in config and restart the server (or the worker) so that timing lines are written. Then run this command again.

- **MISSING_LOG_PATH**: Neither log_path nor worker_type provided, or path could not be resolved from config. Provide log_path explicitly or set worker_type and ensure server config is available.

- **LOG_FILE_NOT_FOUND**: The resolved log file does not exist or is not a regular file. Check path and that the worker has written to the log (e.g. enable log_all_operations_timing and run the worker).

- **LOG_READ_ERROR**: OS error while reading the log file (permission, I/O, etc.). Ensure file is readable and disk is accessible.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `TIMING_DISABLED` | log_all_operations_timing is false in code_analysis.worker c | Set log_all_operations_timing to true in config an |
| `MISSING_LOG_PATH` | Neither log_path nor worker_type provided, or path could not | Provide log_path explicitly or set worker_type and |
| `LOG_FILE_NOT_FOUND` | The resolved log file does not exist or is not a regular fil | Check path and that the worker has written to the  |
| `LOG_READ_ERROR` | OS error while reading the log file (permission, I/O, etc.) | Ensure file is readable and disk is accessible. |

## Best practices

- Remember: this analyzes the server's own code (workers, chunking, DB), not user projects.
- Enable log_all_operations_timing in worker config before collecting data.
- Use tail for recent bottleneck analysis; use from_time/to_time for a specific window.
- Compare bottlenecks_by_total (where time is spent) with bottlenecks_by_avg (slow per call).
- Let the worker run for a while to accumulate timing data before analyzing.

---
