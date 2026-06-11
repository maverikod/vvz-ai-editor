# 02. Add generator and CLI options

Parent step: [index.md](index.md)
Main task: [../01-task-spec.md](../01-task-spec.md)

## Goal

Add safe config generation support for `code_analysis.docs_indexing`.

## Inspect first

- `code_analysis/core/config_generator.py`
- `code_analysis/cli/config_cli_generate.py`
- `code_analysis/cli/config_cli_parser.py`
- `code_analysis/cli/config_cli_commands.py`

## Actions

1. Find existing code_analysis generator arguments.
2. Add docs indexing arguments.
3. Ensure generated defaults are disabled.
4. Add CLI help text that says `.md` only.
5. Add CLI help text that says vectorization is off by default.
6. Update or add generator tests.

## Output

Code changes plus notes in:

```text
generator-change-notes.md
cli-change-notes.md
```

## Verification

Generated config must contain disabled docs indexing or equivalent safe defaults.
