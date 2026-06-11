# Step 10: code_analysis/commands/universal_file_save_command.py

- Add the universal save command.
- Resolve handler by file_path before validation, backup, write, DB update, or indexing.
- Validate handler-specific payload before any side effect.
- Support dry_run=true and diff=true for handlers that can serialize before/after content.
- For text files, save full content only through text handler.
- For JSON/YAML, save structured document/tree only through structured handlers.
- For Python, save only through CST-safe handler.
- Acceptance: unsupported extension and wrong payload fail before backup/write; successful save response includes selected handler, dry_run flag, diff when requested, and write status.
