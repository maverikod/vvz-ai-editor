# ast_statistics

**Command name:** `ast_statistics`  
**Class:** `ASTStatisticsMCPCommand`  
**Source:** `code_analysis/commands/ast/statistics.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The ast_statistics command collects and returns AST (Abstract Syntax Tree) statistics for a project or a specific file. It provides counts of AST trees stored in the analysis database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection at root_dir/data/code_analysis.db
3. Resolves project_id (from parameter or inferred from root_dir)
4. If file_path provided:
   - Finds file record in database
   - Counts AST trees for that specific file
   - Returns file-specific statistics
5. If file_path not provided:
   - Counts all AST trees for the project
   - Counts all files in the project
   - Returns project-wide statistics

Use cases:
- Check if AST data exists for a file before analysis
- Get overview of project AST coverage
- Verify AST indexing status
- Monitor AST database size

Important notes:
- Returns count of stored AST trees, not parsed files
- File count excludes deleted files
- AST trees are created during file analysis/indexing
- If file has no AST data, count will be 0

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | No | Optional file path to compute stats for (relative to project root) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `file_path (if provided)`: File path that statistics were computed for
- `project_id (if file_path not provided)`: Project UUID
- `files_count (if file_path not provided)`: Total number of files in project
- `ast_trees_count`: Number of AST trees stored in database
- `success`: Always true on success

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, AST_STATS_ERROR (and others).

---

## Examples

### Correct usage

**Get project-wide AST statistics**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns total count of files and AST trees for the entire project. Useful for checking overall AST coverage.

**Get AST statistics for specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Returns AST tree count for the specific file. Useful for verifying if a file has been analyzed.

**Get statistics with explicit project_id**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7"
}
```

Explicitly specifies project_id. Useful when root_dir might match multiple projects or for programmatic access.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered in database. Ensure project is registered. Run update_indexes command first to create project entry and analyze files.

- **FILE_NOT_FOUND**: file_path='src/main.py' but file not in database. Ensure file exists and has been indexed. Check file path is correct (absolute or relative to root_dir). Run update_indexes to index files.

- **AST_STATS_ERROR**: Database error, permission denied, or corrupted database. Check database integrity, verify file permissions, ensure database is not locked, or run repair_sqlite_database if corrupted

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes c |
| `FILE_NOT_FOUND` | File not found in database | Ensure file exists and has been indexed. Check fil |
| `AST_STATS_ERROR` | General error during statistics collection | Check database integrity, verify file permissions, |

## Best practices

- Use project-wide statistics to check overall AST coverage before detailed analysis
- Check file-specific statistics before running AST-dependent commands
- Run update_indexes if AST statistics show 0 counts for expected files
- Use explicit project_id when working with multiple projects
- Monitor AST tree count vs file count to detect indexing issues

---
