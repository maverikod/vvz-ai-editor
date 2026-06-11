# Step 28 - Observations document

Previous: [Step 27](step_27_tests_postgres_integration.md). Next: [Step 29](step_29_pre_mcp_source_verification.md).

File: `docs/observations/db_retry_worker_coordination.md`

## Goal

Keep execution evidence in one place. A step is not complete until its behavior is verified and recorded.

## Required content

1. Create the observations file if it does not exist.
2. Add a section for every completed implementation block, test block, MCP check, and skipped test group.
3. Do not mark a step complete based only on code inspection.
4. Do not omit failed or skipped tests.

## Required bug report template

Use this exact format when a bug is found:

```text
Command:
Expected:
Actual:
Error:
Root cause:
Fix:
Post-fix verification:
Status:
```

## Required non-bug verification template

Use this exact format for every non-bug verification:

```text
Step:
Command:
Expected:
Actual:
Verification command:
Verification result:
Status:
```

## Required skip template

Use this exact format for skipped tests or unavailable optional environments:

```text
Step:
Skipped item:
Reason:
Mandatory alternative evidence:
Status:
```

Example: PostgreSQL integration tests may be skipped only when PostgreSQL test configuration is unavailable. The mandatory alternative evidence must include Step 20 unit tests and any deterministic fake-driver coverage required by the plan.

## Queue evidence rule

For queue checks, record both outer queue status and inner command success.

Required fields:

- outer `status`
- outer `progress`
- inner `result.command.result.success`
- inner error details if success is false

Outer `status=completed` and `progress=100` are not enough.

## Destructive/safety evidence rule

For destructive project-management checks, record target validation before command execution:

- `project_id`
- name
- path
- deleted flag
- files count if available
- chunks count if available
- explicit confirmation target is not `vast_srv`

## Worker coordination evidence rule

For worker coordination checks, record:

- owner that acquired the project lease;
- owner that skipped/deferred;
- `project_id`;
- whether unrelated project processing continued;
- separate read/log verification command;
- `[WORKER_COORD]` log evidence.

## Retry evidence rule

For retry checks, record:

- operation name;
- backend;
- layer;
- attempt count;
- SQLSTATE if present;
- error kind;
- `[DB_RETRY]` log evidence;
- whether commit outcome was known or unknown.

## Forbidden

- Do not mark a step complete based only on code inspection.
- Do not omit failed or skipped tests.
- Do not describe queue job as successful unless the inner command result is successful.
- Do not report skipped PostgreSQL tests as passed.

## Verification

Read the observations file after creation and confirm the templates and evidence rules are present. Record command, expected result, actual result, and status in the observations file itself.
