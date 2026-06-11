# comprehensive_analysis

**Command name:** `comprehensive_analysis`  
**Class:** `ComprehensiveAnalysisMCPCommand`  
**Source:** `code_analysis/commands/comprehensive_analysis_mcp.py`  
**Category:** analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The comprehensive_analysis command performs comprehensive code quality analysis combining multiple analysis types in a single operation. This is a long-running command executed via queue and provides detailed code quality metrics.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id:
   - If project_id parameter provided, validates it exists
   - If not provided, tries to infer from root_dir
   - If cannot infer, project_id remains None (analyze all projects)
4. Sets up dedicated log file (logs/comprehensive_analysis.log)
5. Initializes ComprehensiveAnalyzer and DuplicateDetector
6. If file_path provided:
   - Analyzes single file with all enabled checks
7. If file_path not provided:
   - If project_id is set: Analyzes all files in that project
   - If project_id is None: Analyzes ALL files in ALL projects
   - Processes files with progress tracking
   - Runs all enabled checks for each file
8. Aggregates results and creates summary statistics
9. Saves results to database (comprehensive_analysis_results table)
10. Returns comprehensive analysis results

Incremental Analysis (mtime gate):
- Analyzes only if file on disk is newer than latest DB analysis (or no prior record).
- Skips when disk mtime is equal to DB mtime within tolerance (0.1s).
- Skips when disk mtime is older than DB mtime (no re-analysis of older files).
- Single file mode: returns cached results when file is skipped.

Analysis Types:
- Placeholders: Finds TODO, FIXME, XXX, HACK, NOTE comments
- Stubs: Finds functions/methods with pass, ellipsis, NotImplementedError
- Empty methods: Finds methods without body (excluding abstract methods)
- Imports not at top: Finds imports after non-import statements
- Long files: Finds files exceeding max_lines threshold
- Duplicates: Finds code duplicates (structural and semantic)
- Flake8: Runs flake8 linter and reports errors
- Mypy: Runs mypy type checker and reports errors
- Missing docstrings: Finds files/classes/methods/functions without docstrings

Use cases:
- Complete code quality audit
- Identify code quality issues before refactoring
- Monitor code quality metrics
- Find technical debt indicators
- Generate code quality reports

Important notes:
- This is a long-running command (use_queue=True)
- When file_path not provided:
  * If project_id is set: analyzes all files in that project
  * If project_id is None: analyzes ALL files in ALL projects
- Progress is tracked and logged to logs/comprehensive_analysis.log
- Each check can be enabled/disabled via boolean parameters
- Results include summary statistics for all analysis types
- Results are saved to database (comprehensive_analysis_results table)
- Incremental analysis: only analyzes files whose disk mtime is newer than latest DB (with tolerance)
- Older-than-DB files are skipped; equal-within-tolerance files are skipped
- Single file mode: returns cached results when file is skipped

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | No | Optional path to specific file to analyze |
| `max_lines` | integer | No | Maximum lines threshold for long files Default: `400`. |
| `check_placeholders` | boolean | No | Check for placeholders (TODO, FIXME, etc.) Default: `true`. |
| `check_stubs` | boolean | No | Check for stub functions/methods Default: `true`. |
| `check_empty_methods` | boolean | No | Check for empty methods Default: `true`. |
| `check_imports` | boolean | No | Check for imports not at top of file Default: `true`. |
| `check_long_files` | boolean | No | Check for long files Default: `true`. |
| `check_duplicates` | boolean | No | Check for code duplicates Default: `true`. |
| `check_flake8` | boolean | No | Check code with flake8 linter Default: `true`. |
| `check_mypy` | boolean | No | Check code with mypy type checker Default: `true`. |
| `check_docstrings` | boolean | No | Check for missing docstrings (files, classes, methods) Default: `true`. |
| `duplicate_min_lines` | integer | No | Minimum lines for duplicate detection Default: `5`. |
| `duplicate_min_similarity` | number | No | Minimum similarity for duplicates Default: `0.8`. |
| `mypy_config_file` | string | No | Optional path to mypy config file |
| `limit` | integer | No | Max number of files to analyze per run (e.g. 10–15). None = all files. Use with offset for paging. |
| `offset` | integer | No | Number of files to skip (for paging with limit). Default 0. Default: `0`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `placeholders`: List of placeholder comments (TODO, FIXME, etc.)
- `stubs`: List of stub functions/methods
- `empty_methods`: List of empty methods
- `imports_not_at_top`: List of imports not at top of file
- `long_files`: List of files exceeding max_lines
- `duplicates`: List of duplicate code groups
- `flake8_errors`: List of flake8 linting errors
- `mypy_errors`: List of mypy type checking errors
- `missing_docstrings`: List of missing docstrings (files, classes, methods, functions)
- `summary`: Summary statistics dictionary with:
- total_placeholders, total_stubs, total_empty_methods
- total_imports_not_at_top, total_long_files
- total_duplicate_groups, total_duplicate_occurrences
- total_flake8_errors, files_with_flake8_errors
- total_mypy_errors, files_with_mypy_errors
- total_missing_docstrings, files_without_docstrings
- classes_without_docstrings, methods_without_docstrings
- functions_without_docstrings

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, FILE_NOT_FOUND, COMPREHENSIVE_ANALYSIS_ERROR (and others).

---

## Examples

### Correct usage

**Run full comprehensive analysis on all files in all projects**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Runs all checks on all files in all projects. This is a long-running operation. Use queue_get_job_status to check progress.

**Analyze all files in specific project**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

Runs all checks on all files in the specified project only. Faster than analyzing all projects.

**Analyze specific file with all checks**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py"
}
```

Runs all checks on src/main.py file only. Faster than project-wide analysis.

**Analyze in batches of 15 files (paging)**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "limit": 15,
  "offset": 0
}
```

Runs analysis on first 15 files. Next run use offset=15, then offset=30, etc.

**Run only specific checks**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "check_placeholders": true,
  "check_stubs": true,
  "check_duplicates": false,
  "check_flake8": false,
  "check_mypy": false
}
```

Runs only placeholder and stub checks, skipping duplicates and linting.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **FILE_NOT_FOUND**: file_path='src/main.py' but file doesn't exist. Verify file path is correct and file exists.

- **COMPREHENSIVE_ANALYSIS_ERROR**: Database error, analysis failure, or tool execution error. Check database integrity, verify file paths, ensure analysis tools (flake8, mypy) are installed. Check logs/comprehensive_analysis.log for details.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `FILE_NOT_FOUND` | File not found | Verify file path is correct and file exists. |
| `COMPREHENSIVE_ANALYSIS_ERROR` | General error during comprehensive analysis | Check database integrity, verify file paths, ensur |

## Best practices

- Use file_path parameter for faster analysis of specific files
- Use project_id parameter to analyze specific project instead of all projects
- Disable checks you don't need to improve performance
- Use queue_get_job_status to monitor progress for project-wide analysis
- Check logs/comprehensive_analysis.log for detailed analysis logs
- Review summary statistics first, then drill down into specific issues
- Run this command regularly to track code quality over time
- Use custom duplicate settings to focus on significant duplicates

---
