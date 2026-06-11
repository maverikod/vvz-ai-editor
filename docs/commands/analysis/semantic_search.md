# semantic_search

**Command name:** `semantic_search`  
**Class:** `SemanticSearchMCPCommand`  
**Source:** `code_analysis/commands/semantic_search_mcp.py`  
**Category:** analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The semantic_search command performs semantic search using embeddings and FAISS vector index. It converts the query text to an embedding vector using an embedding service, then searches for similar code chunks in the FAISS index.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Loads server config to get vector_dim and embedding service config
5. Resolves FAISS index path (one index per project: {faiss_dir}/{project_id}.bin)
6. Loads FAISS index using FaissIndexManager
7. Gets query embedding from embedding service (SVOClientManager)
8. Normalizes embedding vector
9. Searches FAISS index for limit nearest neighbors
10. Filters results by min_score (if provided)
11. Returns similar code chunks with similarity scores

Semantic Search:
- Uses embedding vectors to find semantically similar code
- Query is converted to embedding using embedding service
- Searches in FAISS index for similar vectors
- Returns chunks ranked by similarity (distance)
- Similarity score: 1.0 / (1.0 + distance)

FAISS Index:
- One index per project: {faiss_dir}/{project_id}.bin
- Must be built with update_indexes first
- Uses cosine similarity (normalized vectors)
- Returns up to limit nearest neighbors

Important notes:
- Requires embedding service to be available
- Requires FAISS index (run update_indexes first)
- Similarity scores range from 0.0 to 1.0 (higher is better)
- min_score filters results by similarity threshold

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `query` | string | **Yes** | Search query text |
| `limit` | integer | No | Maximum number of results to return (1-100). Same as fulltext_search/search_ast_nodes. |
| `min_score` | number | No | Minimum similarity score (0.0-1.0) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `query`: Search query that was used
- `limit`: Maximum number of results requested (same as request parameter)
- `min_score`: Minimum score threshold (if provided)
- `index_path`: Path to FAISS index file ({faiss_dir}/{project_id}.bin)
- `project_id`: Project UUID
- `results`: List of similar code chunks. Each contains:
- score: Similarity score (0.0-1.0, higher is better)
- distance: Distance in vector space (lower is better)
- vector_id: Vector ID in FAISS index
- chunk_uuid: Chunk UUID
- chunk_type: Type of chunk
- file_path: Path to file containing the chunk
- line: Line number in file
- text: Text content of chunk
- `count`: Number of results returned (after min_score filtering)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, FAISS_INDEX_NOT_FOUND, EMBEDDING_SERVICE_ERROR, SEARCH_ERROR (and others).

---

## Examples

### Correct usage

**Basic semantic search**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "query": "database connection",
  "limit": 10
}
```

Searches for code chunks semantically similar to 'database connection', returning top 10 results.

**Search with minimum score threshold**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "query": "error handling",
  "limit": 20,
  "min_score": 0.7
}
```

Searches for similar code with minimum similarity score of 0.7, returning up to 20 results.

**Find highly similar code**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "query": "file processing",
  "limit": 5,
  "min_score": 0.9
}
```

Finds highly similar code (score >= 0.9) related to 'file processing', returning top 5 results.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **CONFIG_NOT_FOUND**: Server config.json missing. Ensure server config has embedding service configuration (code_analysis.embedding).

- **FAISS_INDEX_NOT_FOUND**: Index file doesn't exist for project. Run update_indexes first to build the FAISS index. One index per project: {faiss_dir}/{project_id}.bin

- **EMBEDDING_SERVICE_ERROR**: Service unavailable, invalid response, or zero norm vector. Check embedding service configuration in server config. Ensure service is available and responding correctly.

- **SEARCH_ERROR**: Database error, FAISS error, or vector dimension mismatch. Check database integrity, verify FAISS index is valid, ensure vector_dim matches index configuration.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `CONFIG_NOT_FOUND` | Configuration file not found | Ensure server config has embedding service configu |
| `FAISS_INDEX_NOT_FOUND` | FAISS index not found | Run update_indexes first to build the FAISS index. |
| `EMBEDDING_SERVICE_ERROR` | Failed to get embedding from service | Check embedding service configuration in server co |
| `SEARCH_ERROR` | General error during search | Check database integrity, verify FAISS index is va |

## Best practices

- Run update_indexes first to build the FAISS index
- Ensure embedding service is configured and available
- Use min_score to filter low-quality results
- Adjust limit based on expected result count
- Similarity scores help identify most relevant matches
- Query text should describe the concept you're searching for

---
