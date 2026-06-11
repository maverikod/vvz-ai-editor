# Step 07 -- query_cst empty diff fix

## Goal
Fix the bug where query_cst returns replaced=1 with empty diff
when modified_source differs from the file on disk.

## Requires
Step 06 completed. Use file path and line numbers from step 06.

## Rule
diff must be non-empty when modified_source != original file content.
If there is no change, replaced must be 0.

## Change

Find the block that produces the diff field (from step 06).
Replace with correct unified diff logic:

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

if not diff:
    replaced = 0
```

## Verification after change

1. Run lint_code on edited file -- expect 0 errors.
2. Call query_cst with a replacement that changes one line.
   Verify diff is non-empty and contains the changed line.
3. Call query_cst with replacement identical to original.
   Verify replaced=0 and diff="".

## Risk
Low. Only affects diff field in result. Does not change file write logic.
