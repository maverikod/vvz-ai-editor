# query_cst

**Command name:** `query_cst`  
**Class:** `QueryCSTCommand`  
**Source:** `code_analysis/commands/query_cst_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

> **AI / MCP editing:** for XPath on the **open edit-session** draft tree, use [`universal_file_search`](../file_editing/universal_file_search.md) (`session_id`). `query_cst` parses from disk/file path — no session draft.

## Purpose (Предназначение)

The query_cst command queries Python source code using CSTQuery selectors to locate specific LibCST nodes. It provides a jQuery/XPath-like selector language for finding nodes while preserving formatting and comments.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves file_path (absolute or relative to root_dir)
3. Validates file is a .py file
4. Validates file exists
5. Reads file source code
6. Parses source using LibCST
7. Applies CSTQuery selector to find matching nodes
8. Generates node IDs for each match
9. Optionally includes code snippets
10. Limits results to max_results if specified
11. Returns list of matches with metadata

CSTQuery Selector Syntax:
- Selectors are sequences of steps connected by combinators
- Descendant combinator: whitespace (A B finds B inside A)
- Child combinator: > (A > B finds B as direct child of A)
- Each step: TYPE or * with optional predicates and pseudos
- Predicates: [attr OP value] only (e.g. [name="MyClass"]). Bare [attr] like [name] is invalid; operator and value are required.
- Pseudos: :first, :last, :nth(N)

Supported TYPE Aliases:
- module, class, function, method, stmt, smallstmt, import, node
- LibCST node class names: If, For, Try, With, Return, Assign, Call, etc.

Predicate Operators:
- = exact equality
- != not equal
- ~= substring match
- ^= prefix match
- $= suffix match

Supported Attributes:
- type: LibCST node type
- kind: Node kind (stmt, smallstmt, class, function, method, etc.)
- name: Node name (for named nodes)
- qualname: Qualified name (for methods: ClassName.method)
- start_line, end_line: Line numbers

Node Information:
- node_id: Stable-enough identifier (span-based) for cst_modify_tree
- kind: Node kind classification
- type: LibCST node type
- name: Node name (if applicable)
- qualname: Qualified name (if applicable)
- start_line, start_col: Starting position
- end_line, end_col: Ending position
- code: Code snippet (if include_code=True)

Use cases:
- Find specific nodes by type or name
- Locate statements, expressions, or declarations
- Discover code patterns
- Find nodes for refactoring operations
- Analyze code structure
- Prepare for cst_modify_tree operations

Typical Workflow (query only):
1. Use query_cst to find target nodes
2. Get node_id from matches
3. Use cst_modify_tree with selector kind='node_id' or kind='cst_query'
4. Preview diff and compile result
5. Apply changes if satisfied

Replace mode (find + replace in one call):
Pass replace_with (string) or code_lines (array of lines). Optionally match_index (0-based, which match to replace) or replace_all (replace every match). File is backed up, then updated; database is refreshed. Response is compact: replaced count, file_path, backup_uuid.

Important notes:
- Selector syntax follows CSTQuery rules (see docs/CST_QUERY.md)
- node_id is span-based and stable enough for patch workflows
- Results can be truncated if max_results limit is reached
- include_code=True can make response large for many matches
- Use max_results to limit output size
- Line numbers are 1-based
- Column numbers are 0-based

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). Required for commands that operate on a project. |
| `file_path` | string | **Yes** | Target python file path (relative to project root) |
| `selector` | string | No | CSTQuery selector string. Predicate must be [attr OP value] (e.g. [name=\"foo\"]); [name] alone is invalid. |
| `include_code` | boolean | No | If true, include code snippets for each match (can be large) Default: `false`. |
| `max_results` | integer | No | Maximum number of matches to return Default: `200`. |
| `replace_with` | string | No | If set, replace the matched node(s) with this code (single string). Use code_lines for multi-line to avoid escaping. One call = find + replace. |
| `code_lines` | array | No | If set, replace the matched node(s) with these lines (joined by newline). Prefer over replace_with for multi-line code. |
| `match_index` | integer | No | When replacing: which match to replace (0-based). Ignored if replace_all is true. Default: `0`. |
| `replace_all` | boolean | No | When replacing: if true, replace all matches with the same new code. match_index is ignored. Default: `false`. |
| `replacements` | array | No | When set: replace multiple matches with different code per match. Each entry: match_index (0-based) and either replace_with or code_lines. Ignored if replace_with/code_lines (single-code path) is used |
| `start_line` | integer | No | 1-based start line for range-based replace. When used with end_line (and replace_with/code_lines), replace the statement(s) covering this range. Optional; if both start_line and end_line are set, rang |
| `end_line` | integer | No | 1-based end line for range-based replace. Must be >= start_line. When both start_line and end_line are set, replace that line range. |
| `preview` | boolean | No | If true, run replace in memory and return diff/modified_source without writing to file. No backup, no file change. Default: `false`. |
| `dry_run` | boolean | No | Alias for preview: if true, same as preview=true. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `file_path`: Path to queried file
- `selector`: Selector string that was used
- `truncated`: True if results were truncated due to max_results
- `matches`: List of match dictionaries. Each contains:
- node_id: Stable identifier for cst_modify_tree
- kind: Node kind (stmt, smallstmt, class, function, method, etc.)
- type: LibCST node type (If, Return, ClassDef, FunctionDef, etc.)
- name: Node name (if applicable)
- qualname: Qualified name (if applicable)
- start_line, start_col: Starting position (1-based line, 0-based col)
- end_line, end_col: Ending position (1-based line, 0-based col)
- code: Code snippet (if include_code=True)
- `replace_response`: When replace_with or code_lines is used, success data contains:
- replaced: Number of nodes replaced
- removed: Number of nodes removed (empty new_code)
- file_path: Path to modified file
- backup_uuid: Backup identifier (if backup was created)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_FILE, FILE_NOT_FOUND, CST_QUERY_PARSE_ERROR, CST_QUERY_ERROR, CST_QUERY_NO_MATCH, CST_QUERY_MATCH_INDEX, CST_REPLACE_ERROR, CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX, CST_QUERY_REPLACEMENTS_MISSING_CODE, CST_QUERY_REPLACEMENTS_BOTH_CODE (and others).

---

## Examples

### Correct usage

**Find class by exact name**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/main.py",
  "selector": "class[name=\"MyClass\"]"
}
```

