# collapse_versions

**Command name:** `collapse_versions`  
**Class:** `CollapseVersionsMCPCommand`  
**Source:** `code_analysis/commands/file_management_mcp_commands.py`  
**Category:** file_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The collapse_versions command collapses file versions, keeping only the latest version by last_modified timestamp. It finds all database records with the same path but different last_modified timestamps and keeps only the latest one, deleting others with hard delete.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Finds all files with multiple versions (same path, different last_modified)
5. For each file with multiple versions:
   - Gets all versions sorted by last_modified (descending)
   - If keep_latest=True: Keeps first version (latest), deletes others
   - If keep_latest=False: Keeps last version (oldest), deletes others
6. If dry_run=True:
   - Lists files that would be collapsed
   - Shows which versions would be kept/deleted
7. If dry_run=False:
   - Performs hard delete on old versions
   - Removes all data for deleted versions
8. Returns collapse statistics

Version Collapsing:
- Finds files with same path but different last_modified
- Keeps latest version (by default) or oldest version
- Hard deletes old versions (permanent removal)
- Removes all data: file record, chunks, AST, vectors, entities

Use cases:
- Clean up duplicate file versions in database
- Remove old versions after file updates
- Reduce database size by removing redundant versions
- Fix database inconsistencies with multiple versions

Important notes:
- Hard delete is PERMANENT and cannot be recovered
- Always use dry_run=True first to preview changes
- Default behavior keeps latest version (keep_latest=True)
- Only collapses files with same path but different last_modified

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `keep_latest` | boolean | No | If True, keep latest version (default: True) Default: `true`. |
| `dry_run` | boolean | No | If True, only show what would be collapsed Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `kept_count`: Number of versions kept
- `deleted_count`: Number of versions deleted
- `collapsed_files`: List of files that were collapsed. Each entry contains:
- path: File path
- version_count: Number of versions found
- keep: Version that was kept (id, last_modified)
- delete: List of versions that were deleted (id, last_modified)
- `dry_run`: Whether this was a dry run
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, COLLAPSE_ERROR (and others).

---

## Examples

### Correct usage

**Preview version collapse (dry run)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "dry_run": true
}
```

Lists all files with multiple versions that would be collapsed, showing which versions would be kept and deleted.

**Collapse versions, keep latest**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "keep_latest": true
}
```

Collapses file versions, keeping only the latest version by last_modified. Permanently deletes old versions.

**Collapse versions, keep oldest**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "keep_latest": false
}
```

Collapses file versions, keeping only the oldest version. Permanently deletes newer versions.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **COLLAPSE_ERROR**: Database error, version retrieval error, or deletion failure. Check database integrity, verify file versions exist, ensure database is not locked. Use dry_run=True first.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `COLLAPSE_ERROR` | General error during version collapse | Check database integrity, verify file versions exi |

## Best practices

- Always use dry_run=True first to preview what would be collapsed
- Default keep_latest=True keeps the most recent version
- Use this command to clean up duplicate file versions
- Hard delete is permanent - backup database before running
- Run this command periodically to maintain database cleanliness

---
