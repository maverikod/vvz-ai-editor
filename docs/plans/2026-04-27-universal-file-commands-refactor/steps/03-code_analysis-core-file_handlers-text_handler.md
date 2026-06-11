# Step 03: code_analysis/core/file_handlers/text_handler.py

- Move plain-text read/write behavior out of read_project_text_file_command.py and write_project_text_lines_command.py.
- Allow only configured plain text suffixes, initially .md, .txt, .rst, .adoc.
- Implement read with 1-based inclusive line ranges and explicit clamping rules.
- Implement save for full text content with dry_run and diff support.
- Implement replace for one or many ranges with atomic validation before write.
- Implement delete for line ranges or full-file delete only through explicit parameters.
- Never call Python AST/CST/entity indexing from this handler.
- Acceptance: .md write succeeds without ast.parse and without update_file_data_atomic_batch; dry_run returns diff and does not write.
