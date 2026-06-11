# Step 19 - Client transient fallback

Previous: [Step 18](step_18_base_driver_compatibility.md). Next: [Step 20](step_20_tests_transient_errors.md).

File: `code_analysis/core/database_client/transient.py`

## Goal

Keep old string-based transient helpers only as backward compatibility fallback. New retry decisions must prefer structured error data.

## Required changes

1. Keep existing public SQLite/RPC helper functions when imports still reference them.
2. Before removing or changing any public helper, search the repository for imports/callers and update all affected code in the same step.
3. Add a module-level note: preferred transient source is structured `ErrorResult.data` from [Step 06](step_06_rpc_logical_write_retry.md) and [Step 07](step_07_rpc_base_structured_errors.md).
4. Add helper `is_structured_retryable_error(data: Mapping[str, Any] | None) -> bool`.
5. `is_structured_retryable_error` must return `True` only when:
   - `data` is a mapping;
   - `data.get("retryable") is True`;
   - `data.get("commit_outcome_unknown") is not True`.
6. `is_structured_retryable_error` must return `False` for missing data, malformed data, `retryable=False`, or `commit_outcome_unknown=True`.
7. PostgreSQL retry decisions must not depend on parsing strings such as `deadlock detected`.
8. SQLite fallback string matching may remain only for backward compatibility and must be documented as fallback behavior.

## Forbidden

- Do not introduce client-side retry loops here.
- Do not parse PostgreSQL SQLSTATE strings here.
- Do not remove public helpers without checking all imports.
- Do not make string parsing the primary PostgreSQL transient-error source.

## Verification

1. Search/CST check confirms the module-level note and `is_structured_retryable_error` exist.
2. Unit tests cover true, false, missing, malformed, and `commit_outcome_unknown=True` data cases.
3. Existing tests using old helpers still pass.
4. Record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
