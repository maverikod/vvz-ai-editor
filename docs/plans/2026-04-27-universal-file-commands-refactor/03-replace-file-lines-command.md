# Step 03: code_analysis/commands/replace_file_lines_command.py

## Goal
- Restrict line-based replace operations to configured plain-text files only.
- Prevent JSON, YAML, and Python files from being edited through raw line replacement.

## Current responsibility
- Performs line-range replacement in project files.
- Can currently be used as a generic text mutation path.

## Required changes
- Call `project_text_file_guard` before any read, diff, backup, write, indexing, or DB update.
- Allow only configured plain-text suffixes:
  - `.md`
  - `.txt`
  - `.rst`
  - `.adoc`
- Reject structured/code suffixes:
  - `.json`
  - `.yaml`
  - `.yml`
  - `.py`
  - `.pyi`
  - `.pyw`
- Validate all requested ranges before modifying content.
- Reject overlapping ranges, or document and test exact ordering semantics.
- Preserve dry-run behavior with no side effects.
- Return unified diff when requested.

## MCP validation
- Replace lines in `.md` succeeds.
- Replace lines in `.txt` succeeds.
- Replace lines in `.json` fails before backup/write/index updates.
- Replace lines in `.py` fails before backup/write/index updates.
- Overlapping ranges fail before writing.
- Dry-run returns diff and a follow-up read confirms no change.
