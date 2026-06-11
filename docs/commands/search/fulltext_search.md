# fulltext_search

**Command name:** `fulltext_search`  
**Class:** `FulltextSearchMCPCommand`  
**Source:** `code_analysis/commands/search_mcp_commands.py`  
**Category:** search

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The fulltext_search command performs full-text search over indexed code content using SQLite FTS5 (Full-Text Search 5). It searches through code content, docstrings, and entity names to find matches for the query text.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Performs FTS5 search in code_content_fts table (BM25 ranking)
5. Filters by entity_type if provided (class, method, function)
6. Limits results to specified limit
7. Returns matching chunks with file paths and metadata

Search Capabilities:
- Searches in code content (chunk_text)
- Searches in docstrings
- Searches in entity names
- Supports partial word matching
- Case-insensitive search
- Can filter by entity type

Use cases:
- Find code containing specific text
- Search for function/class names
- Find code with specific patterns
- Search in docstrings

Important notes:
- Requires built database (run update_indexes first)
- Uses SQLite FTS5 for fast text search
- Results are ranked by relevance
- Default limit is 20 results
- Entity type filter: 'class', 'method', or 'function'

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `query` | string | **Yes** | Search query text |
| `entity_type` | string | No | Filter by entity type (class, method, function) |
| `limit` | integer | No | Maximum number of results Default: `20`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `query`: Search query that was used
- `results`: List of matching chunks. Each contains:
- chunk_uuid: Chunk UUID
- chunk_type: Type of chunk (class, method, function, etc.)
- chunk_text: Text content of chunk
- file_path: Path to file containing the chunk
- line: Line number in file
- rank: Relevance rank (lower is better)
- `count`: Number of results found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, SEARCH_ERROR (and others).

---

## Examples

### Correct usage

**Search for text in code**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "query": "structure analysis",
  "limit": 10
}
```

Searches for 'structure analysis' in all code content and docstrings, returning up to 10 results.

**Search for classes**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "query": "MyClass",
  "entity_type": "class"
}
```

Searches for classes containing 'MyClass' in their name or content.

**Search for function definitions**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "query": "def solve",
  "entity_type": "function"
}
```

Searches for functions containing 'solve' in their name or content.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **SEARCH_ERROR**: Database error, FTS5 not available, or query parsing error. Check database integrity, ensure FTS5 is enabled, verify database was built with update_indexes.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `SEARCH_ERROR` | General error during search | Check database integrity, ensure FTS5 is enabled,  |

## Best practices

- Run update_indexes first to build the search index
- Use entity_type filter to narrow down results
- Adjust limit based on expected result count
- Query text supports partial word matching
- Results are ranked by relevance

---
