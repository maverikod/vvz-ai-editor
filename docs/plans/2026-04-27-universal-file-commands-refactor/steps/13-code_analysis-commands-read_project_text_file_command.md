# Step 13: code_analysis/commands/read_project_text_file_command.py

- Convert this legacy command into a compatibility wrapper over universal_file_read_command.py.
- Preserve existing response shape for plain text range reads where possible.
- Stop embedding JSON special-case routing in this command; route through registry/handler instead.
- Keep Python read compatibility by delegating to python handler/get_file_lines through universal routing.
- Keep non-Python source rejection behavior through the registry.
- Acceptance: existing callers still read README.md and Python ranges, while handler selection is visible in diagnostics or metadata.
