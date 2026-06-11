# Code Quality Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for formatting, linting, and type checking (Black, Flake8, mypy).

## Commands → File Mapping

| MCP Command Name | Class              | Source File (single module)     |
|------------------|--------------------|----------------------------------|
| format_code      | FormatCodeCommand  | `commands/code_quality_commands.py`|
| lint_code        | LintCodeCommand    | (same)                           |
| type_check_code  | TypeCheckCodeCommand| (same)                          |

These commands inherit from `Command` (not BaseMCPCommand). Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
