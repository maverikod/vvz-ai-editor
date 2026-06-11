# get_class_hierarchy

**Command name:** `get_class_hierarchy`  
**Class:** `GetClassHierarchyMCPCommand`  
**Source:** `code_analysis/commands/ast/hierarchy.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_class_hierarchy command retrieves class inheritance hierarchy (inheritance tree) for a specific class or all classes in the project. It builds parent-child relationships based on base classes stored in the database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Queries classes table for project classes
5. If class_name provided, filters to that class
6. If file_path provided, filters to classes in that file
7. Parses bases field (JSON array of base class names)
8. Builds hierarchy map with parent-child relationships
9. Returns hierarchy structure with bases and children

Hierarchy Structure:
- Each class entry contains: name, file_path, line, bases (list), children (list)
- bases: List of base/parent class names
- children: List of derived/child class names
- Hierarchy is built by matching base names to class names

Use cases:
- Understand class inheritance structure
- Find all subclasses of a base class
- Find all parent classes of a derived class
- Visualize inheritance relationships
- Analyze class design patterns

Important notes:
- Bases are stored as JSON array in database
- Base class names are extracted from full qualified names (module.Class -> Class)
- If class_name provided, returns hierarchy for that class only
- If class_name not provided, returns all hierarchies in project

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `class_name` | string | No | Optional class name to get hierarchy for (if null, returns all hierarchies) |
| `file_path` | string | No | Optional file path to filter by (relative to project root) |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `class_name`: Class name if specified (or null)
- `hierarchy`: Dictionary mapping class names to hierarchy info. Each entry contains:
- name: Class name
- file_path: File where class is defined
- line: Line number where class is defined
- bases: List of base class names
- children: List of child class names
- `count`: Number of classes in hierarchy

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, GET_CLASS_HIERARCHY_ERROR (and others).

---

## Examples

### Correct usage

**Get hierarchy for specific class**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "class_name": "BaseHandler"
}
```

Returns inheritance hierarchy for BaseHandler class, showing its bases and all classes that inherit from it.

**Get all class hierarchies in project**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns complete inheritance hierarchy for all classes in the project.

**Get hierarchies for classes in specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/handlers.py"
}
```

Returns hierarchies for all classes defined in src/handlers.py file.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **GET_CLASS_HIERARCHY_ERROR**: Database error, JSON parsing error, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed. Check that bases field contains valid JSON.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `GET_CLASS_HIERARCHY_ERROR` | General error during hierarchy retrieval | Check database integrity, verify parameters, ensur |

## Best practices

- Use class_name parameter to focus on specific class hierarchy
- Use file_path filter to analyze classes in specific module
- Combine with export_graph (graph_type='hierarchy') for visualization
- Check bases and children arrays to understand inheritance flow
- Use for design pattern analysis and refactoring planning

---
