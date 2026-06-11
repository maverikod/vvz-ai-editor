# Step 10 — Config validator

Previous: [Step 09](step_09_client_metadata_forwarding.md). Next: [Step 11](step_11_schema_activity_locks.md).

File: `code_analysis/core/config_validator/section_database_driver.py`

Goal: validate canonical retry and timeout settings under `code_analysis.database.driver.config`.

Required changes:
1. Accept old configs without new fields.
2. Validate `write_retry_attempts`: integer, 1..20.
3. Validate `write_retry_delay_seconds`: number, 0..60.
4. Validate `write_retry_backoff_multiplier`: number, 1.0..10.0.
5. Validate `write_retry_jitter_seconds`: number, 0..10.
6. Validate `lock_timeout_seconds`: number, >0..300 when present.
7. Validate `statement_timeout_seconds`: number, >0..3600 when present.
8. Allow these fields for `postgres`, `sqlite`, and `sqlite_proxy`.
9. Reject aliases `retry_attempts` and `retry_delay_seconds` with a clear suggestion to use canonical names.

Forbidden: do not move config to another section. Do not introduce new names.

Verification: run validator tests from [Step 22](step_22_tests_config_validator.md) and read the file to confirm all canonical fields are present.
