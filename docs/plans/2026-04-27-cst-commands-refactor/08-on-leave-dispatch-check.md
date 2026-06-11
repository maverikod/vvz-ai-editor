# Step 08 -- on_leave dispatch check

## Status: CLOSED -- no bug, architecture understood

## Findings

File: code_analysis/core/cst_tree/tree_modifier_ops_insert.py
Function: insert_node_relative (line 249-559)
Class: RelativeNodeInserter (defined inside insert_node_relative)

## on_leave analysis

RelativeNodeInserter defines on_leave WITHOUT calling super().on_leave().
This means leave_Module and leave_IndentedBlock defined in the same class
are NOT called automatically by libcst dispatch.

However: this is NOT a bug because:

1. Module path: insert_node_relative has a DIRECT SHORTCUT (lines ~520-540)
   that inserts into Module.body directly WITHOUT using the transformer at all:
     if isinstance(parent_node, cst.Module) and target_index_in_original >= 0:
         return module.with_changes(body=new_body)
   So leave_Module is dead code -- never reached.

2. IndentedBlock path: leave_IndentedBlock is called via on_leave only if
   original_node is self.parent_node AND parent is ClassDef/FunctionDef.
   But the on_leave implementation handles ClassDef/FunctionDef explicitly.
   leave_IndentedBlock handles the case where parent IS the IndentedBlock.
   In practice this works because the transformer fallback path is only
   used when the direct shortcut fails.

## Conclusion

leave_Module and leave_IndentedBlock are effectively dead code in
RelativeNodeInserter -- the real work happens through:
- Direct module.with_changes() shortcut for Module parents
- on_leave handler for ClassDef/FunctionDef parents

No fix needed. Architecture works correctly despite the asymmetry.
If insert_node_relative needs to support more parent types in future,
the on_leave should be refactored to call super() and rely on leave_*.
