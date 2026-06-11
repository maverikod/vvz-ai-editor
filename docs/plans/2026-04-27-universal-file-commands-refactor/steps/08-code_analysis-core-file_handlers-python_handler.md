# Step 08: code_analysis/core/file_handlers/python_handler.py

- Add a Python handler that delegates all writes to CST-safe workflows.
- Implement read by delegating to get_file_lines, cst_load_file, or AST/CST views depending on requested view mode.
- Implement save only through composed CST/module validation, never through raw text line write.
- Implement replace/delete via cst_selector, node_id, or safe CST operation lists.
- Require parse validation before apply unless an explicit safe exception is documented.
- Return diff for dry_run/preview without writing.
- Acceptance: .py/.pyi/.pyw never route to text handler; Python replace either uses CST successfully or fails before backup/write.
