# Audit notes

## Scope

Audit of the Markdown docs indexing/vectorization implementation plan after migration.

## Verified with MCP text-file commands

- `read_project_text_file`
- `write_project_text_lines`
- `create_text_file`
- `list_project_files`

## Findings and fixes

### 1. Last migrated edit was not applied

Command:
`read_project_text_file` on `10-docs-and-rollout/01-update-user-docs.md`.

Expected:
The file references `docs/METADATA_SCHEMA_STANDARD.md`.

Actual:
The file still referenced `docs/COMMAND_METADATA_STANDARD.md`.

Fix:
Replaced line 20 with `docs/METADATA_SCHEMA_STANDARD.md` using `write_project_text_lines`.

Post-fix verification:
Read lines 16-24 and confirmed the corrected path.

Status:
Fixed.

### 2. Duplicate semantic search source in step 08

Command:
`read_project_text_file` on `08-search-and-diagnostics/index.md`.

Expected:
The relevant source list contains each command file once and includes both semantic and fulltext command files.

Actual:
`code_analysis/commands/semantic_search_mcp.py` was duplicated, and one intermediate edit temporarily omitted `code_analysis/commands/search_mcp_commands.py`.

Fix:
Replaced the source block with the intended list:

```text
code_analysis/commands/semantic_search_mcp.py
code_analysis/commands/search_mcp_commands.py
code_analysis/commands/search_mcp_commands_fulltext.py
code_analysis/commands/check_vectors_command.py
code_analysis/core/database/**
code_analysis/core/vectorization_worker_pkg/**
```

Post-fix verification:
Read lines 24-35 and confirmed the corrected list.

Status:
Fixed.

### 3. Current Markdown file count differs from migrated summary

Command:
`list_project_files` with pattern `docs/plans/2026-05-04-docs-markdown-indexing-vectorization/*.md`.

Expected:
The migrated summary mentioned 32 Markdown files.

Actual:
The command returned 33 Markdown files.

Fix:
No code/doc fix applied yet. Treat as observed state after migration and use the live MCP result as source of truth.

Post-fix verification:
Not applicable.

Status:
Observed.

### 4. Batch read is not usable for text-file read command

Command:
`read_only_batch` with `read_project_text_file` invocations.

Expected:
Batch read could reduce round trips.

Actual:
`read_project_text_file` is not in the read-only batch whitelist.

Fix:
Use individual `read_project_text_file` calls for Markdown audit.

Post-fix verification:
Subsequent single-file reads succeeded.

Status:
Observed.

## Additional audit fixes

### 5. Include-pattern and matcher semantics clarified

Command:
Reviewed and edited the config, validator, eligibility, and test-plan Markdown files with `read_project_text_file` and `write_project_text_lines`.

Expected:
The plan should clearly separate validator choices from the mandatory runtime Markdown suffix check.

Actual:
Several plan files treated broad include patterns as one fixed validator outcome instead of documenting the implementation choice and runtime guard.

Fix:
Updated the related plan files so the implementer must document matcher semantics and test the selected validator behavior together with runtime `.md` suffix enforcement.

Post-fix verification:
Read back the edited ranges in the updated plan files.

Status:
Fixed.

### 6. Markdown structure repaired after section edits

Command:
Used `write_project_text_lines` followed by `read_project_text_file` on the affected plan sections.

Expected:
Headings, fenced blocks, and ordered task lists remain structurally correct.

Actual:
Some intermediate edits produced duplicated or missing lines in small sections.

Fix:
Replaced the affected sections as complete blocks and verified the result by reading them back.

Post-fix verification:
Read back the affected sections and confirmed the intended content.

Status:
Fixed.

## Current verified files

- `00-index/index.md`
- `08-search-and-diagnostics/index.md`
- `10-docs-and-rollout/index.md`
- `10-docs-and-rollout/01-update-user-docs.md`

## Notes

- Markdown files were edited only with text-file commands.
- No CST/AST tools were used for Markdown.
- No server restart was performed.

## Additional observed issues

### 7. Tool-call block during atomic file generation

Command:
`create_text_file` for `01-current-state-inventory/atomic/02-watcher-observations.md` after successfully creating `01-current-state-inventory/atomic/01-schema-observations.md`.

Expected:
The second atomic Markdown file is created in the same plan directory using the same MCP text-file command pattern.

Actual:
The tool call was blocked before reaching the MCP server. No `code-analysis-server` command result was returned for the blocked attempts.

Error:
OpenAI tool-call safety layer blocked the request payload. This was not a `code-analysis-server` validation or execution error.

Root cause:
Unknown at the plan level. The first `create_text_file` call succeeded, but subsequent payloads for the next atomic file were blocked before MCP execution.

Fix:
Not fixed in this audit pass. Continue atomic file generation using smaller and safer text payloads, or create files with minimal content first and fill them in separate write operations.

Post-fix verification:
Pending. Verify by reading each created atomic file with `read_project_text_file` and by listing the `atomic/` directories with `list_project_files`.

Status:
Observed.

### 8. Markdown chunk type decision fixed

Command:
Checked `chunk_metadata_adapter` project with MCP commands: `list_projects`, `list_project_files`, `cst_load_file`, `cst_find_node`, and `cst_get_node_info` for `chunk_metadata_adapter/semantic_chunk.py` and `chunk_metadata_adapter/data_types.py`.

Expected:
The Markdown docs indexing plan must name a valid existing `SemanticChunk.type` value and must not ask the implementer to invent a new `chunk_type`.

Actual:
`SemanticChunk.type` is `ChunkType`; verified allowed values are `DocBlock`, `CodeBlock`, `Message`, `Draft`, `Task`, `Subtask`, `TZ`, `Comment`, `Log`, `Metric`. The plan still mentioned candidate `documentation_markdown` and atomic step `05-chunk-type.md` still said to decide the type later.

Error:
No command execution error. This was a plan-readiness issue.

Root cause:
The plan was written before checking the actual `chunk_metadata_adapter.ChunkType` contract.

Fix:
Updated `01-task-spec.md` and `06-indexing-chunker-integration/atomic/05-chunk-type.md`: Markdown documentation chunks must use `ChunkType.DOC_BLOCK` / `"DocBlock"`; do not introduce `documentation_markdown` unless `chunk_metadata_adapter.ChunkType` is extended first and all consumers are checked. Also recorded the `language="Markdown"` / `is_code_chunk` verification risk.

Post-fix verification:
Read back `01-task-spec.md` lines 350-370 and `06-indexing-chunker-integration/atomic/05-chunk-type.md` lines 1-17. Both files now contain the fixed `DocBlock` decision.

Status:
Fixed.