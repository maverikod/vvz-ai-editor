# Step 23 - Metadata forwarding tests

Previous: [Step 22](step_22_tests_config_validator.md). Next: [Step 24](step_24_tests_worker_activity.md).

File: `tests/test_logical_write_program_metadata.py`

## Goal

Prove logical-write metadata is backward-compatible, validated by the client, and forwarded to RPC without adding client-side retry or project-lock behavior.

## Required tests

1. `test_program_with_only_batches_preserves_old_behavior`
   - Program with only `batches` still works.
   - RPC params contain `batches` and do not invent `operation_name`, `project_id`, or `lock_scope` fields unless current RPC contract requires explicit default `lock_scope="none"`.

2. `test_defer_constraints_is_preserved`
   - Program with `defer_constraints=True` still sends `defer_constraints=True`.
   - Existing batch conversion behavior remains unchanged.

3. `test_metadata_fields_are_forwarded`
   - Program with `operation_name`, `project_id`, and `lock_scope` sends all three fields to RPC params unchanged.

4. `test_valid_lock_scope_values`
   - Valid `lock_scope` values are exactly `none`, `project_write`, and `project_read`.

5. `test_invalid_operation_name_type_raises_value_error`
   - Non-string `operation_name` raises `ValueError` before RPC call.

6. `test_invalid_project_id_type_raises_value_error`
   - Non-string `project_id` raises `ValueError` before RPC call.

7. `test_invalid_lock_scope_raises_value_error`
   - Unknown `lock_scope` raises `ValueError` before RPC call.

8. `test_metadata_forwarding_does_not_retry_client_side`
   - The client method does not sleep, loop, parse SQLSTATE, or retry RPC calls.

9. `test_metadata_forwarding_does_not_acquire_project_activity_locks`
   - Forwarding `project_id` or `lock_scope` does not call the Step 13 coordinator.
   - Project activity acquisition belongs to worker coordination steps, not this client metadata step.

## Implementation notes

- Use a fake RPC client that records call name and params.
- Test changes from [Step 08](step_08_logical_write_metadata_type.md) and [Step 09](step_09_client_metadata_forwarding.md).
- No real database required.

## Forbidden

- Do not add client-side retry loops.
- Do not parse SQLSTATE in client metadata forwarding tests.
- Do not acquire project activity locks in this test or implementation step.
- Do not change the `batches` structure.

## Verification

Run this test file and record command, expected result, actual result, and status in [Step 28 observations](step_28_observations_document.md).
