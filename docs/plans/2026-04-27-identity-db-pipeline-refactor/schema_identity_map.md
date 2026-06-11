# Schema identity map — current state and audit output

## Status

This file is the required output artifact for Step 05 (`05-code_analysis_core_database_schema_identity.md`), aligned with Step 12 (`12-uuid_business_identity_transition.md`). Content is derived from the Python schema definition modules only (no live DB inspection, no migration edits).

## Source files read

- `code_analysis/core/database/schema_definition_tables_core.py`
- `code_analysis/core/database/schema_definition_tables_mid.py`
- `code_analysis/core/database/schema_definition_tables_rest.py`
- `code_analysis/core/database/schema_definition_indexes.py`
- `code_analysis/core/database/schema_sync_sql_postgres.py` — generates PostgreSQL DDL from the same dicts (IDENTITY for integer autoincrement PKs, same UNIQUE/FK strings).
- `code_analysis/core/database/sqlite_to_postgres.py` — migration concerns (e.g. `code_chunks` dedupe by `chunk_uuid`), not alternate PK/FK shapes.

## Schema graph (high level)

```text
watch_dirs (TEXT id, app-supplied)
  └── FK ← watch_dir_paths.watch_dir_id (PK), ON DELETE CASCADE
  └── FK ← projects.watch_dir_id (nullable), ON DELETE SET NULL
  └── FK ← files.watch_dir_id (nullable), ON DELETE SET NULL

projects (TEXT id, app-supplied)
  └── FK ← files.project_id, ON DELETE CASCADE
  └── FK ← [many tables].project_id — see § AST/CST and project-scoped tables

files (INTEGER id, autoincrement)
  └── FK parent: projects, watch_dirs (optional)
  └── FK ← classes, functions, imports, usages, code_content, ast_trees, cst_trees,
             issues (optional), entity_cross_ref (optional), duplicate_occurrences,
             comprehensive_analysis_results, file_tree_snapshots, code_chunks
```

Integer identity hub: `files.id` and `code_chunks.id` (and class/method/function/import chains) are **INTEGER autoincrement**; `projects.id` / `watch_dirs.id` are **TEXT** (UUID-like strings supplied by the application, not DB-generated UUID types).

---

## Table-by-table: core pipeline tables

### `watch_dirs`

| Aspect | Definition |
|--------|------------|
| **PK** | `id` — `TEXT NOT NULL`, primary key. **App-supplied** (not autoincrement; not a DB `UUID` type). |
| **Important columns** | `name`, `created_at`, `updated_at` (`REAL`, Julian defaults in SQLite schema). |
| **FKs** | None (root of watch-dir subtree). |
| **Unique constraints** | None in schema dict. |
| **Indexes** | None declared in `schema_definition_indexes.py` for this table. |
| **Notes** | Path is **not** stored here; canonical path association is `watch_dir_paths.absolute_path` per watch dir row. |

### `watch_dir_paths`

| Aspect | Definition |
|--------|------------|
| **PK** | `watch_dir_id` — `TEXT NOT NULL`, sole primary key column → **one row per `watch_dirs` row** (1:1 by id). |
| **Important columns** | `absolute_path` — `TEXT`, **nullable** in column definition (semantics: resolved absolute path for that watch dir when set). |
| **FKs** | `watch_dir_id` → `watch_dirs.id`, **ON DELETE CASCADE**. |
| **Unique constraints** | None beyond PK. |
| **Indexes** | None in `schema_definition_indexes.py`. |
| **Notes** | PK doubles as FK to `watch_dirs`; there is no separate surrogate key. |

### `projects`

