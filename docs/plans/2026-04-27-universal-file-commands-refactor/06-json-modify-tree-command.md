# Step 06: code_analysis/commands/json_modify_tree_command.py

## Goal
- Keep JSON mutation structural and tree-based.
- Prevent raw text replacement from becoming the JSON mutation path.

## Current responsibility
- Modifies a loaded JSON tree.

## Required changes
- Require a valid JSON tree/session produced by `json_load_file`.
- Validate node paths before mutating the tree.
- Reject ambiguous or missing nodes with stable diagnostics.
- Preserve formatting policy expected by `json_save_tree`.
- Ensure no filesystem write happens in this command.
- Expose enough diagnostics for the universal file router to report failed JSON mutations.

## MCP validation
- Modify a known JSON node succeeds.
- Modify a missing node fails with structured error.
- Follow-up tree read confirms only intended node changed.
- Filesystem content remains unchanged until `json_save_tree`.
