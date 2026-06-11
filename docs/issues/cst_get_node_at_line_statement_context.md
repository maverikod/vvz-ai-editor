# Issue: cst_get_node_at_line — return statement-level ancestor with source

## Problem

`cst_get_node_at_line(line=N)` currently returns the deepest (leaf) node at
that line — e.g. `Name`, `SimpleWhitespace`, `AssignTarget`. This is useless
for editing: the caller cannot pass a leaf `stable_id` to `cst_modify_tree`
because leaves are not replaceable statement units.

To find the correct node for replacement the caller must:
1. Take the leaf `parent_id`
2. Call `cst_get_node_info` on the parent
3. Repeat until reaching a statement-level node
4. Separately read the source to understand what to replace it with

This costs 3–5 round trips and makes CST editing impractical in agentic
workflows with context constraints.

## Expected behaviour

`cst_get_node_at_line` should walk up from the leaf and return the nearest
**statement-level ancestor** together with its full source fragment annotated
with absolute line numbers. Example response:

```json
{
  "line": 246,
  "statement": {
    "stable_id": "27e3156b-...",
    "type": "Try",
    "start_line": 245,
    "end_line": 258,
    "source": "        try:\n245:         file_path = file_path.resolve()\n246:         root_path = root_path.resolve()\n247:         try:\n248:             rel_path = str(file_path.relative_to(root_path))\n..."
  },
  "leaf": {
    "stable_id": "d204ad80-...",
    "type": "Name",
    "start_line": 246,
    "end_line": 246
  }
}
```

## Statement-level node types

Nodes that qualify as statement-level ancestors (stop walking up at first match):

```python
STATEMENT_TYPES = {
    "Assign", "AugAssign", "AnnAssign",
    "If", "For", "While", "Try", "With",
    "Return", "Raise", "Assert", "Delete",
    "Expr",        # standalone expression statement
    "FunctionDef", "AsyncFunctionDef", "ClassDef",
    "Import", "ImportFrom",
    "Global", "Nonlocal", "Pass", "Break", "Continue",
}
```

If the leaf is already a statement-level node, return it directly.
If no statement ancestor is found (e.g. leaf is inside a decorator), return
the nearest named ancestor and set `"fallback": true`.

## Source annotation format

The `source` field must:
- Contain the full text of the statement node
- Prefix each line with its absolute line number and a tab: `"246\t    file_path = ..."`
- Use the same indentation as in the original file (do not strip)
- Be capped at 60 lines; if longer, truncate the middle and insert
  `"... (N lines omitted) ..."` marker

## New parameter

Add optional `statement_level: bool = True`. When `False`, preserve current
behaviour (return leaf node only, no source). This allows callers that need
only the leaf to avoid the extra work.

## Implementation sketch

```python
def _find_statement_ancestor(node_id: str, tree: CSTTree) -> str:
    """Walk parent chain; return first statement-level node id."""
    current_id = node_id
    while current_id:
        node_type = type(tree.node_map[current_id]).__name__
        if node_type in STATEMENT_TYPES:
            return current_id
        meta = tree.metadata_map.get(current_id)
        if meta is None:
            break
        current_id = meta.parent_id
    return node_id  # fallback: return leaf


def _annotate_source(source: str, start_line: int) -> str:
    """Prefix each line with its absolute line number."""
    lines = source.splitlines()
    annotated = [
        f"{start_line + i}\t{line}"
        for i, line in enumerate(lines)
    ]
    MAX_LINES = 60
    if len(annotated) > MAX_LINES:
        half = MAX_LINES // 2
        omitted = len(annotated) - MAX_LINES
        annotated = (
            annotated[:half]
            + [f"... ({omitted} lines omitted) ..."]
            + annotated[-half:]
        )
    return "\n".join(annotated)
```

## Motivation

The primary use case is agentic code editing:

1. Agent finds a bug at line N via logs or search
2. Calls `cst_get_node_at_line(line=N)`
3. Receives the statement node + its source in one call
4. Understands what to replace without additional round trips
5. Calls `cst_modify_tree` with `stable_id` + new code

This reduces CST edit workflow from 5–7 tool calls to 2–3.

## Related

- `cst_modify_tree` — consumes `stable_id` from this call
- `cst_get_node_info` — still useful for deeper inspection
- Bug that exposed this issue: `analyze_file` in
  `code_analysis/commands/update_indexes_analyzer.py` line 246
  (`file_path.resolve()` uses CWD instead of `root_path / file_path`)
