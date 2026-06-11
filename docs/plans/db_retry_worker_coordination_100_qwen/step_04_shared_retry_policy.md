# Step 04 — Shared retry policy

Previous: [Step 03](step_03_postgres_transaction_timeouts.md). Next: [Step 05](step_05_postgres_driver_retry.md).

File: `code_analysis/core/retry_policy.py`

## Goal
Use one retry policy implementation in driver/RPC/SQLite code so delay and config names cannot diverge.

## Required changes
1. Create `RetryPolicy` as a small dataclass with fields:
   - `attempts: int = 3`
   - `delay_seconds: float = 0.5`
   - `backoff_multiplier: float = 2.0`
   - `jitter_seconds: float = 0.05`
2. Add `from_driver_config(config: Mapping[str, Any]) -> RetryPolicy` reading only canonical names:
   - `write_retry_attempts`
   - `write_retry_delay_seconds`
   - `write_retry_backoff_multiplier`
   - `write_retry_jitter_seconds`
3. Add `delay_for_attempt(attempt_1based: int) -> float`.
4. Delay formula: `delay_seconds * backoff_multiplier ** (attempt_1based - 1)` plus bounded jitter in range `[-jitter_seconds, +jitter_seconds]`. Final delay must be `>= 0`.
5. This file must not import PostgreSQL or SQLite driver modules.

## Forbidden
- Do not introduce alias names.
- Do not hide validation here; range validation belongs to [Step 10](step_10_config_validator.md).

## Verification
Run import/unit test or CST query to verify `RetryPolicy`, `from_driver_config`, and `delay_for_attempt` exist.
