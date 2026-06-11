# Step 15 -- Functional tests: insert in all compound statement bodies

## Goal
Verify insert_node_at_position works for ALL compound statement body types.
Run after steps 02 and 14.

## Test file setup
Create a test file via cst_create_file with the following content.
Load it with cst_load_file. Use declarative mode to get all node_ids.

```python
def f():
    if True:
        pass
    else:
        pass
    for i in range(10):
        pass
    while True:
        break
    try:
        pass
    except Exception:
        pass
    finally:
        pass
    with open("f") as fh:
        pass
    match x:
        case 1:
            pass
```

## For each test case
1. Find node_id of the target body using cst_find_node.
2. Call cst_modify_tree insert with parent_node_id = body node, position=first,
   code = "x = 1\n".
3. Verify result does NOT contain INVALID_OPERATION.
4. Verify new statement appears via cst_get_node_info.

## Test cases

```text
A: If.body (the then-branch)
B: Else.body (the else-branch)
C: For.body
D: While.body
E: Try.body
F: ExceptHandler.body
G: Finally.body
H: With.body
I: MatchCase.body
J: Nested -- If.body inside For.body (two levels deep)
```

## After all tests
Unload tree with cst_unload_tree.
Delete the test file with delete_file.

## If a test case fails
Report which node type (A-J) failed and the exact error.
Do not attempt to fix -- report back for analysis.

## Risk
None -- uses temporary test file, cleaned up after.