| Aspect | Definition |
|--------|------------|
| **PK** | `id` — `TEXT NOT NULL`, primary key. **App-supplied** UUID-like string. |
| **Important columns** | `root_path` (TEXT NOT NULL), `name`, `comment`, `watch_dir_id` (nullable TEXT), `deleted` (BOOLEAN, default 0), `processing_paused` (BOOLEAN, default 0), timestamps. |
| **FKs** | `watch_dir_id` → `watch_dirs.id`, **ON DELETE SET NULL**. |
| **Unique constraints** | **`UNIQUE(root_path)`** — global uniqueness of project root path. |
| **Indexes** | `idx_projects_root_path` on `(root_path)` — **non-unique** in index list (uniqueness enforced via table UNIQUE constraint, not redundant unique index name). |
| **Notes** | `deleted` / `processing_paused` are soft-state flags; not part of PK/UNIQUE. |

### `files`

| Aspect | Definition |
|--------|------------|
| **PK** | `id` — `INTEGER NOT NULL`, autoincrement, primary key. |
| **Important columns** | `project_id` (TEXT NOT NULL), `watch_dir_id` (nullable), `path` (absolute, TEXT NOT NULL), `relative_path`, `lines`, `last_modified`, `has_docstring`, `deleted`, `original_path`, `version_dir`, `needs_chunking`, timestamps. |
| **FKs** | `project_id` → `projects.id` **CASCADE**; `watch_dir_id` → `watch_dirs.id` **SET NULL**. |
| **Unique constraints** | **`UNIQUE(project_id, path)`** — uniqueness of absolute path **within** a project. |
| **Indexes** | `idx_files_project` (`project_id`); `idx_files_path` (`path`); `idx_files_deleted` (`deleted`) WHERE `deleted = 1`; `idx_files_deleted_project_id` (`deleted`, `project_id`); `idx_files_updated_at` (`updated_at`); `idx_files_needs_indexing` (`project_id`, `updated_at`) WHERE active file and `needs_chunking = 1`. |
| **Path semantics** | **`path`**: absolute filesystem path string. **`relative_path`**: path relative to project root (nullable in schema); **not** globally unique — same relative path in different projects is valid. |
| **Notes** | Cross-project duplicate **absolute** `path` is not prevented by DB (only per-project uniqueness); application conflict logic must handle that (per Step 05 narrative). |

### `code_chunks`

| Aspect | Definition |
|--------|------------|
| **PK** | `id` — `INTEGER NOT NULL`, autoincrement, primary key (row id). |
| **Business identifier** | **`chunk_uuid`** — `TEXT NOT NULL`, **`UNIQUE(chunk_uuid)`**. Stable identity for chunk dedup/search; generation today includes integer `file_id` in the UUID5 name input (see Step 12 / docstring chunker). |
| **Important columns** | `file_id`, `project_id` (both NOT NULL), `chunk_type`, `chunk_text`, `chunk_ordinal`, `vector_id`, `embedding_model`, scores, optional `class_id` / `function_id` / `method_id`, `line`, `ast_node_type`, `source_type`, `binding_level`, `vectorization_skipped`, timestamps. |
| **FKs** | `file_id` → `files.id` **CASCADE**; `project_id` → `projects.id` **CASCADE**; `class_id` / `function_id` / `method_id` → respective entity tables **CASCADE**. |
| **Unique constraints** | `UNIQUE(chunk_uuid)` only (no composite unique on `(file_id, …)` in schema dict). |
| **Indexes** | `idx_code_chunks_file` (`file_id`); `idx_code_chunks_project` (`project_id`); `idx_code_chunks_uuid` (`chunk_uuid`); `idx_code_chunks_vector` (`vector_id`); `idx_code_chunks_not_vectorized` (`project_id`, `id`) WHERE `vector_id IS NULL`; `idx_code_chunks_created_at` (`created_at`); `idx_code_chunks_project_embedding_model` (`project_id`) WHERE `embedding_model IS NOT NULL`. |
| **Denormalized fields** | **`project_id`** is denormalized from the owning file’s project for query convenience; **no CHECK constraint** enforcing `code_chunks.project_id = files.project_id`. |
| **Notes** | FKs ensure `file_id` and `project_id` each reference **some** valid row, but **not** that they refer to the **same** project as the parent file. |

