# Step 06: code_analysis/core/file_handlers/json_handler.py

- Wrap existing JSON tree workflow behind the universal handler contract.
- Delegate read to json_load_file/json tree builder semantics.
- Delegate replace/delete to json_modify_tree-style operations using JSON Pointer or key_path.
- Delegate save to json_save_tree-style validation and persistence.
- Reject plain text line ranges for .json by default.
- Support dry_run/diff by serializing before/after JSON without writing.
- Acceptance: .json resolves to json handler and cannot be edited through text handler; json replace validates the node/path before backup or write.
