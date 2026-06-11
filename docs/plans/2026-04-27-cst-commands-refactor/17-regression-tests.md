# Step 17 -- Regression tests: existing CST operations still work

## Goal
Verify all changes from steps 02-14 did not break existing CST functionality.

## Requires
Steps 02, 04, 07, 08, 10, 12, 14 completed.

## Test 1 -- insert_node_relative still works (unchanged code path)
1. Load any small project file with cst_load_file.
2. Find any statement node_id.
3. Call cst_modify_tree insert with target_node_id (not parent_node_id),
   position=after, code="# regression comment\n".
4. Verify success. Unload.

## Test 2 -- replace still works in function body (original case)
1. Load file, find simple assignment inside a function.
2. Call cst_modify_tree replace. Verify success. Unload.

## Test 3 -- insert into FunctionDef body still works
1. Load file, find FunctionDef node.
2. Call cst_modify_tree insert with parent_node_id = FunctionDef, position=first.
3. Verify success. Unload.

## Test 4 -- insert into ClassDef body still works
Same as Test 3 with ClassDef.

## Test 5 -- insert into Module body still works
1. Load file.
2. Call cst_modify_tree insert with parent_node_id = Module root, position=last.
3. Verify success. Unload.

## Test 6 -- cst_list_trees and cst_unload_tree still work
1. Load two files. Call cst_list_trees -- verify count=2.
2. Unload one -- verify was_present=true.
3. Call cst_list_trees -- verify count=1. Unload remaining.

## Test 7 -- query_cst diff is non-empty after fix
1. Pick any Python file.
2. Call query_cst with a replacement that changes one identifier.
3. Verify diff is non-empty. Verify replaced >= 1.

## Test 8 -- compose_cst_module validate_syntax_only=false still validates mypy
1. Call compose_cst_module with validate_syntax_only=false (default).
2. On a file with known mypy errors -- verify mypy errors are reported.

## Test 9 -- result fields present in cst_modify_tree response
1. Call cst_modify_tree with preview=true.
2. Verify response contains file_written=false and preview_only=true.
3. Call cst_modify_tree with preview=false (actual change).
4. Verify response contains file_written=true and preview_only=false.

## Expected results
All 9 tests pass without errors.

## If any test fails
Report test number and exact error. Do not attempt to fix.

## Risk
None -- read/test only. Unload all trees at the end.
