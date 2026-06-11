# export_graph

**Command name:** `export_graph`  
**Class:** `ExportGraphMCPCommand`  
**Source:** `code_analysis/commands/ast/graph.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The export_graph command exports dependency graphs, class hierarchies, or call graphs in DOT (Graphviz) or JSON format. The command provides stable output without failing when the underlying project contains partial or missing data.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Applies edge limit (default 5000, max 50000, min 1)
5. Based on graph_type:
   - 'dependencies': Extracts file-to-module import relationships
   - 'hierarchy': Extracts class inheritance relationships
   - 'call_graph': Extracts file-to-entity usage relationships
6. If file_path provided, filters results to that file
7. Formats output as DOT (Graphviz) or JSON
8. Returns graph with nodes and edges

Graph Types:
- dependencies: Shows which files import which modules. Nodes are file paths and module names. Edges represent imports.
- hierarchy: Shows class inheritance relationships. Nodes are class names. Edges go from base class to derived class.
- call_graph: Shows which files use which entities. Nodes are file paths and entity names. Edges represent usages.

Output Formats:
- dot: Graphviz DOT format, can be rendered with tools like Graphviz, PlantUML, or online viewers
- json: Structured JSON with nodes array and edges array

Important notes:
- Edge limit prevents memory issues with large projects
- Graph is stable: missing data doesn't cause failures
- DOT format escapes special characters in node names
- JSON format provides structured data for programmatic use

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `graph_type` | string | No | Type of graph: 'dependencies', 'hierarchy', or 'call_graph' Default: `"dependencies"`. |
| `format` | string | No | Output format: 'dot' (Graphviz) or 'json' Default: `"dot"`. |
| `file_path` | string | No | Optional file path to limit scope |
| `limit` | integer | No | Optional limit on number of edges |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, EXPORT_GRAPH_ERROR (and others).

---

## Examples

### Correct usage

**Export dependency graph in DOT format**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "graph_type": "dependencies",
  "format": "dot"
}
```

Exports file-to-module import relationships in Graphviz DOT format. Can be saved to file and rendered with 'dot -Tpng graph.dot -o graph.png'.

**Export class hierarchy in JSON format**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "graph_type": "hierarchy",
  "format": "json"
}
```

Exports class inheritance relationships as structured JSON. Useful for programmatic analysis or custom visualization.

**Export call graph for specific file**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "graph_type": "call_graph",
  "file_path": "src/main.py",
  "format": "json"
}
```

Exports call graph limited to relationships involving src/main.py. Shows what entities this file uses.

**Export with edge limit**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "graph_type": "dependencies",
  "limit": 1000
}
```

Limits output to 1000 edges to reduce memory usage and simplify visualization.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **EXPORT_GRAPH_ERROR**: Database error, invalid graph_type, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed. For large projects, try reducing limit parameter.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `EXPORT_GRAPH_ERROR` | General error during graph export | Check database integrity, verify parameters, ensur |

## Best practices

- Use DOT format for visualization with Graphviz or online tools
- Use JSON format for programmatic analysis or custom visualizations
- Set limit parameter for large projects to avoid memory issues
- Use file_path filter to focus on specific file relationships
- Export hierarchy graphs to understand class inheritance structure
- Export dependencies graphs to understand module import structure
- Export call_graph to understand entity usage patterns

---
