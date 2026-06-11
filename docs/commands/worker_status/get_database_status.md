# get_database_status

**Command name:** `get_database_status`  
**Class:** `GetDatabaseStatusMCPCommand`  
**Source:** `code_analysis/commands/worker_status_mcp_commands.py`  
**Category:** worker_status

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_database_status command provides comprehensive monitoring of the SQLite database state, statistics, and pending work. It reports file statistics, chunk statistics, project information, and recent activity to help monitor database health and identify work that needs to be done.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves database path: root_dir/data/code_analysis.db
3. Checks if database file exists
4. Gets file size if database exists
5. Opens database connection
6. Queries project statistics
7. Queries file statistics (total, deleted, indexed, needing indexing, needing chunking)
8. Queries chunk statistics (total, vectorized, not vectorized)
9. Queries recent activity (last 24 hours)
10. Gets samples of files needing indexing and needing chunking
11. Gets samples of chunks needing vectorization
12. Returns comprehensive status report

File Statistics:
- total: Total number of files in database
- deleted: Number of deleted files
- active: Number of active (non-deleted) files
- with_docstring: Files that have docstrings
- indexed: Files indexed by indexing worker (needs_chunking=0)
- indexed_percent: Percentage of active files indexed
- needing_indexing: Active files with needs_chunking=1 (pending indexer)
- needing_indexing_sample: Sample of files needing indexing (up to 10)
- needing_chunking: Active files without chunks
- needing_chunking_sample: Sample of files needing chunking (up to 10)

Chunk Statistics:
- total: Total number of code chunks
- vectorized: Chunks with embedding vectors
- not_vectorized: Chunks without embedding vectors
- vectorization_percent: Percentage of chunks that are vectorized
- needing_vectorization_sample: Sample of chunks needing vectorization (up to 10)

Project Statistics:
- total: Total number of projects
- sample: Sample of projects (up to 10) with id and name

Recent Activity:
- files_updated_24h: Files updated in last 24 hours
- chunks_updated_24h: Chunks created in last 24 hours

Use cases:
- Monitor database health and size
- Check pending work (files needing chunking, chunks needing vectorization)
- Track project and file statistics
- Monitor recent activity
- Identify files that need processing
- Verify vectorization progress
- Database capacity planning

Important notes:
- Database must exist (returns error if not found)
- Statistics are calculated from database queries
- Samples are limited to 10 items each
- Recent activity uses SQLite julianday() for time calculations
- File size is reported in megabytes
- All statistics are read-only (no database modifications)

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `db_path`: Path to database file
- `timestamp`: ISO timestamp of status check
- `exists`: True if database file exists
- `file_size_mb`: Database file size in megabytes
- `projects`: (see example)
- `files`: (see example)
- `chunks`: (see example)
- `recent_activity`: (see example)
- `error`: Error message if status check failed (optional)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** DATABASE_STATUS_ERROR (and others).

---

## Examples

### Correct usage

**Check database status**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns comprehensive database statistics including files, chunks, projects, and recent activity.

**Monitor database health**
```json
{
  "root_dir": "."
}
```

Checks database status in current directory to monitor health and pending work.

### Incorrect usage

- **DATABASE_STATUS_ERROR**: Error during database status check. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `DATABASE_STATUS_ERROR` | Error during database status check |  |

## Best practices

- Check exists field first to verify database exists
- Monitor file_size_mb to track database growth
- Check files.indexed and files.indexed_percent to track indexing progress
- Check files.needing_indexing and needing_indexing_sample for indexer backlog
- Check files.needing_chunking to identify chunking backlog
- Check chunks.not_vectorized to see vectorization backlog
- Use indexed_percent and vectorization_percent to track progress
- Review needing_indexing_sample and needing_vectorization_sample for specific items

---
