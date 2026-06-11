# revectorize

**Command name:** `revectorize`  
**Class:** `RevectorizeCommand`  
**Source:** `code_analysis/commands/vector_commands/revectorize.py`  
**Category:** vector

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The revectorize command regenerates embeddings for code chunks and updates the FAISS index. One index per project.

Operation flow:
1. Validates root_dir exists and is a directory
2. Validates project_id matches root_dir/projectid file
3. Opens database connection
4. Verifies project exists in database
5. Loads config.json to get storage paths and vector dimension
6. Initializes SVOClientManager for embedding generation
7. Gets chunks that need revectorization for the project
8. For each chunk: gets text, calls SVO for embedding, updates DB, sets vector_id to NULL
9. Rebuilds FAISS index from updated embeddings
10. Returns revectorization statistics

Revectorization Process:
- Finds chunks without embeddings or with force=True (all chunks)
- Generates new embeddings using SVO (Semantic Vector Operations) service
- Updates code_chunks.embedding_vector in database
- Updates code_chunks.embedding_model with model name
- Sets vector_id to NULL (normalized during FAISS rebuild)
- Rebuilds FAISS index after revectorization

Force Mode:
- If force=False: Only revectorizes chunks without embeddings
- If force=True: Revectorizes all chunks (regenerates all embeddings)
- Use force=True to update embeddings after model changes
- Use force=False to only process missing embeddings

Embedding Generation:
- Uses SVOClientManager to call embedding service
- Embeddings are generated asynchronously
- Vector dimension comes from config.json (default: 384)
- Embeddings are stored as JSON arrays in database
- Model name is stored for tracking embedding source

FAISS Index Update:
- After revectorization, FAISS index is rebuilt
- Rebuild normalizes vector_id to dense range
- Index includes all chunks with valid embeddings (one index per project)

Use cases:
- Generate embeddings for chunks without vectors
- Regenerate embeddings after model changes
- Update embeddings for improved quality
- Initialize embeddings for new chunks
- Fix corrupted or invalid embeddings
- Revectorize after embedding service updates

Important notes:
- Requires SVO service to be configured and accessible
- Embedding generation can be slow for many chunks
- FAISS index is automatically rebuilt after revectorization
- force=True regenerates all embeddings (can be time-consuming)
- Chunks with empty text are skipped
- Failed chunks are logged but don't stop the process
- project_id must match root_dir/projectid file

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `force` | boolean | No | Force revectorization even if embeddings exist (default: false) Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `project_id`: Project UUID
- `chunks_revectorized`: Number of chunks revectorized
- `vectors_in_index`: Number of vectors in rebuilt FAISS index
- `index_path`: Path to FAISS index file ({faiss_dir}/{project_id}.bin)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, REVECTORIZE_ERROR (and others).

---

## Examples

### Correct usage

**Revectorize missing embeddings for project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "force": false
}
```

Revectorizes only chunks without embeddings. FAISS index is automatically rebuilt after completion.

**Force revectorize all chunks**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "force": true
}
```

Regenerates all embeddings. Useful after embedding model changes.

### Incorrect usage

- **PROJECT_NOT_FOUND**: Project not found in database. Verify project_id is correct. Ensure project is registered in database. Run update_indexes to register project if needed.

- **CONFIG_NOT_FOUND**: Configuration file not found. Ensure config.json exists in root_dir. Config file is required for SVO service configuration.

- **REVECTORIZE_ERROR**: Error during revectorization. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Verify project_id is correct. Ensure project is re |
| `CONFIG_NOT_FOUND` | Configuration file not found | Ensure config.json exists in root_dir. Config file |
| `REVECTORIZE_ERROR` | Error during revectorization |  |

## Best practices

- Use force=False to only process missing embeddings (faster)
- Use force=True after embedding model changes
- Run revectorize before rebuild_faiss if embeddings are missing
- Monitor chunks_revectorized to track progress
- Check vectors_in_index to verify FAISS index was rebuilt
- Ensure SVO service is configured and accessible
- Run rebuild_faiss after revectorize to ensure index is updated

---
