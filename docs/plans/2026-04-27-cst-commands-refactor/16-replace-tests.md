# Step 16 -- Functional tests: replace in IndentedBlock contexts

## Goal
Verify replace works correctly in all IndentedBlock contexts.
Run after step 04.

## Test file setup
Same test file as step 15 (or recreate if deleted).

## Test cases

```text
A: Replace If-statement inside function body (direct child of IndentedBlock)
B: Replace assignment inside If.body
C: Replace pass inside ExceptHandler.body
D: Replace pass inside Finally.body
E: Replace pass inside With.body
```

## For each test case
1. Load file with cst_load_file.
2. Find node_id of target statement with cst_find_node.
3. Call cst_modify_tree replace with that node_id,
   code = "y = 2\n".
4. Verify result does NOT contain INVALID_OPERATION.
5. Verify replacement appears via cst_get_node_info.
6. Unload with cst_unload_tree.

## If a test case fails
Report which case (A-E) failed and the exact error.
Note: if NodeReplacer works but dispatch fails, step 04 fix is incomplete.

## Risk
None -- uses temporary test file.
