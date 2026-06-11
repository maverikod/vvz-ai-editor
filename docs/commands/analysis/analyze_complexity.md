# analyze_complexity

**Command name:** `analyze_complexity`  
**Class:** `AnalyzeComplexityMCPCommand`  
**Source:** `code_analysis/commands/analyze_complexity_mcp.py`  
**Category:** analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The analyze_complexity command analyzes cyclomatic complexity for functions and methods in a project. Cyclomatic complexity measures the number of linearly independent paths through code, helping identify functions that may need refactoring.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. If file_path provided:
   - Analyzes specific file using AST parsing
   - Calculates complexity for each function and method
   - Filters results by min_complexity threshold
5. If file_path not provided:
   - Retrieves all files from database
   - Analyzes each file (skips syntax errors)
   - Calculates complexity for all functions and methods
   - Filters results by min_complexity threshold
6. Sorts results by complexity (descending)
7. Returns list of functions/methods with complexity scores

Complexity Calculation:
- Uses AST analysis to count decision points (if, for, while, except, etc.)
- Complexity = 1 + number of decision points
- Higher complexity indicates more complex code paths
- Common thresholds: 1-10 (simple), 11-20 (moderate), 21+ (complex)

Use cases:
- Identify complex functions that need refactoring
- Find methods with high complexity scores
- Monitor code complexity over time
- Focus refactoring efforts on most complex code

Important notes:
- Skips files with syntax errors (continues with other files)
- Results sorted by complexity (highest first)
- min_complexity filter helps focus on problematic code
- Complexity is calculated for both functions and methods

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | No | Optional path to specific file to analyze (relative to project root) |
| `min_complexity` | integer | No | Optional minimum complexity threshold for filtering results Default: `1`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `results`: List of complexity results. Each entry contains:
- file_path: File where function/method is defined
- function_name: Name of function or method
- complexity: Cyclomatic complexity score (integer)
- line: Line number where function/method is defined
- type: 'function' or 'method'
- class_name: Class name (for methods only)
- `total_count`: Total number of results found
- `min_complexity`: Minimum complexity threshold used

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, ANALYZE_COMPLEXITY_ERROR (and others).

---

## Examples

### Correct usage

**Analyze complexity for specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Analyzes cyclomatic complexity for all functions and methods in src/main.py.

**Find complex functions (complexity >= 10)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "min_complexity": 10
}
```

Finds all functions and methods with complexity >= 10 across the project. Useful for identifying code that needs refactoring.

**Find very complex code (complexity >= 20)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "min_complexity": 20
}
```

Finds functions and methods with very high complexity (>= 20). These are prime candidates for refactoring.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **ANALYZE_COMPLEXITY_ERROR**: Database error, file access error, or analysis failure. Check database integrity, verify file paths, ensure files are readable. Syntax errors in files are skipped automatically.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `ANALYZE_COMPLEXITY_ERROR` | General error during complexity analysis | Check database integrity, verify file paths, ensur |

## Best practices

- Use min_complexity parameter to focus on problematic code
- Start with min_complexity=10 to find moderately complex code
- Use min_complexity=20+ to find very complex code requiring immediate attention
- Analyze specific files first before running project-wide analysis
- Review results sorted by complexity (highest first) to prioritize refactoring
- Combine with comprehensive_analysis for complete code quality overview

---
