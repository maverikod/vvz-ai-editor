# Step 19: tests/file_handlers/test_text_handler.py

- Add tests for plain text handler read/save/replace/delete.
- Verify .md and .txt use text handler and never call Python AST parsing.
- Verify save/replace with dry_run=true returns diff and leaves file unchanged.
- Verify replace with diff=true returns unified diff and changed line ranges.
- Verify multi-range replace validates all ranges before write.
- Verify overlapping ranges are rejected before write.
- Verify wrong suffixes .json, .yaml, .yml, .py are rejected by text handler.
- Acceptance: Markdown/text writes do not call update_file_data_atomic_batch or ast.parse.
