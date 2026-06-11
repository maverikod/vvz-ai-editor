# list_errors_by_category

**Command name:** `list_errors_by_category`  
**Class:** `ListErrorsByCategoryMCPCommand`  
**Source:** `code_analysis/commands/code_mapper_mcp_commands.py`  
**Category:** code_mapper

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_errors_by_category command lists code errors grouped by category. This is equivalent to old code_mapper functionality for listing code issues. It provides a categorized view of all code quality issues in the project.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. If project_id is None, lists errors from all projects
5. Queries issues table grouped by issue_type
6. Aggregates issues by category
7. Creates summary statistics
8. Returns categorized errors with summary

Use cases:
- Get overview of code quality issues by category
- Identify most common issue types
- Track code quality metrics
- Generate code quality reports

Important notes:
- If project_id is None, returns errors from all projects
- Issues are grouped by issue_type (category)
- Summary includes counts per category and total
- Equivalent to code_mapper functionality

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | No | Optional project UUID (from list_projects); if omitted, all projects |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `categories`: Dictionary mapping issue_type to list of issues. Each issue contains file path, line number, and issue details.
- `summary`: Summary statistics dictionary with:
- Counts per category (issue_type)
- total: Total number of issues
- `total`: Total number of issues found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** LIST_ERRORS_ERROR (and others).

---

## Examples

### Correct usage

**List errors for specific project**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Lists all code errors grouped by category for the project.

**List errors from all projects**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "project_id": null
}
```

Lists errors from all projects in the database (if project not found).

### Incorrect usage

- **LIST_ERRORS_ERROR**: Database error or invalid parameters. Check database integrity, verify parameters, ensure project has been indexed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `LIST_ERRORS_ERROR` | General error during error listing | Check database integrity, verify parameters, ensur |

## Best practices

- Use this command to get overview of code quality issues
- Review summary statistics first, then drill down into specific categories
- Combine with comprehensive_analysis for detailed issue analysis
- Use for tracking code quality trends over time

---
