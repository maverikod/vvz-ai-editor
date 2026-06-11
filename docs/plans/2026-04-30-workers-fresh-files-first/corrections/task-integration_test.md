# Task: Integration test — concurrent MCP + workers under PostgreSQL

**Finding:** F-08 from AUDIT_SUMMARY_2.md
**File:** `tests/test_postgres_integration_concurrent.py` (new file)
**Severity:** Medium (the original problem scenario is untested)
**Phase:** 1 (step 7 completion)

---

## Context

The entire plan exists because MCP commands (`list_projects`) timed out when workers
held the DB connection. The pool (3W+2R) was built to fix this. Unit tests verify pool
mechanics (acquire/release, timeout, lane selection). But **no test verifies the
end-to-end scenario**: MCP read commands completing while worker write traffic is active.

## Task

Create an integration test that simulates the original problem:

### Test scenario

1. Set up `PostgreSQLDriver` with pool (3W+2R) using test DSN
2. Start 3 threads simulating worker traffic:
   - Each thread loops `execute` with write SQL (e.g., `INSERT INTO ... / UPDATE ...`)
   - Each holds a write-pool connection for ~100ms per operation (simulate `index_file`)
   - All 3 write slots should be occupied
3. While write slots are busy, run MCP-like read queries from the main thread:
   - `execute("SELECT COUNT(*) FROM projects")` — should use read pool
   - Should complete in < 2s (plan acceptance criterion: `list_projects < 2s`)
4. Assert: read queries succeed without timeout while write pool is saturated

### Test structure

```python
@pytest.mark.skipif(
    not os.environ.get("CODE_ANALYSIS_POSTGRES_TEST_DSN"),
    reason="Live PostgreSQL required"
)
class TestConcurrentMCPAndWorkers:

    def test_read_not_blocked_by_write_saturation(self):
        """MCP read commands complete while all 3 write connections are busy."""
        # 1. Create driver, connect with test DSN
        # 2. Start 3 writer threads (saturate write pool)
        # 3. From main thread, do read queries
        # 4. Assert reads complete in < 2s
        # 5. Stop writers, cleanup

    def test_pool_timeout_on_write_exhaustion(self):
        """4th concurrent write request waits and gets timeout."""
        # 1. Occupy all 3 write slots with long-running threads
        # 2. Try 4th write — should wait then timeout (max_wait_seconds)
        # 3. Assert DriverOperationError with timeout message
```

### Guard rails

- Use `CODE_ANALYSIS_POSTGRES_TEST_DSN` env var — skip if not set
- Create a test-only table, clean up after
- Use `threading.Barrier` to synchronize writer starts
- Keep test under 200 lines

### What NOT to test here

- SQLite subprocess (Phase 2)
- Pool unit mechanics (already tested in `test_postgres_connection_pool.py`)
- Priority field behavior (dead code, see F-01)

## Acceptance criteria

- [ ] Test exists and passes with live PostgreSQL
- [ ] Read queries complete in < 2s while write pool is saturated
- [ ] Test is skipped (not failed) when `CODE_ANALYSIS_POSTGRES_TEST_DSN` is not set
- [ ] Test uses real `PostgreSQLDriver` + pool, not mocks
