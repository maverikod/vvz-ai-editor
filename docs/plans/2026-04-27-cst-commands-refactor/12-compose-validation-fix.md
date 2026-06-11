# Step 12 -- compose_cst_module validate_syntax_only mode

## Goal
Add validate_syntax_only=true parameter to compose_cst_module.
When true: run only syntax check (ast.parse), skip mypy and docstring validation.

## Requires
Step 11 completed. Use file path and line numbers from step 11.

## Change 1 -- add parameter to schema

In get_schema() add:

```python
"validate_syntax_only": {
    "type": "boolean",
    "description": (
        "When true: validate syntax only (ast.parse). "
        "Skip mypy and docstring checks. "
        "Use when pre-existing mypy/docstring errors block a local patch."
    ),
    "default": False,
},
```

## Change 2 -- add parameter to execute()

Add `validate_syntax_only: bool = False` to execute() signature.

## Change 3 -- gate mypy and docstring validation

Find the mypy validation call (from step 11 findings). Wrap:

```python
if not validate_syntax_only:
    # existing mypy validation call
    ...
```

Find the docstring validation call. Wrap the same way:

```python
if not validate_syntax_only:
    # existing docstring validation call
    ...
```

Syntax check (ast.parse) must always run regardless of validate_syntax_only.

## Verification after change

1. Run lint_code on edited file -- expect 0 errors.
2. Call with validate_syntax_only=false (default).
   Verify mypy still runs on a file with known errors.
3. Call with validate_syntax_only=true on a file with pre-existing mypy errors.
   Verify it succeeds if syntax is valid.
4. Call with validate_syntax_only=true and broken syntax (missing colon).
   Verify it still fails with syntax error.

## Risk
Low. New parameter, default false = existing behavior unchanged.
