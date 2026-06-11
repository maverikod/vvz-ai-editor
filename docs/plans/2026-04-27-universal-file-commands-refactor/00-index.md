# Universal file commands refactor index

## Read first

1. `README.md` is the authoritative corrected plan.
2. `observations.md` is the factual log of current-code checks, reproduced bugs, and post-fix verification.
3. Files under `steps/` are implementation work packets. A performer must treat each step as incomplete unless it satisfies the Qwen 32B step contract from `README.md`.

## Current status

**2026-05-01:** Plan is **implemented**. All 23 steps completed; universal commands registered on the live server (verified via `help` MCP). Remaining: E2E MCP verification for the `Partial` items in observations.md definition-of-done checklist.

Verified facts (updated 2026-05-01):

- `code_analysis/core/file_handlers/` **exists** with 6+ files (registry, base, text_handler, json_handler, yaml_handler, python_handler, diff_support, text_ranges).
- `universal_file_read/save/replace/delete` registered and accessible via `help` on `code-analysis-server`.
- `write_project_text_lines` uses `persist_plain_text_file_metadata` only; `update_file_data_atomic_batch` removed from text write path.
- `read_project_text_file` routes via universal handler registry for supported types.

## Legacy draft files (NOT part of steps/)

Files `03-replace-file-lines-command.md`, `04-create-text-file-command.md`, `05-json-load-file-command.md`, `06-json-modify-tree-command.md` in the plan root are **stale early drafts** from before the corrected step structure. They are NOT implementation work packets. Use only files under `steps/` for execution.

1. `steps/01-code_analysis-core-file_handlers-registry.md`
2. `steps/02-code_analysis-core-file_handlers-base.md`
3. `steps/03-code_analysis-core-file_handlers-text_handler.md`
4. `steps/04-code_analysis-core-file_handlers-text_ranges.md`
5. `steps/05-code_analysis-core-file_handlers-diff_support.md`
6. `steps/06-code_analysis-core-file_handlers-json_handler.md`
7. `steps/07-code_analysis-core-file_handlers-yaml_handler.md`
8. `steps/08-code_analysis-core-file_handlers-python_handler.md`
9. `steps/09-code_analysis-commands-universal_file_read_command.md`
10. `steps/10-code_analysis-commands-universal_file_save_command.md`
11. `steps/11-code_analysis-commands-universal_file_replace_command.md`
12. `steps/12-code_analysis-commands-universal_file_delete_command.md`
13. `steps/13-code_analysis-commands-read_project_text_file_command.md`
14. `steps/14-code_analysis-commands-write_project_text_lines_command.md`
15. `steps/15-code_analysis-commands-create_text_file_command.md`
16. `steps/16-code_analysis-commands-delete_file_command.md`
17. `steps/17-code_analysis-commands-registration.md`
18. `steps/18-tests-file_handlers-registry.md`
19. `steps/19-tests-file_handlers-text_handler.md`
20. `steps/20-tests-file_handlers-structured_handlers.md`
21. `steps/21-tests-file_handlers-python_handler.md`
22. `steps/22-tests-mcp-universal_file_commands.md`
23. `steps/23-observations-and-definition-of-done.md`

## Mandatory rule for every step

Before editing source code, read the current target files with MCP commands. After every write, verify with a separate read command. Record observations in `observations.md`.

Do not edit `.venv`, `site-packages`, installed packages, or unrelated packages.

## Known plan corrections

- Public MCP command names are `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`, not ambiguous `read/save/replace/delete`.
- Text ranges are `start_line/end_line`, 1-based inclusive. Python-like slice notation is not part of the first implementation.
- `.toml` is unsupported until explicitly designed.
- `.json` writes/replaces/deletes must use JSON handler semantics, not raw text replacement.
- Python writes/replaces/deletes must use CST-safe paths.
- Text writes must not call Python parsing, entity extraction, or code-oriented indexing.