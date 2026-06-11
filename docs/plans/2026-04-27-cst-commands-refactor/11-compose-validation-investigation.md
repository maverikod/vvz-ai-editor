# Step 11 -- compose_cst_module validation gate investigation

## Status: DONE

## Findings

### Where validation runs
File: code_analysis/commands/compose_cst_writer.py
Function: validate_and_write_temp (line 34)

Called from: compose_cst_ops_flow.py line 164 (run_ops_mode)
Called from: compose_cst_tree_flow.py (run_tree_id_flow, not investigated but likely same)

### What validation does
validate_and_write_temp calls:
  validate_file_in_temp(validate_linter=True, validate_type_checker=True)
This runs BOTH flake8 and mypy on the entire file.

### When validation runs
- apply=True: validation runs before write (blocks on any mypy/flake8 error)
- apply=False (preview): validation does NOT run (returns before validate_and_write_temp)
  See compose_cst_ops_flow.py line ~161: if not apply: return SuccessResult(...)

### Pre-existing errors
validate_file_in_temp runs on the PATCHED source against pre-existing errors.
If the file already has mypy errors before the patch, the patch is blocked.
This is the root cause of csterr.md Problem 6.

### No existing validate_syntax_only parameter
The schema has no validate_syntax_only, skip_validation, or similar.
Only: apply (bool), create_backup (bool), return_diff (bool).

## Fix needed (step 12)
Add validate_syntax_only: bool = False parameter.
When True: call validate_file_in_temp with validate_linter=False, validate_type_checker=False.
Syntax check (ast.parse / compile) still runs.

## Files to change in step 12
1. code_analysis/commands/compose_cst_writer.py
   - add validate_syntax_only param to validate_and_write_temp signature
   - pass validate_linter=not validate_syntax_only, validate_type_checker=not validate_syntax_only

2. code_analysis/commands/compose_cst_ops_flow.py
   - add validate_syntax_only param to run_ops_mode signature
   - pass it through to validate_and_write_temp

3. code_analysis/commands/cst_compose_module_command.py
   - add validate_syntax_only to get_schema() properties
   - add validate_syntax_only param to execute() and pass to run_ops_mode
