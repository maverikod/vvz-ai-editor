# DB retry and worker coordination plan for Qwen

Status: ready for execution by a weak/Qwen model.

Mandatory addendum: [Architecture addendum - project-scoped smart coordination](architecture_addendum.md). Execute it together with Steps 13, 14, 16, 24, 25, 32, and 35.

Scope: `code-analysis-server` source repository only. Do not edit `.venv`, `venv`, `site-packages`, installed packages, generated artifacts, or nested project copies in `test_data` unless a step explicitly creates a temporary test project. Never run destructive checks on `vast_srv`.

Goal: make PostgreSQL transient DB failures, logical write retries, config validation, SQLite compatibility, and watcher/indexer project coordination production-ready and verifiable through MCP behavior.

Execution order is mandatory. Do not start watcher/indexer steps before the DB transient-error and retry contract is implemented and tested.

## Global rules

1. Retry database operations only. Do not put filesystem or network side effects inside retried blocks.
2. Driver-level retry is allowed only for self-managed operations without external `transaction_id`, and only after rollback before the next attempt.
3. For operations with external `transaction_id`, retry must happen only at logical-write RPC level by repeating the whole transaction.
4. Never retry if commit outcome is unknown. Return structured error with `commit_outcome_unknown=true` and `retryable=false`.
5. Canonical config fields only: `write_retry_attempts`, `write_retry_delay_seconds`, `write_retry_backoff_multiplier`, `write_retry_jitter_seconds`, `lock_timeout_seconds`, `statement_timeout_seconds`.
6. Config path is `code_analysis.database.driver.config.<field>`.
7. PostgreSQL retryable SQLSTATE policy: `40P01=deadlock`, `40001=serialization_failure`, `55P03=lock_not_available`. `57014=query_canceled` is retryable only for timeout messages, not manual/external cancel.
8. Do not implement advisory-lock behavior in this plan. Worker coordination uses `project_activity_locks` leases.
9. Every step must be verified by a separate read/test/MCP command and recorded in `docs/observations/db_retry_worker_coordination.md`.

## Steps

00. [Architecture addendum - project-scoped smart coordination](architecture_addendum.md)
01. [Exceptions contract](step_01_exceptions_contract.md)
02. [PostgreSQL error classification](step_02_postgres_error_classification.md)
03. [PostgreSQL transaction timeouts](step_03_postgres_transaction_timeouts.md)
04. [Shared retry policy](step_04_shared_retry_policy.md)
05. [PostgreSQL driver retry](step_05_postgres_driver_retry.md)
06. [RPC logical write retry](step_06_rpc_logical_write_retry.md)
07. [RPC base structured errors](step_07_rpc_base_structured_errors.md)
08. [Logical write metadata type](step_08_logical_write_metadata_type.md)
09. [Client metadata forwarding](step_09_client_metadata_forwarding.md)
10. [Config validator](step_10_config_validator.md)
11. [Schema definition for activity locks](step_11_schema_activity_locks.md)
12. [SQLite/PostgreSQL migrations](step_12_activity_lock_migrations.md)
13. [Worker activity coordinator](step_13_worker_activity_coordinator.md)
14. [Watcher coordination](step_14_watcher_coordination.md)
15. [Ignore purge metadata](step_15_ignore_purge_metadata.md)
16. [Indexer coordination](step_16_indexer_coordination.md)
17. [SQLite retry compatibility](step_17_sqlite_retry_compatibility.md)
18. [Base driver compatibility](step_18_base_driver_compatibility.md)
19. [Client transient fallback](step_19_client_transient_fallback.md)
20. [Unit tests for transient errors](step_20_tests_transient_errors.md)
21. [Unit tests for logical write retry](step_21_tests_rpc_logical_write_retry.md)
22. [Config validator tests](step_22_tests_config_validator.md)
23. [Metadata forwarding tests](step_23_tests_logical_write_metadata.md)
24. [Worker activity tests](step_24_tests_worker_activity.md)
25. [Watcher/indexer coordination tests](step_25_tests_watcher_indexer_coordination.md)
26. [SQLite retry tests](step_26_tests_sqlite_retry.md)
27. [PostgreSQL integration contract tests](step_27_tests_postgres_integration.md)
28. [Observations document](step_28_observations_document.md)
29. [Pre-MCP source verification](step_29_pre_mcp_source_verification.md)
30. [MCP smoke regression](step_30_mcp_smoke_regression.md)
31. [MCP retry behavior check](step_31_mcp_retry_behavior.md)
32. [MCP worker coordination check](step_32_mcp_worker_coordination.md)
33. [Safe project-management regression](step_33_safe_project_management_regression.md)
34. [clear_trash PostgreSQL safety](step_34_clear_trash_safety.md)
35. [Final acceptance criteria](step_35_final_acceptance.md)
36. [Final report](step_36_final_report.md)
