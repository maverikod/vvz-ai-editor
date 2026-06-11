# Step 07: code_analysis/core/file_handlers/yaml_handler.py

- Add a structured YAML handler instead of treating .yaml/.yml as plain text.
- Implement read as parsed YAML document/tree with stable path addressing.
- Implement replace/delete by YAML path, not by raw line ranges.
- Preserve comments and formatting where the chosen YAML library supports it.
- Reject YAML edits through the text handler by default.
- Support dry_run/diff by serializing before/after YAML without writing.
- Acceptance: .yaml and .yml resolve to yaml handler; invalid yaml_path fails before backup, write, DB update, or indexing.
