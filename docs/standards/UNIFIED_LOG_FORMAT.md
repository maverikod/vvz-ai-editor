# Unified log format and log analyzer

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All worker and server logs SHOULD use the same line format. One log analyzer parses and filters all log files regardless of worker type.

---

## 1. Unified line format

Every log line SHOULD follow:

```
YYYY-MM-DD HH:MM:SS | LEVEL | IMPORTANCE | message
```

- **Timestamp**: `YYYY-MM-DD HH:MM:SS` (local time; no timezone in line).
- **LEVEL**: One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (standard logging level).
- **IMPORTANCE**: Integer **0–10** (see [LOG_IMPORTANCE_CRITERIA.md](LOG_IMPORTANCE_CRITERIA.md)); separate column for operational impact/urgency.
- **message**: Free text (no `|` in message, or escape it).

**Example:**

```
2026-02-05 14:30:01 | INFO | 4 | Cycle #2 completed; 5 files processed
2026-02-05 14:30:02 | ERROR | 8 | Indexing failed for /path/to/file.py: connection refused
```

Legacy formats (e.g. `timestamp - level - message` or 3-part `timestamp | level | message`) are still parsed; importance is then derived from LEVEL (DEBUG→2, INFO→4, WARNING→6, ERROR→8, CRITICAL→10).

---

## 2. Date/time interval (partial or full)

The analyzer accepts an optional **time range**:

- **from_time** only: return lines with `timestamp >= from_time`.
- **to_time** only: return lines with `timestamp <= to_time`.
- **Both**: return lines where `from_time <= timestamp <= to_time`.

So the interval can be **partially** specified (e.g. “from 2026-02-01” or “until 2026-02-05 12:00:00”).  
Time format: ISO (`YYYY-MM-DDTHH:MM:SS`) or `YYYY-MM-DD HH:MM:SS` or date-only `YYYY-MM-DD` (implies 00:00:00 for that day).

---

## 3. Search by message (regex)

- The **search_pattern** parameter is a **regular expression** applied to the **message** part of each line.
- Matching is case-insensitive unless the regex specifies otherwise.
- Only lines whose message matches the regex are returned (in addition to other filters).

---

## 4. Single analyzer for all logs

- **One** log analyzer implementation is used for **all** log files (file_watcher, vectorization, indexing, database_driver, server, etc.).
- The same parser handles:
  - Unified format (4 parts: timestamp | level | importance | message).
  - Legacy formats (3 parts or “timestamp - level - message”); importance is derived from level.
- The same filters apply everywhere:
  - Optional **from_time** / **to_time** (partial or full interval).
  - Optional **log_levels** (DEBUG, INFO, …).
  - Optional **importance_min** / **importance_max** (0–10).
  - Optional **search_pattern** (regex on message).
  - Optional **event_types** (regex-based event tags; same pattern set for all, or per worker_type for backward compatibility).
- Output is uniform: each entry has **timestamp**, **level**, **importance** (0–10), **message**, and optional **event_type**, **line_number**.

---

## 5. Implementing the format in workers

To emit the unified format (with importance), workers should:

1. Use a **fixed date format**: `datefmt="%Y-%m-%d %H:%M:%S"`.
2. Use a **formatter** that outputs: `%(asctime)s | %(levelname)-8s | %(importance)s | %(message)s`.
3. Set **importance** via a logging adapter or `LogRecord` extra: e.g. `extra={"importance": 4}` for normal info, or use a custom `LoggerAdapter` that adds `importance` from a rule/criteria table (see LOG_IMPORTANCE_CRITERIA.md).

Until all workers are updated, the analyzer will continue to accept legacy formats and default importance from level.
