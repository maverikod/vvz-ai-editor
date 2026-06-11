# Step 07 — Rest schema: duplicates, comprehensive analysis, snapshots, stats, locks

## Goal
Convert remaining schema identity columns to PostgreSQL-first UUID where they are real identities or foreign keys, while leaving non-identity counters/stat rows alone.

## Current code checked
`schema_definition_tables_rest.py` was inspected. It defines these relevant integer identity/reference columns:

```text
code_duplicates.id INTEGER PK

duplicate_occurrences.id INTEGER PK
duplicate_occurrences.duplicate_id INTEGER -> code_duplicates.id
duplicate_occurrences.file_id INTEGER -> files.id

comprehensive_analysis_results.id INTEGER PK
comprehensive_analysis_results.file_id INTEGER -> files.id

file_tree_snapshots.id INTEGER PK
file_tree_snapshots.file_id INTEGER -> files.id
file_tree_snapshot_roots.snapshot_id INTEGER PK/FK -> file_tree_snapshots.id
file_tree_snapshot_nodes.id INTEGER PK
file_tree_snapshot_nodes.snapshot_id INTEGER -> file_tree_snapshots.id
```

Stats/lock tables use text ids or counters and are not part of DB identity migration unless product explicitly decides otherwise:

```text
file_watcher_stats.cycle_id TEXT PK
vectorization_stats.cycle_id TEXT PK
indexing_worker_stats.cycle_id TEXT PK
project_activity_locks.project_id TEXT PK
```

## Prerequisites
Complete first:
- `03-driver-layer-boundaries.md`
- `04-driver-insert-return-contract.md`
- `05-schema-core-files-and-entities.md`
- `06-schema-mid-ast-cst-chunks-vector-index.md`

## Files to edit in this step
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_definition_indexes.py` only if schema tests require immediate index metadata alignment; main index work is Step 08
- tests for rest schema

## Target schema

```text
code_duplicates.id UUID PK

duplicate_occurrences.id UUID PK
duplicate_occurrences.duplicate_id UUID FK -> code_duplicates.id
duplicate_occurrences.file_id UUID FK -> files.id

comprehensive_analysis_results.id UUID PK
comprehensive_analysis_results.file_id UUID FK -> files.id

file_tree_snapshots.id UUID PK
file_tree_snapshots.file_id UUID FK -> files.id
file_tree_snapshot_roots.snapshot_id UUID PK/FK -> file_tree_snapshots.id
file_tree_snapshot_nodes.id UUID PK
file_tree_snapshot_nodes.snapshot_id UUID FK -> file_tree_snapshots.id
```

Keep project IDs as UUID-compatible and validate/cast them, but do not regenerate them.

## Required decisions
1. `file_tree_snapshot_nodes.node_id` is TEXT logical tree node id, not DB row identity. Do not convert it to UUID unless the tree algorithm requires it.
2. `cycle_id` in worker stats is TEXT. Decide separately whether it is already UUID-like. Do not block DB identity migration on this.
3. `project_activity_locks.owner_id` is TEXT lock owner identity. Do not convert unless lock ownership contract requires it.

## Required changes
1. Change real PK/FK identity columns to UUID/logical UUID.
2. Preserve uniqueness constraints:
   - `code_duplicates UNIQUE(project_id, duplicate_hash)`
   - `comprehensive_analysis_results UNIQUE(file_id, file_mtime)`
   - `file_tree_snapshots UNIQUE(file_id)`
   - `file_tree_snapshot_nodes UNIQUE(snapshot_id, node_id)`
   - `file_tree_snapshot_nodes UNIQUE(snapshot_id, parent_node_id, child_index)`
3. Do not alter stats counters such as `files_indexed`, `chunks_processed`, etc.
4. Do not alter queue/worker lifecycle semantics in this step.

## Layering requirements
- Schema definitions express logical UUID fields.
- PostgreSQL-specific UUID DDL belongs to PostgreSQL schema sync/migration layer.
- Command/API changes belong to Step 16.
- Cleanup/trash behavior belongs to Step 17.

## Must not do
- Do not change comprehensive analysis command behavior here.
- Do not treat `node_id` as database identity.
- Do not change worker stats counters to UUID.
- Do not change project trash/delete logic here.
- Do not make schema depend on SQLite FTS rowids.

## Tests required
1. PostgreSQL DDL test for UUID PK/FK columns in rest tables.
2. Snapshot FK test: roots/nodes reference UUID snapshot ids.
3. Duplicate occurrence test: duplicate_id and file_id reference UUID rows.
4. Comprehensive analysis result test: file_id is UUID and uniqueness remains `(file_id, file_mtime)`.
5. Stats tables remain unchanged unless explicitly approved.

## Verification
No live DB migration in this step. Verify schema metadata and generated PostgreSQL DDL only.

## References
- `01-current-schema-inventory.md`
- `08-indexes-and-constraints.md`
- `16-mcp-api-compatibility.md`
- `17-cleanup-trash-repair-commands.md`
