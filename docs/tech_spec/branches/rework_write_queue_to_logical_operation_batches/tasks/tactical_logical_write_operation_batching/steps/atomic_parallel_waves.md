<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic parallel waves: tactical_logical_write_operation_batching

## Parent links

- Tech spec: `docs/tech_spec/tech_spec.md`
- Global step: `docs/tech_spec/steps/rework_write_queue_to_logical_operation_batches.md`
- Tactical task: `docs/tech_spec/branches/rework_write_queue_to_logical_operation_batches/tasks/tactical_logical_write_operation_batching.md`

## Policy

This workstream is **mostly serial**. Do **not** parallelize coding across steps **01–07** (each step depends on the previous).

**Wave A (serial):** steps **01 → 05** — types, handler parsing, RPC handler implementation, `rpc_server` registration, `DatabaseClient` method.

**Wave B (serial):** steps **06 → 07** — `file_data_batch` SQL/batch construction, then `file_tree_sync` orchestration.

**Wave C (serial):** steps **08 → 12** — tests and contract verification.

There is **no** safe parallel wave for independent code files in this batch because later steps assume earlier API and behavior exists.