---

## AST / CST / entity tables — `file_id` and `project_id`

Legend: PK / FK / UQ / IDX = primary key, foreign key, unique constraint (from table dict), index name from `schema_definition_indexes.py`.

### Tables with direct `file_id` → `files.id`

| Table | PK | FK `file_id` | FK `project_id` | Unique (involves `file_id` or file-scoped) | Indexes (file-related) |
|-------|----|--------------|-----------------|---------------------------------------------|-------------------------|
| **classes** | INTEGER AI | CASCADE | — | **UQ (`file_id`, `name`, `line`)** | `idx_classes_file`, `idx_classes_name` |
| **functions** | INTEGER AI | CASCADE | — | **UQ (`file_id`, `name`, `line`)** | `idx_functions_file`, `idx_functions_name` |
| **imports** | INTEGER AI | CASCADE | — | — | `idx_imports_file`, `idx_imports_name` |
| **usages** | INTEGER AI | CASCADE | — | — | `idx_usages_file`, … |
| **code_content** | INTEGER AI | CASCADE | — | — | `idx_code_content_file`, `idx_code_content_entity` |
| **ast_trees** | INTEGER AI | CASCADE | **CASCADE** | **UQ (`file_id`, `ast_hash`)** | `idx_ast_trees_file`, `idx_ast_trees_project`, `idx_ast_trees_hash` |
| **cst_trees** | INTEGER AI | CASCADE | **CASCADE** | **UQ (`file_id`, `cst_hash`)** | `idx_cst_trees_file`, `idx_cst_trees_project` |
| **issues** | INTEGER AI | CASCADE (nullable col) | **CASCADE** (nullable col) | — | `idx_issues_file`, `idx_issues_project`, … |
| **entity_cross_ref** | INTEGER AI | **SET NULL** (nullable) | — | — | `idx_entity_cross_ref_file` |
| **duplicate_occurrences** | INTEGER AI | CASCADE | — | — | `idx_duplicate_occurrences_file` |
| **comprehensive_analysis_results** | INTEGER AI | CASCADE | **CASCADE** | **UQ (`file_id`, `file_mtime`)** | `idx_comprehensive_analysis_results_file`, `…_project` |
| **file_tree_snapshots** | INTEGER AI | CASCADE | **CASCADE** | **UQ (`file_id`)** — one snapshot row per file | `idx_file_tree_snapshots_file_id`, `…_project_id` |
| **code_chunks** | INTEGER AI | CASCADE | **CASCADE** | **UQ (`chunk_uuid`)** only | see § `code_chunks` |

**methods**: no `file_id`; links via **`class_id`** → `classes` (CASCADE). **UQ (`class_id`, `name`, `line`)**. Indexes `idx_methods_class`, `idx_methods_name`.

### Tables with `project_id` → `projects.id` (no `file_id`)

| Table | PK | FK `project_id` | Unique | Indexes |
|-------|----|-----------------|--------|---------|
| **vector_index** | INTEGER AI | CASCADE | **UQ (`project_id`, `entity_type`, `entity_id`)** | `idx_vector_index_project`, `idx_vector_index_entity`, `idx_vector_index_vector_id` |
| **code_duplicates** | INTEGER AI | CASCADE | **UQ (`project_id`, `duplicate_hash`)** | `idx_code_duplicates_project`, `idx_code_duplicates_hash` |
| **indexing_errors** | INTEGER AI | CASCADE | **UQ (`project_id`, `file_path`)** | `idx_indexing_errors_project` |

### `duplicate_occurrences`

- **PK**: INTEGER AI  
- **FKs**: `duplicate_id` → `code_duplicates`; `file_id` → `files` CASCADE  
- **Unique**: none  
- **Indexes**: `idx_duplicate_occurrences_duplicate`, `idx_duplicate_occurrences_file`

### `project_activity_locks`

