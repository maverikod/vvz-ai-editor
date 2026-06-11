# Step 04: code_analysis/commands/create_text_file_command.py

## Goal
- Make text-file creation explicit and safe.
- Prevent `create_text_file` from becoming a bypass for structured/code file creation.

## Current responsibility
- Creates a project-relative text file with optional parent directory creation.

## Required changes
- Apply the same centralized file-type guard used by text read/replace commands.
- Allow creation only for configured plain-text suffixes:
  - `.md`
  - `.txt`
  - `.rst`
  - `.adoc`
- Reject structured/code suffixes before file creation:
  - `.json`
  - `.yaml`
  - `.yml`
  - `.py`
  - `.pyi`
  - `.pyw`
- Reject unknown suffixes fail-closed.
- Validate parent path and file type before creating directories when possible.
- Keep `overwrite=false` as the safe default.

## MCP validation
- Create `.md` succeeds.
- Create `.txt` succeeds.
- Create `.json` fails and no file is created.
- Create `.py` fails and no file is created.
- Unknown extension fails and no file is created.
