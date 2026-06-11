# Step 04 -- query_cst empty diff fix

## Goal
Fix the bug where query_cst returns replaced=1 with empty diff
when modified_source differs from the file on disk.

## Requires
Step 03 completed. Use file path and line numbers from step 03.

## Rule
diff must be non-empty when modified_source != original file content.
If there is no change, replaced must be 0.

## Change

Find the block that produces the diff field (from step 03).

The correct logic:

```python
import difflib

original_lines = original_source.splitlines(keepends=True)
modified_lines = modified_source.splitlines(keepends=True)

diff_lines = list(difflib.unified_diff(
    original_lines,
    modified_lines,
    fromfile="original",
    tofile="modified",
))
diff = "".join(diff_lines)
```

If diff is empty and replaced > 0: set replaced = 0.
If diff is non-empty: keep replaced as-is and include diff in result.

## Verification after change

1. Run lint_code on edited file -- expect 0 errors.
2. Manual test: call query_cst with a replacement that changes one line.
   Verify diff is non-empty and contains the changed line.
3. Call query_cst with replacement identical to original.
   Verify replaced=0 and diff="".

## Risk
Low. Only affects diff field in result. Does not change file write logic.
