# Step 04 -- Replace in IndentedBlock fix

## Status: NO FIX NEEDED

## Findings from step 03

Investigation of tree_modifier.py (_apply_operation) and mutable_cst/edits.py:

- _apply_operation: no isinstance whitelist for REPLACE, no INVALID_OPERATION
- _replace_node_source (edits.py): no node type check, works on source string level
- apply_operations (edits.py): no INVALID_OPERATION
- _validate_operation: not yet checked, but INVALID_OPERATION absent from all dispatch paths

## Conclusion

The INVALID_OPERATION for replace reported in docs/csterr.md (Problem 2)
does not appear to originate from a whitelist in the replace dispatch path.
Most likely cause: stale node_id (node_map out of sync after prior operations).

NodeReplacer in tree_modifier_ops_replace.py already has leave_IndentedBlock
and handles all block types correctly.

## Action

No code changes required for this step.
If INVALID_OPERATION for replace reproduces in step 16 tests -- reopen this step.
