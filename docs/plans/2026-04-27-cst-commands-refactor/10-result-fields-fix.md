# Step 10 -- Add file_written and preview_only to CST edit commands

## Goal
Add file_written and preview_only fields to every CST edit command result
that currently lacks them. Use inventory from step 09.

## Requires
Step 09 completed. Edit only commands where field is missing (No in table).

## Required fields in every CST edit command result

```python
"file_written": bool,   # True if file was actually written to disk
"preview_only": bool,  # True if this was a preview/dry-run (no disk write)
```

## Change pattern for each command

Find the SuccessResult or dict construction in execute().
Add the two fields:

```python
return SuccessResult(data={
    # ... existing fields ...
    "file_written": not preview,
    "preview_only": preview,
})
```

If command has multiple return paths -- add fields to EVERY return path:
- Error early-returns: file_written=False, preview_only=False.
- Preview path: file_written=False, preview_only=True.
- Apply path: file_written=True, preview_only=False.

## One file at a time
Edit one command file, run lint_code, verify, then move to next.

## Verification after each file
1. Run lint_code -- expect 0 errors.
2. Call command with preview=true. Verify preview_only=true, file_written=false.
3. Call command with preview=false. Verify preview_only=false, file_written=true.

## Risk
Low. Additive change -- new fields in result dict.
Existing callers ignore unknown fields.
