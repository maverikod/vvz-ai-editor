# cst_find_node

**Command name:** `cst_find_node`  
**Class:** `CSTFindNodeCommand`  
**Source:** `code_analysis/commands/cst_find_node_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

> **AI / MCP editing:** use [`universal_file_search`](../file_editing/universal_file_search.md) with `session_id` from `universal_file_open` to search the **edit-session** CST tree. This command uses legacy `tree_id` from `cst_load_file` — separate in-memory session.

## Purpose (Предназначение)

The cst_find_node command finds nodes in a CST tree using two search modes: simple search (by type, name, position) or XPath-like search (using CSTQuery selectors). Search is performed on the server using the tree stored in memory, so no need to transfer the entire tree to the client.

Operation flow:
1. Validates tree_id exists
2. Validates search parameters based on search_type
3. Performs search on tree stored in memory
4. Returns node metadata for matching nodes

Search Types:
1. Simple search (search_type='simple'):
   - Filter by node_type (e.g., 'FunctionDef', 'ClassDef')
   - Filter by name (exact match)
   - Filter by qualname (exact match)
   - Filter by line range (start_line, end_line)
   - Multiple filters can be combined (AND logic)
2. XPath-like search (search_type='xpath'):
   - Uses CSTQuery selector syntax
   - Supported combinators:
     - `A B` — descendant (B anywhere inside A)
     - `A > B` — direct child
     - `//B` — B anywhere in the tree (shorthand for recursive descendant from root)
   - Supported predicates: `[attr OP value]` or `[@attr OP value]` (`@` is optional)
     - String operators: `=`, `!=`, `~=` (contains), `^=` (starts-with), `$=` (ends-with)
     - Numeric operators: `>`, `<`, `>=`, `<=` — compare integer attribute values
     - Numeric attributes: `start_line`, `end_line`, `children_count`
     - String attributes: `name`, `qualname`, `type`, `kind`, `module`
   - Supported pseudos:
     - `:first`, `:last`, `:nth(N)` — positional filters among siblings
     - `:not(selector)` — exclude nodes matching inner selector
   - Type wildcard: `Def:*` matches any type ending with `Def` (e.g. FunctionDef, ClassDef)
   - Examples:
     - `function[name='foo']` — function named foo
     - `//FunctionDef[@name='foo']` — same, XPath-style
     - `function[start_line>=100]` — functions at line 100+
     - `function[@name^='_']:not([name^='__'])` — private but not dunder
     - `class > method:first` — first method of each class


---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `search_type` | string | No | Search type: 'simple' or 'xpath' Default: `"xpath"`. |
| `query` | string | No | CSTQuery selector string (for xpath search) |
| `node_type` | string | No | Node type filter (for simple search, e.g., 'FunctionDef', 'ClassDef') |
| `name` | string | No | Node name filter (for simple search) |
| `qualname` | string | No | Qualified name filter (for simple search) |
| `start_line` | integer | No | Start line filter (for simple search) |
| `end_line` | integer | No | End line filter (for simple search) |
| `require_one` | boolean | No | If true, require exactly one match; otherwise return NoMatch or NonUniqueMatch with candidates. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID that was searched
- `search_type`: Search type that was used
- `matches`: List of node metadata dictionaries for matching nodes
- `total_matches`: Total number of matches found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_SEARCH, CST_FIND_ERROR (and others).

---

## Examples

### Correct usage

**XPath search: find class by name**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "search_type": "xpath",
  "query": "class[name=\"MyClass\"]"
}
```

Finds all classes named 'MyClass' using CSTQuery selector. Uses XPath-like search with predicate matching.

**XPath search: find all return statements**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "search_type": "xpath",
  "query": "smallstmt[type=\"Return\"]"
}
```

Finds all return statements in the tree. Uses XPath search with type predicate.

**XPath search: find first return in function**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "search_type": "xpath",
  "query": "function[name=\"process_data\"] smallstmt[type=\"Return\"]:first"
}
```

Finds the first return statement in process_data function. Uses descendant combinator and :first pseudo selector.

**Simple search: find by node type**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "search_type": "simple",
  "node_type": "FunctionDef"
}
```

Finds all functions in the tree using simple search. Faster than XPath for simple type-based queries.

**Simple search: find by name**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "search_type": "simple",
  "name": "main"
}
```

Finds all nodes named 'main' using simple search. Exact match on node name.

### Incorrect usage

- **INVALID_SEARCH**: Invalid search parameters. Check search parameters:
- For xpath search: query parameter is required
- For simple search: at least one filter should be provided
- search_type must be 'simple' or 'xpath'
See command metadata for parameter requirements.

- **CST_FIND_ERROR**: Error during search. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_SEARCH` | Invalid search parameters | Check search parameters:
- For xpath search: query |
| `CST_FIND_ERROR` | Error during search |  |

## Best practices

- Use XPath search for complex queries with CSTQuery selectors
- Use simple search for basic type/name/position filters (faster)
- Tree must be loaded first with cst_load_file
- Save node_id from results for use with cst_modify_tree
- XPath search supports all CSTQuery features (see query_cst examples)
- Simple search filters can be combined (AND logic)
- Search is performed on server (efficient, no tree transfer)

---