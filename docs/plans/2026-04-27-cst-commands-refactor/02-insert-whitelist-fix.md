# Step 02 -- Insert whitelist fix

## Goal
Patch two files to allow insert into any node whose body is IndentedBlock.
Do not change insert_node_relative -- it already works.

## Requires
Step 01 completed. Use line numbers from step 01 answers.

## Files to edit

```text
code_analysis/core/cst_tree/tree_modifier_ops_insert.py
code_analysis/core/cst_tree/tree_modifier_ops_find.py
```

## Change 1 -- tree_modifier_ops_insert.py: expand the isinstance check

Find the block starting at line ~53 that looks like:

```python
if isinstance(parent_node, cst.Module):
    body = list(parent_node.body)
elif isinstance(parent_node, (cst.FunctionDef, cst.ClassDef)) and isinstance(
    parent_node.body, cst.IndentedBlock
):
    body = list(parent_node.body.body)
else:
    raise ValueError(
        f"Parent node {parent_node_id} has no insertable body (Module or IndentedBlock)"
    )
```

Replace with:

```python
if isinstance(parent_node, cst.Module):
    body = list(parent_node.body)
elif isinstance(parent_node, cst.IndentedBlock):
    # parent_node_id points directly to the IndentedBlock
    body = list(parent_node.body)
elif hasattr(parent_node, "body") and isinstance(
    getattr(parent_node, "body", None), cst.IndentedBlock
):
    # FunctionDef, ClassDef, If, For, While, With, Try,
    # ExceptHandler, Else, Finally -- any node with body: IndentedBlock
    body = list(parent_node.body.body)
else:
    raise ValueError(
        f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
        f"has no insertable statement body. "
        f"Supported: Module, IndentedBlock, or any node whose body is IndentedBlock. "
        f"Note: one-liner blocks (SimpleStatementSuite) and Match nodes "
        f"are not supported for positional insert."
    )
```

## Change 2 -- tree_modifier_ops_insert.py: add leave_IndentedBlock to PositionInserter

In the PositionInserter class add a leave_IndentedBlock method that handles
the case where parent_node is IndentedBlock directly or where parent_node
is a compound statement containing an IndentedBlock body.

The existing leave_FunctionDef and leave_ClassDef must remain unchanged.
Add a new method using the SAME pattern but for IndentedBlock:

```python
def leave_IndentedBlock(
    self,
    original_node: cst.IndentedBlock,
    updated_node: cst.IndentedBlock,
) -> cst.IndentedBlock:
    """Handle insert when parent is IndentedBlock directly."""
    if original_node is not self.parent_node:
        return updated_node
    self.done = True
    return updated_node.with_changes(body=tuple(self.replacement_body))
```

Also update the existing leave_FunctionDef and leave_ClassDef to use
`updated_node.body.with_changes(body=...)` instead of
`cst.IndentedBlock(body=...)` to preserve indent/header/footer:

```python
# BEFORE (loses indent/header/footer):
return updated_node.with_changes(
    body=cst.IndentedBlock(body=tuple(self.replacement_body))
)

# AFTER (preserves indent/header/footer):
return updated_node.with_changes(
    body=updated_node.body.with_changes(body=tuple(self.replacement_body))
)
```

## Change 3 -- tree_modifier_ops_find.py: expand ParentFinder whitelist

Find the ParentFinder visitor class and its visit method with:

```python
if not isinstance(node, (cst.Module, cst.FunctionDef, cst.ClassDef)):
    return True
```

Replace with:

```python
is_container = (
    isinstance(node, (cst.Module, cst.IndentedBlock))
    or (
        hasattr(node, "body")
        and isinstance(getattr(node, "body", None), cst.IndentedBlock)
    )
)
if not is_container:
    return True
```

Also update the return type annotation from:
```python
Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]]
```
to:
```python
Optional[cst.CSTNode]
```

## Verification after change

1. Run lint_code on both edited files -- expect 0 errors.
2. Run type_check_code on both edited files -- expect 0 new errors.
3. Proceed to step 10 for functional testing.

## Risk
Medium. Changes affect insert path used by cst_modify_tree.
insert_node_relative is not touched and remains the fallback.
If something breaks, restore from backup.

## Must not do
- Do not change insert_node_relative.
- Do not change NodeReplacer in tree_modifier_ops_replace.py.
- Do not add on_leave override without calling super().on_leave() first.
