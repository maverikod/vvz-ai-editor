<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic index: tactical_logical_write_operation_batching

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`

## Atomic summary

| Step ID | File |
|---------|------|
| `step_01_logical_write_program_types` | `step_01_logical_write_program_types.md` |
| `step_02_rpc_handlers_base_parse_logical_write` | `step_02_rpc_handlers_base_parse_logical_write.md` |
| `step_03_rpc_handlers_schema_handle_execute_logical_write_operation` | `step_03_rpc_handlers_schema_handle_execute_logical_write_operation.md` |
| `step_04_rpc_server_register_execute_logical_write_operation` | `step_04_rpc_server_register_execute_logical_write_operation.md` |
| `step_05_client_operations_execute_logical_write_operation` | `step_05_client_operations_execute_logical_write_operation.md` |
| `step_06_file_data_batch_subquery_class_ids` | `step_06_file_data_batch_subquery_class_ids.md` |
| `step_07_file_tree_sync_single_logical_write_rpc` | `step_07_file_tree_sync_single_logical_write_rpc.md` |
| `step_08_tests_database_client_logical_write` | `step_08_tests_database_client_logical_write.md` |
| `step_09_tests_driver_rpc_server_logical_write` | `step_09_tests_driver_rpc_server_logical_write.md` |
| `step_10_tests_cst_stable_ids_mock` | `step_10_tests_cst_stable_ids_mock.md` |
| `step_11_tests_file_tree_snapshot_fidelity` | `step_11_tests_file_tree_snapshot_fidelity.md` |
| `step_12_tests_sync_path_contract_and_verification` | `step_12_tests_sync_path_contract_and_verification.md` |

Additional index files in this directory: `atomic_parallel_waves.md` (serialization policy).

## Dependency order (serial)

`01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12`

Steps 01–05 implement protocol + wiring. Steps 06–07 implement caller batching and remove multi-RPC transaction sequences from the sync path. Steps 08–12 add tests and contract verification.
