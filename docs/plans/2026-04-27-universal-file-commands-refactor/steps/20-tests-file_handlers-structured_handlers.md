# Step 20: tests/file_handlers/test_structured_handlers.py

- Add tests for JSON and YAML handlers.
- Verify .json routes to JSON handler, not text handler.
- Verify .yaml and .yml route to YAML handler, not text handler.
- Verify JSON replacement uses JSON Pointer or key_path semantics.
- Verify YAML replacement uses yaml_path semantics.
- Verify invalid JSON/YAML paths fail before backup, write, DB update, or indexing.
- Verify dry_run/diff serializes before/after content without writing.
- Acceptance: structured formats cannot be edited through raw line replacement by default.