- **PK**: `project_id` (TEXT) — **no FK** to `projects` in schema dict (application must keep consistent).  
- **Indexes**: `idx_project_activity_locks_lease_until` (`lease_until`)

### AST/CST ownership note

`ast_trees` and `cst_trees` both store **`file_id` and `project_id`**. Like `code_chunks`, the database does **not** enforce `project_id` = `files.project_id` for the same `file_id` via CHECK; diagnostics below apply analogously.

---

## Required invariant diagnostics (Step 05)

### 1. Chunks with mismatched project ownership

```sql
SELECT cc.id, cc.file_id, cc.project_id AS chunk_project_id, f.project_id AS file_project_id
FROM code_chunks cc
JOIN files f ON f.id = cc.file_id
WHERE cc.project_id != f.project_id;
```

**Expected:** zero rows in a healthy corpus.

### 2. Active same absolute path in multiple projects

```sql
SELECT path, COUNT(DISTINCT project_id) AS projects_count
FROM files
WHERE deleted IS NOT TRUE OR deleted IS NULL
GROUP BY path
HAVING COUNT(DISTINCT project_id) > 1;
```

**Interpretation:** rare; indicates relocation, symlink, or cross-project path collision — diagnostic, not automatic failure.

### 3. Same relative path in multiple projects (diagnostic only)

```sql
SELECT relative_path, COUNT(DISTINCT project_id) AS projects_count
FROM files
WHERE deleted IS NOT TRUE OR deleted IS NULL
GROUP BY relative_path
HAVING COUNT(DISTINCT project_id) > 1;
```

**Expected / policy:** **allowed** — do not treat as error (Step 05).

---

## Additional diagnostic SQL (recommended)

### 4. AST rows: `project_id` vs file’s project

```sql
SELECT a.id, a.file_id, a.project_id AS ast_project_id, f.project_id AS file_project_id
FROM ast_trees a
JOIN files f ON f.id = a.file_id
WHERE a.project_id != f.project_id;
```

### 5. CST rows: `project_id` vs file’s project

```sql
SELECT c.id, c.file_id, c.project_id AS cst_project_id, f.project_id AS file_project_id
FROM cst_trees c
JOIN files f ON f.id = c.file_id
WHERE c.project_id != f.project_id;
```

### 6. Issues: when both `file_id` and `project_id` set, compare to file

```sql
SELECT i.id, i.file_id, i.project_id AS issue_project_id, f.project_id AS file_project_id
FROM issues i
JOIN files f ON f.id = i.file_id
WHERE i.project_id IS NOT NULL
  AND i.project_id != f.project_id;
```

### 7. Comprehensive analysis: `project_id` vs file

```sql
SELECT r.id, r.file_id, r.project_id AS result_project_id, f.project_id AS file_project_id
FROM comprehensive_analysis_results r
JOIN files f ON f.id = r.file_id
WHERE r.project_id != f.project_id;
```

### 8. File tree snapshots: `project_id` vs file

```sql
SELECT s.id, s.file_id, s.project_id AS snapshot_project_id, f.project_id AS file_project_id
FROM file_tree_snapshots s
JOIN files f ON f.id = s.file_id
WHERE s.project_id != f.project_id;
```

### 9. Locks without matching project row (orphan locks)

```sql
SELECT pal.project_id
FROM project_activity_locks pal
LEFT JOIN projects p ON p.id = pal.project_id
WHERE p.id IS NULL;
```

*(Valid only on engines where schema is applied consistently; highlights missing FK on `project_activity_locks`.)*

---

## Known gaps vs target model

