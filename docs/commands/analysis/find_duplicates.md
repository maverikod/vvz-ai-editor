# find_duplicates

**Command name:** `find_duplicates`  
**Class:** `FindDuplicatesMCPCommand`  
**Source:** `code_analysis/commands/find_duplicates_mcp.py`  
**Category:** analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The find_duplicates command finds duplicate code blocks using AST normalization and optional semantic vector analysis. It identifies code that can be refactored to reduce duplication.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Initializes DuplicateDetector with specified parameters
5. If use_semantic=True:
   - Initializes SVO client manager for semantic search
   - Falls back to AST-only if semantic initialization fails
6. If file_path provided:
   - Analyzes specific file using AST parsing
   - Finds duplicates within the file
7. If file_path not provided:
   - Analyzes all files in project
   - Finds duplicates across all files
8. Filters results by min_similarity threshold
9. Sorts by similarity and number of occurrences
10. Returns duplicate groups with occurrences

Detection Methods:
- AST normalization: Normalizes AST structures to find structural duplicates
- Semantic vectors: Uses embeddings to find logical duplicates (if enabled)
- Hybrid mode: Combines both methods for comprehensive detection

Use cases:
- Find code duplication for refactoring opportunities
- Identify repeated patterns that can be extracted
- Detect copy-paste code blocks
- Find logical duplicates (semantically similar code)

Important notes:
- Skips files with syntax errors
- Results sorted by similarity (highest first) and occurrence count
- Semantic detection requires SVO service (falls back to AST if unavailable)
- Each duplicate group contains multiple occurrences

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | No | Optional path to specific file to analyze (relative to project root) |
| `min_lines` | integer | No | Minimum lines for duplicate block Default: `5`. |
| `min_similarity` | number | No | Minimum similarity threshold (0.0-1.0) Default: `0.8`. |
| `use_semantic` | boolean | No | Use semantic vectors for finding logical duplicates Default: `true`. |
| `semantic_threshold` | number | No | Minimum semantic similarity threshold (0.0-1.0) Default: `0.85`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `duplicate_groups`: List of duplicate groups. Each group contains:
- similarity: Similarity score (0.0-1.0)
- occurrences: List of occurrences, each with:
  - file_path: File where duplicate occurs
  - start_line: Starting line number
  - end_line: Ending line number
  - code: Code snippet (normalized)
- `total_groups`: Total number of duplicate groups found
- `total_occurrences`: Total number of duplicate occurrences across all groups
- `min_lines`: Minimum lines threshold used
- `min_similarity`: Minimum similarity threshold used

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FIND_DUPLICATES_ERROR (and others).

---

## Examples

### Correct usage

**Find duplicates in specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Finds duplicate code blocks within src/main.py file.

**Find duplicates across project with AST only**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "use_semantic": false
}
```

Finds structural duplicates using AST normalization only, without semantic analysis.

**Find significant duplicates (10+ lines, 90% similarity)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "min_lines": 10,
  "min_similarity": 0.9
}
```

Finds duplicates with at least 10 lines and 90% similarity. Focuses on significant duplication.

**Find logical duplicates with semantic search**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "use_semantic": true,
  "semantic_threshold": 0.9
}
```

Finds logical duplicates using semantic vectors with 90% similarity threshold.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FIND_DUPLICATES_ERROR**: Database error, AST parsing error, or semantic service unavailable. Check database integrity, verify file paths. If semantic search fails, command falls back to AST-only detection.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FIND_DUPLICATES_ERROR` | General error during duplicate detection | Check database integrity, verify file paths. If se |

## Best practices

- Use min_lines to filter out small duplicates
- Use min_similarity to focus on high-confidence duplicates
- Start with AST-only detection (use_semantic=False) for faster results
- Use semantic search for finding logical duplicates (similar functionality)
- Analyze specific files first before running project-wide detection
- Review duplicate groups sorted by similarity to prioritize refactoring
- Combine with comprehensive_analysis for complete code quality overview

---
