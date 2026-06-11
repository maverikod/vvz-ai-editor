# Step 11: code_analysis/commands/universal_file_replace_command.py

- Add the universal replace command.
- Resolve handler by file_path before validation, backup, write, DB update, or indexing.
- Expose handler-specific replace schemas.
- Text: accept one or many validated line ranges.
- JSON: accept JSON Pointer/key_path node replacement.
- YAML: accept yaml_path replacement.
- Python: accept CST selector/node_id/range-safe replacement only.
- Support dry_run=true and diff=true.
- Reject overlapping text ranges before backup and before write (multi-range); document in plan README.
- Acceptance: no partial replacement occurs after any validation failure; response includes selected handler and changed ranges/nodes.
