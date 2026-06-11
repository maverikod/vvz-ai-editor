# Step 15: code_analysis/commands/create_text_file_command.py

- Convert or align create_text_file with the universal save flow.
- Validate extension through the registry before directory creation, backup, write, DB update, or indexing.
- Allow only configured plain text suffixes for this legacy text command.
- Reject JSON/YAML/Python/source-code paths with handler-specific guidance.
- Keep create_dirs and overwrite semantics, but enforce handler validation first.
- Do not update Python AST/CST/entity indexes for plain text files.
- Acceptance: creating .md/.txt works; creating .json/.yaml/.py through create_text_file fails before file creation unless an explicit universal structured command is used.
