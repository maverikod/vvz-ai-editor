# Step 17: code_analysis/commands/registration.py

- Register universal_file_read, universal_file_save, universal_file_replace, and universal_file_delete.
- Keep legacy command names registered as compatibility wrappers.
- Ensure help/metadata exposes handler-specific schemas or schema discovery links.
- Group universal commands under file_management.
- Make command descriptions explicit: text commands are not fallback editors for code or structured formats.
- Acceptance: MCP help lists universal commands; legacy commands still exist; command descriptions point models to the correct handler workflow.
