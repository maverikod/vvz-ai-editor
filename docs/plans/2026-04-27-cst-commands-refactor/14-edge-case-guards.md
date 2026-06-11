# Step 14 -- Edge case guards: SimpleStatementSuite and Match

## Goal
Add explicit guards in insert_node_at_position for two cases
that cannot support positional insert.

## Requires
Step 02 completed.

## File to edit

```text
code_analysis/core/cst_tree/tree_modifier_ops_insert.py
```

## Change -- add guards BEFORE the main isinstance block from step 02

```python
# Guard: Match has no body field -- it has cases: Sequence[MatchCase].
# To insert into a match arm, use the MatchCase node as parent (it has body: IndentedBlock).
if isinstance(parent_node, cst.Match):
    raise ValueError(
        f"Parent node {parent_node_id} is a Match statement. "
        f"Match has no statement body -- it has cases (Sequence[MatchCase]). "
        f"To insert into a match arm, use the MatchCase node as parent_node_id."
    )

# Guard: SimpleStatementSuite is a one-liner block (if x: pass).
# Its body is Sequence[BaseSmallStatement], not Sequence[BaseStatement].
# Cannot insert a full statement there.
if isinstance(parent_node, cst.SimpleStatementSuite):
    raise ValueError(
        f"Parent node {parent_node_id} is a one-liner block (SimpleStatementSuite). "
        f"One-liner blocks cannot contain multiple statements. "
        f"Expand the block to IndentedBlock first, then insert."
    )
```

Note: MatchCase.body IS IndentedBlock -- insert into MatchCase works
via the structural check added in step 02. Only Match itself is blocked.

## Verification after change

1. Run lint_code on edited file -- expect 0 errors.
2. Call cst_modify_tree insert with parent_node_id = Match node.
   Verify error contains "Match statement" and "MatchCase".
3. Call cst_modify_tree insert with parent_node_id = MatchCase node.
   Verify SUCCESS (MatchCase.body is IndentedBlock -- allowed).
4. Call cst_modify_tree insert with parent_node_id = SimpleStatementSuite.
   Verify error contains "one-liner" and "IndentedBlock".

## Risk
Low. Guards fire before any modification. Error messages are informative.
