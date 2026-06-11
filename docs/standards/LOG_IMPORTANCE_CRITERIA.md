# Log message importance level (0–10): criteria

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document defines how to assign the **importance** value (0–10) to a log message. Importance is stored in a separate column from the standard log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) and indicates **business/operational impact** and **urgency of attention**.

---

## Scale

| Value | Name / meaning | When to use |
|-------|----------------|-------------|
| **0** | Trace / noise | Very low value for diagnostics; can be ignored in normal operation (e.g. per-item debug). |
| **1** | Low / verbose | Detailed flow or state; useful only for deep debugging. |
| **2** | Debug | Debug-level detail (e.g. internal state, non-critical decisions). |
| **3** | Minor info | Informational, no impact on correctness or availability (e.g. “retry attempt 1 of 3”). |
| **4** | Info | Normal operational events (e.g. “cycle started”, “file processed”). |
| **5** | Notice | Notable but expected (e.g. “backoff applied”, “queue not empty”). |
| **6** | Warning | Something unexpected but handled; may need attention later (e.g. “fallback used”, “slow response”). |
| **7** | Warning+ | Warning with possible impact on quality or performance; should be reviewed. |
| **8** | Error | Error condition; operation failed for one item or one request but service continues. |
| **9** | Severe | Error affecting a major function or multiple items; partial outage or data risk. |
| **10** | Critical | Failure that threatens availability, data integrity, or security; requires immediate action. |

---

## Criteria in more detail

### 0–2: Trace / debug

- **0**: Per-entity or per-request trace; high volume; typically disabled in production.
- **1**: Verbose internal state; useful only when debugging a specific component.
- **2**: Standard DEBUG; e.g. “entering function X”, “config value Y”.

**Rule of thumb**: Would a support engineer need this only when reproducing a bug? → 0–2.

---

### 3–4: Informational

- **3**: Minor operational info; no impact on correctness or SLA (e.g. “retry in 2s”, “cache miss”).
- **4**: Normal operation (e.g. “cycle completed”, “file indexed”, “connection established”).

**Rule of thumb**: “Everything is working as designed” → 3–4.

---

### 5: Notice

- Expected but noteworthy: backoff, fallback, degraded path, or “expected” errors that are handled.
- No immediate action; useful for capacity or quality analysis.

**Rule of thumb**: “We handled it, but it’s worth a look later” → 5.

---

### 6–7: Warnings

- **6**: Recoverable or local issue (e.g. one file failed, one request timed out, fallback used).
- **7**: Warning with broader impact (e.g. repeated failures, resource exhaustion risk, quality degradation).

**Rule of thumb**: “No outage yet, but could become one if it continues” → 6–7.

---

### 8: Error

- A distinct operation or request failed (e.g. one file not indexed, one RPC failed).
- Other work continues; no data loss or full service failure.

**Rule of thumb**: “One thing failed; the rest is still running” → 8.

---

### 9: Severe

- Major feature or component impaired (e.g. all files in a project failing, driver unreachable for a long time).
- Partial outage or risk of data inconsistency.

**Rule of thumb**: “A significant part of the system is broken or at risk” → 9.

---

### 10: Critical

- Total failure of a critical path, data loss/corruption risk, or security incident.
- Requires immediate human or automated response.

**Rule of thumb**: “Service or data is at serious risk right now” → 10.

---

## Mapping from standard log level (defaults)

When a message has no explicit importance, the analyzer can derive it from the log level:

| Level    | Default importance |
|----------|--------------------|
| DEBUG    | 2                  |
| INFO     | 4                  |
| WARNING  | 6                  |
| ERROR    | 8                  |
| CRITICAL | 10                 |

Explicit importance in the log line overrides this default.

---

## Examples (by importance)

- **0**: “Processing chunk id=12345”
- **2**: “Config: poll_interval=30”
- **4**: “Cycle #3 completed; 5 files processed”
- **5**: “Circuit breaker open; using fallback”
- **6**: “File X skipped (parse error); continuing”
- **8**: “Indexing failed for project P: connection refused”
- **9**: “Database driver unreachable; all indexing stopped”
- **10**: “Database file corrupted; integrity check failed”

---

## Summary

- **0–2**: Diagnostics only; low urgency.  
- **3–5**: Informational/notice; no immediate action.  
- **6–7**: Warnings; review when possible.  
- **8**: Error; one operation failed.  
- **9**: Severe; significant part of system affected.  
- **10**: Critical; immediate action required.

Importance is **independent** of DEBUG/INFO/WARNING/ERROR/CRITICAL: the same level (e.g. ERROR) can have different importance (8 vs 9 vs 10) depending on impact. Use this document to assign the 0–10 value when writing or classifying log messages.
