# Step 22 - Config validator tests

Previous: [Step 21](step_21_tests_rpc_logical_write_retry.md). Next: [Step 23](step_23_tests_logical_write_metadata.md).

File: `tests/test_database_driver_config_validator_retry.py`

## Goal

Prove retry and timeout config validation is strict, canonical, and backward-compatible.

## Required tests

1. `test_existing_config_without_retry_timeout_fields_passes`
   - Existing database driver config with no new retry/timeout fields still passes.

2. `test_postgres_config_with_valid_canonical_fields_passes`
   - PostgreSQL config passes with all canonical fields:
     - `write_retry_attempts`
     - `write_retry_delay_seconds`
     - `write_retry_backoff_multiplier`
     - `write_retry_jitter_seconds`
     - `lock_timeout_seconds`
     - `statement_timeout_seconds`

3. `test_sqlite_config_with_valid_canonical_retry_fields_passes`
   - SQLite config passes with retry fields.
   - SQLite config may include timeout fields only if Step 10 explicitly allows them for SQLite; otherwise the test must assert the documented behavior from Step 10.

4. `test_sqlite_proxy_config_with_valid_canonical_retry_fields_passes`
   - SQLite proxy config passes with retry fields.
   - Timeout field behavior must match Step 10 exactly.

5. `test_invalid_retry_attempts_ranges_fail`
   - `write_retry_attempts < 1` fails.
   - `write_retry_attempts > 20` fails.
   - Non-integer `write_retry_attempts` fails.

6. `test_invalid_delay_backoff_jitter_ranges_fail`
   - Negative delay fails.
   - Negative jitter fails.
   - `write_retry_backoff_multiplier < 1.0` fails.
   - Values above Step 10 maximums fail.

7. `test_invalid_timeout_ranges_fail`
   - `lock_timeout_seconds <= 0` fails when present.
   - `lock_timeout_seconds > 300` fails.
   - `statement_timeout_seconds <= 0` fails when present.
   - `statement_timeout_seconds > 3600` fails.

8. `test_invalid_types_fail_with_clear_messages`
   - Strings, booleans, lists, and dicts for numeric fields fail with clear field names in the error.

9. `test_deprecated_aliases_fail_with_suggestion`
   - `retry_attempts` fails with suggestion to use `write_retry_attempts`.
   - `retry_delay_seconds` fails with suggestion to use `write_retry_delay_seconds`.

10. `test_no_unknown_retry_aliases_are_silently_accepted`
   - Misspelled retry/timeout aliases must not be silently accepted as canonical fields.

## Implementation notes

- Test the validator function changed in [Step 10](step_10_config_validator.md).
- Do not require a live database.
- Use exact config path `code_analysis.database.driver.config.<field>` in test data and expected error messages when possible.

## Forbidden

- Do not accept alias names.
- Do not move config to another section.
- Do not make tests pass by ignoring invalid fields.

## Verification

Run this test file and record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
