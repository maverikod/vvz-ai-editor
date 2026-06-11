# check_vectors

**Command name:** `check_vectors`  
**Class:** `CheckVectorsCommand`  
**Source:** `code_analysis/commands/check_vectors_command.py`  
**Category:** misc

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The `check_vectors` command provides a comprehensive overview of the vectorization status of code chunks stored in the database. It reports on the total number of chunks, how many have been vectorized (i.e., have a `vector_id` in the FAISS index), how many have an `embedding_model` specified, and how many are still pending vectorization. It also calculates the overall vectorization percentage and provides a sample of vectorized chunks with detailed information such as their FAISS ID, the embedding model used, chunk type, source type, and a text preview. This command is crucial for monitoring the progress and health of the vectorization pipeline, diagnosing issues, and verifying the integrity of the FAISS index.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** MISSING_PARAMETER, PROJECT_NOT_FOUND, CHECK_VECTORS_ERROR (and others).

---

## Examples

### Correct usage

**Get vectorization status for entire database using project path**
```json
"check_vectors --root-dir /path/to/your/project"
```

**Get vectorization status using project UUID**
```json
"check_vectors --root-dir 550e8400-e29b-41d4-a716-446655440000"
```

**Get vectorization status for a specific project with explicit project_id filter**
```json
"check_vectors --root-dir /path/to/project --project-id 550e8400-e29b-41d4-a716-446655440000"
```

### Incorrect usage

- **MISSING_PARAMETER**: Occurs when `root_dir` parameter is not provided or is empty.. Ensure `root_dir` is provided with either a valid file system path or a UUID4 project identifier.

- **PROJECT_NOT_FOUND**: Occurs in two scenarios: 1) When `root_dir` is a UUID4 but no matching project is found in the database. 2) When `project_id` parameter is provided but no matching project is found.. Verify that the project UUID exists in the database using `list_projects` command. Ensure the project has been indexed using `update_indexes` command.

- **CHECK_VECTORS_ERROR**: A general error indicating a failure during command execution. Common causes include: database access issues, corrupted database, missing database file, or unexpected data format.. Check the error details in the response. Verify database integrity using `get_database_status`. Ensure the database file exists and is accessible. Check server logs for detailed error information.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `MISSING_PARAMETER` | Occurs when `root_dir` parameter is not provided or is empty | Ensure `root_dir` is provided with either a valid  |
| `PROJECT_NOT_FOUND` | Occurs in two scenarios: 1) When `root_dir` is a UUID4 but n | Verify that the project UUID exists in the databas |
| `CHECK_VECTORS_ERROR` | A general error indicating a failure during command executio | Check the error details in the response. Verify da |

## Best practices

- Always specify `root_dir` to ensure the correct database is accessed.
- Use UUID4 format for `root_dir` when you know the project ID but not the exact path.
- Use `project_id` parameter to filter results when you want statistics for a different project than the one in `root_dir`.
- Monitor `chunks_pending_vectorization` to identify backlogs in the vectorization pipeline.
- Check `embedding_model` in `sample_chunks` to verify that the expected models are being used.
- Use this command regularly to monitor vectorization progress, especially after large code changes.
- If `vectorization_percentage` is low, check the vectorization worker status using `get_worker_status`.

---