Finds all classes named exactly 'MyClass' in main.py. Returns node_id that can be used with cst_modify_tree.

**Find class by name prefix**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/models.py",
  "selector": "class[name^=\"Base\"]"
}
```

Finds all classes whose names start with 'Base' (e.g., BaseModel, BaseView). Uses prefix match operator (^=).

**Find class by name suffix**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/handlers.py",
  "selector": "class[name$=\"Handler\"]"
}
```

Finds all classes whose names end with 'Handler' (e.g., RequestHandler, EventHandler). Uses suffix match operator ($=).

**Find class by name substring**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/services.py",
  "selector": "class[name~=\"Service\"]"
}
```

Finds all classes whose names contain 'Service' (e.g., UserService, PaymentService). Uses substring match operator (~=).

**Find all return statements**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/utils.py",
  "selector": "smallstmt[type=\"Return\"]"
}
```

Finds all return statements in utils.py. Useful for analyzing control flow and finding early returns.

### Incorrect usage

- **INVALID_FILE**: File is not a Python file. Ensure file_path points to a .py file

- **FILE_NOT_FOUND**: File does not exist. Verify file_path is correct and file exists

- **CST_QUERY_PARSE_ERROR**: Invalid selector syntax. Check selector syntax. Ensure:
- Proper predicate syntax: [attr OP value]
- Valid operators: =, !=, ~=, ^=, $=
- Valid pseudos: :first, :last, :nth(N)
- Proper combinator usage: whitespace or >
See docs/CST_QUERY.md for syntax reference.

- **CST_QUERY_ERROR**: Error during query execution. 

- **CST_QUERY_NO_MATCH**: Selector matched no nodes (replace mode only). Verify selector matches at least one node in the file

- **CST_QUERY_MATCH_INDEX**: match_index out of range (replace mode only). Use match_index between 0 and (match_count - 1), or use replace_all

- **CST_REPLACE_ERROR**: Replace failed (e.g. unsupported node kind or parse error). Ensure new code is valid Python; replace supports stmt/smallstmt/function/class/method

- **CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX**: Duplicate match_index in replacements list. Use each match_index at most once in replacements

- **CST_QUERY_REPLACEMENTS_MISSING_CODE**: Replacements entry has neither replace_with nor code_lines. Provide replace_with (string) or code_lines (array of strings)

- **CST_QUERY_REPLACEMENTS_BOTH_CODE**: Replacements entry has both replace_with and code_lines. Use only one of replace_with or code_lines per entry

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_FILE` | File is not a Python file | Ensure file_path points to a .py file |
| `FILE_NOT_FOUND` | File does not exist | Verify file_path is correct and file exists |
| `CST_QUERY_PARSE_ERROR` | Invalid selector syntax | Check selector syntax. Ensure:
- Proper predicate  |
| `CST_QUERY_ERROR` | Error during query execution |  |
| `CST_QUERY_NO_MATCH` | Selector matched no nodes (replace mode only) | Verify selector matches at least one node in the f |
| `CST_QUERY_MATCH_INDEX` | match_index out of range (replace mode only) | Use match_index between 0 and (match_count - 1), o |
| `CST_REPLACE_ERROR` | Replace failed (e.g. unsupported node kind or parse error) | Ensure new code is valid Python; replace supports  |
| `CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX` | Duplicate match_index in replacements list | Use each match_index at most once in replacements |
| `CST_QUERY_REPLACEMENTS_MISSING_CODE` | Replacements entry has neither replace_with nor code_lines | Provide replace_with (string) or code_lines (array |
| `CST_QUERY_REPLACEMENTS_BOTH_CODE` | Replacements entry has both replace_with and code_lines | Use only one of replace_with or code_lines per ent |

## Best practices

- For find+replace in one call: pass replace_with or code_lines (and optionally match_index or replace_all)
- Use query_cst to find specific nodes before cst_modify_tree
- Save node_id from matches for use in cst_modify_tree
- Use include_code=True only when needed (can be large)
- Set max_results to limit output size for broad queries
- Check truncated field to see if results were limited
- Use specific selectors to find exact nodes
- Combine selectors with combinators for complex queries

---
