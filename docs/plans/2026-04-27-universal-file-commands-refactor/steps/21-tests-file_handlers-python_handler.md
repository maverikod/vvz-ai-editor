# Step 21: tests/file_handlers/test_python_handler.py

- Add tests for Python handler routing and CST-safe edits.
- Verify .py, .pyi, and .pyw route to python handler.
- Verify Python files never route to text handler.
- Verify Python save/replace/delete rejects raw text line payloads.
- Verify CST selector/node_id replacement supports dry_run and diff.
- Verify parse validation runs before apply.
- Verify invalid selectors fail before backup, write, DB update, or indexing.
- Acceptance: Python edits are only possible through CST-safe operations or fail before side effects.
