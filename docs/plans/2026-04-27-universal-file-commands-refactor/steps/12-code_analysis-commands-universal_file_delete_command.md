# Step 12: code_analysis/commands/universal_file_delete_command.py

- Add the universal delete command.
- Resolve handler by file_path before validation, backup, write, DB update, indexing, or trash operations.
- Require explicit delete mode: file, range, node, yaml_path, json_pointer, cst_selector, or node_id.
- Text: delete line ranges or full file only with explicit mode.
- JSON/YAML: delete structured nodes by path only.
- Python: delete only through CST-safe selectors or node ids.
- Support dry_run=true and diff=true where content remains serializable.
- Acceptance: accidental full-file delete is impossible without explicit mode; wrong-handler delete fails before side effects.