| Gap | Detail |
|-----|--------|
| **Integer vs TEXT identity split** | `projects` / `watch_dirs` use TEXT UUID-like ids; `files`, `code_chunks`, AST/CST/entity rows use INTEGER PKs/FKs — two identity styles in one graph. |
| **No DB enforcement chunk/project = file/project** | `code_chunks.project_id` (and same pattern on `ast_trees`, `cst_trees`, etc.) is not tied by CHECK to `files.project_id`. |
| **`project_activity_locks.project_id`** | PK column has **no FK** to `projects` — possible orphan or stale lock rows if application slips. |
| **`issues` nullable `file_id` / `project_id`** | Flexible for project-level issues, but allows combinations that need app-level validation. |
| **`entity_cross_ref.file_id`** | Nullable; **ON DELETE SET NULL** — cross-ref can lose file anchor while keeping caller/callee ids. |
| **`vector_index.entity_id`** | INTEGER; maps to chunk or other entity types in app logic — Step 12 calls out FAISS / vector mappings storing integer DB ids. |
| **Cross-project absolute `path`** | Not ruled out by `UNIQUE(project_id, path)` alone. |
| **Command / API surface** | Some flows may still resolve by path without `file_id`; see plan Step 02 — not a DDL gap but an operational identity gap. |
| **Postgres migration** | `sqlite_to_postgres` dedupes `code_chunks` by `chunk_uuid` — legacy rows with null/empty `chunk_uuid` need special handling; unrelated to PK type but affects identity continuity during migrate. |

---

## UUID migration risks (Steps 05 + 12)

Risks below assume moving toward **business UUID columns** while keeping integer PKs first (recommended in Step 12).

| Risk area | Why it matters |
|-----------|----------------|
| **`chunk_uuid` formula** | Today derived from a string that includes **integer `file_id`**. Changing `files` PK or switching the name input to `file_uuid` without a **versioned** scheme changes future UUIDs and breaks dedup continuity with existing rows. |
| **Wide FK fan-in from `files.id`** | Every table in § “Tables with direct `file_id`” plus indirect chains (`methods` → `classes` → `files`) must be migrated or dual-read if internal PK ever changes. |
| **MCP / clients** | Integer `file_id`, `chunk_id` / row ids exposed in commands; breaking change if removed before dual exposure (`id` + `file_uuid`). |
| **`vector_index`** | **UQ (`project_id`, `entity_type`, `entity_id`)** — `entity_id` is integer; vectors keyed in external stores likely use these integers. |
| **`ast_trees` / `cst_trees` UQ** | `(file_id, ast_hash)` / `(file_id, cst_hash)` — hash stability vs file identity if `file_id` changes. |
| **Backfill** | New `file_uuid` must be **unique**, **NOT NULL** after backfill; partial migration leaves mixed clients. |
| **Regenerate `chunk_uuid`** | Forbidden without an explicit migration and re-embedding plan (Step 12). |
| **`project_activity_locks`** | TEXT `project_id` already; adding `projects` FK later would change deletion semantics — design separately. |
| **SQLite vs Postgres** | DDL generated from same source; risk is **application** and **data** migration, not divergent UNIQUE definitions. |

---

## Migration recommendation (Steps 05 + 12)

1. **Do not** replace integer PK/FK internals in the first migration wave.  
2. Prefer **adding** nullable-then-NOT NULL business columns, e.g. `files.file_uuid TEXT UNIQUE`, backfilled with UUID4, exposed **alongside** integer ids in MCP.  
3. Accept UUID in **new** command parameters only after backward-compatible resolution exists.  
4. Decide explicitly on **`chunk_uuid` versioning** (keep integer-based name forever vs versioned `file_uuid`-based scheme vs separate business UUID) before any formula change.  
5. Defer replacing internal FK columns to a **later major** migration if ever.

---

## References

- `docs/plans/2026-04-27-identity-db-pipeline-refactor/05-code_analysis_core_database_schema_identity.md`
- `docs/plans/2026-04-27-identity-db-pipeline-refactor/12-uuid_business_identity_transition.md`
- `docs/plans/2026-04-27-identity-db-pipeline-refactor/14-code_analysis_commands_worker_status_mcp_commands_get_database_status_build.md` (status predicates / counters)
