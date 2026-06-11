# rebuild_faiss

**Command name:** `rebuild_faiss`  
**Class:** `RebuildFaissCommand`  
**Source:** `code_analysis/commands/vector_commands/rebuild_faiss.py`  
**Category:** vector

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The rebuild_faiss command rebuilds FAISS (Facebook AI Similarity Search) index from database embeddings. One index per project: {faiss_dir}/{project_id}.bin.

Operation flow:
1. Validates root_dir exists and is a directory
2. Validates project_id matches root_dir/projectid file
3. Opens database connection
4. Verifies project exists in database
5. Loads config.json to get storage paths and vector dimension
6. Initializes SVOClientManager for embeddings
7. Gets project-scoped FAISS index path
8. Rebuilds FAISS index from database embeddings (all chunks in project)
9. Returns rebuild statistics

FAISS Index:
- One index per project: {faiss_dir}/{project_id}.bin
- Reads embeddings from code_chunks.embedding_vector in database
- Normalizes vector_id to dense range 0..N-1
- Requires valid embeddings in database (use revectorize if missing)
- project_id must match root_dir/projectid file

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `project_id`: Project UUID
- `index_path`: Path to FAISS index file ({faiss_dir}/{project_id}.bin)
- `vectors_count`: Number of vectors in index

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, REBUILD_FAISS_ERROR (and others).

---

## Examples

### Correct usage

**Rebuild FAISS index for project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

Rebuilds the single FAISS index for the project.

### Incorrect usage

- **PROJECT_NOT_FOUND**: Project not found in database. Verify project_id is correct. Ensure project is registered in database. Run update_indexes to register project if needed.

- **CONFIG_NOT_FOUND**: Configuration file not found. Ensure config.json exists in root_dir. Config file is required for storage paths and vector dimension.

- **REBUILD_FAISS_ERROR**: Error during FAISS index rebuild. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct. Ensure project is re |
| `CONFIG_NOT_FOUND` | Configuration file not found | Ensure config.json exists in root_dir. Config file |
| `REBUILD_FAISS_ERROR` | Error during FAISS index rebuild |  |

## Best practices

- Run revectorize first if embeddings are missing
- Rebuild index after bulk embedding updates
- Verify vectors_count matches expected number of chunks
- Check index_path to verify index file location
- Ensure vector_dim in config matches embedding dimension

---
