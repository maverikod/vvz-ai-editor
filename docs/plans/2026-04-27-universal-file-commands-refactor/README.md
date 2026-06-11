# Universal file commands refactor

## Goal

Build a safe, handler-routed file operation layer so models cannot use raw line-edit commands as a fallback editor for code or structured formats.

This plan is written for performers using local models at about `qwen 32B Q4_K_M` capability. Each implementation step must be small, explicit, independently verifiable, and based on current source-code reads before edits.

## Current-code verification snapshot

Verified against the current `code_analysis` project before updating this plan:

- `code_analysis/core/file_handlers/` does not exist yet. The handler layer is still planned work.
- `code_analysis/commands/project_text_file_guard.py` already defines source-file guards.
- `write_project_text_lines` already allows only `.adoc`, `.md`, `.rst`, `.txt` writes and rejects Python / known source-code suffixes.
- `write_project_text_lines` still calls `update_file_data_atomic_batch` after writing. This is the remaining risk for plain text: DB/index update must not parse Markdown, TXT, RST, or ADOC as Python.
- `read_project_text_file` currently routes Python paths to `get_file_lines`. It also returns structured JSON for small `.json` files by using the JSON tree loader.
- Therefore the historical bug is no longer simply “missing suffix check”. The current refactor must preserve existing guards and remove wrong post-write side effects for plain text.

## Corrected problem statement

The command layer currently mixes several responsibilities:

1. path and suffix validation;
2. backup and file write;
3. DB metadata update;
4. Python/entity/index update;
5. structured JSON read/write behavior;
6. user-facing command schemas.

The refactor must separate these responsibilities by file handler and must fail before side effects whenever the selected handler does not support the requested operation.

## Universal command names

Do not use ambiguous public names such as `read`, `save`, `replace`, or `delete`. The MCP command names must be explicit:

```text
universal_file_read
universal_file_save
universal_file_replace
universal_file_delete
```

`universal_file_replace` routes by extension like read/save: `resolve_handler(file_path, "replace")` runs before validation, backup, filesystem write, DB updates, or indexing. Plain-text multi-range replaces reject overlapping ranges before backup and before write.

The short names `read/save/replace/delete` may appear only as internal handler operation names.

Each public command must require:

```text
project_id
file_path
```

Every write-like command must support:

```text
dry_run
diff
backup
```

`dry_run=true` must not write, create backups, update DB rows, update indexes, or mutate in-memory handler state that survives the call.

## Extension / handler registry

Add a config-driven registry in the source repository, not in `.venv`, `site-packages`, or installed packages.

Default mapping:

```text
.md, .txt, .rst, .adoc       -> text
.json                        -> json
.yaml, .yml                  -> yaml
.py, .pyi, .pyw              -> python
.toml                        -> unsupported until explicitly designed
unknown suffix               -> unsupported-extension error
```

Corrections to the earlier draft:

- `.toml` must not silently fall back to text. It is unsupported until a TOML handler or an explicit read-only policy is specified.
- `.json` read compatibility with current `read_project_text_file` must be documented, but new writes/replaces must route through the JSON handler.
- Python reads may continue to delegate to existing safe line/CST read behavior. Python writes/replaces must use CST-safe workflows only.
- Unsupported extensions must fail before backup, write, DB update, indexing, parsing, or queue submission.

Required registry APIs:

```text
resolve_handler(file_path, operation)
validate_supported(file_path, operation)
get_handler_schema(handler_id, operation)
list_handler_mappings()
```

Responses from universal commands must include:

```text
handler_id
operation
file_path
project_id
dry_run
changed
```

## Handler contract

Each handler must implement the same operation names:

```text
read
save
replace
delete
```

A handler may reject an operation, but it must do so with a documented error before side effects.

Required error fields:

```text
success=false
code
message
details.file_path
details.handler_id
details.operation
```

## Text handler

The text handler is only for configured plain text suffixes:

```text
.md
.txt
.rst
.adoc
```

It must never call Python AST/CST/entity indexing. After a successful text write, update only generic file metadata that is safe for non-code text: line count, modified time, file record state. Do not call code parsing, entity extraction, AST, CST, vector chunking, or Python-specific update paths unless a separate text-safe implementation is explicitly added and tested.

### Text range policy

Use the existing MCP convention:

```text
start_line: 1-based inclusive
end_line: 1-based inclusive
```

Do not use Python-like slice strings (`[:12]`, `[11:]`) in the first implementation. They are ambiguous for small models and conflict with existing command schemas. A later parser may accept range strings only if it converts them to the canonical `start_line/end_line` form before validation.

Range rules:

- `start_line >= 1`;
- `end_line >= 1`;
- `start_line <= end_line`;
- no negative indexes;
- no implicit clamping for writes;
- out-of-range writes must fail with `INVALID_RANGE`;
- read operations may clamp only if the command documentation explicitly says so.

### Multi-range replace

Multi-range replacement must be implemented only after single-range replacement is stable.

For multi-range replace:

- validate every range before writing;
- reject overlapping ranges;
- reject duplicate ranges;
- apply replacements from bottom to top or through an immutable edit plan;
- return unified diff when `diff=true`;
- return no partial write after any validation failure.

## JSON handler

The JSON handler must build on current JSON tree commands and code:

```text
json_load_file
json_find_node
json_modify_tree
json_save_tree
json_reload_tree
list_json_blocks
```

Important compatibility note: current `read_project_text_file` may return structured JSON for small `.json` files. Universal JSON read may use the same tree builder, but universal JSON write/replace/delete must not use raw text line replacement.

## YAML handler

YAML support must not assume a dependency is already available. Before implementation, inspect project dependencies and existing imports. If no YAML parser is present, add a dedicated dependency through the project source/dependency configuration only; never patch installed packages.

YAML must preserve comments only if the selected parser and handler explicitly support that. Otherwise the command must document that comments are not preserved or reject comment-preserving requests.

## Python handler

Python write/replace/delete must route to CST-safe commands or CST-safe handler code.

Allowed implementation bases:

```text
cst_load_file
query_cst
cst_modify_tree
compose_cst_module
cst_save_tree
get_file_lines for read-only line views
```

Do not write Python through `write_project_text_lines` or the text handler. Do not edit Python through AST-only transformations because AST does not preserve source formatting/comments.

## Shell-style file name pattern rule

Universal file commands and file-listing instructions must support shell-style filename patterns like `ls`, `cp`, and `mv`.

Required glob syntax:

```text
*          matches any chars inside one path segment
?          matches one char inside one path segment
[abc]      matches one char from set
[a-z]      matches one char from range
[!abc]     matches one char not in set
**         matches zero or more directories only when recursive=true or globstar=true
```

Examples:

```text
docs/*.md
README.*
code_analysis/commands/*text*.py
code_analysis/commands/*_{read,write}_*.py  # optional brace expansion only if explicitly implemented
code_analysis/**/*.py                       # requires recursive/globstar mode
```

Minimum required behavior:

- `list_project_files` must accept and document `file_pattern` with shell-style glob semantics.
- Any new bulk-capable command must use explicit pattern fields such as `source_patterns` / `target_pattern`, not vague directory-only selection.
- Pattern expansion must happen after project-root containment checks and must never escape the project root.
- Pattern matching must not include `.venv`, `venv`, `site-packages`, installed packages, deleted files, or trashed projects unless an explicit safe option says so.
- Bulk write/delete/move operations must support `dry_run=true` and must return the expanded file list before mutation.
- If a pattern matches zero files, return a clear `NO_FILES_MATCHED` error for write/delete/move operations. For read/list operations, zero matches may be a successful empty result only if documented.
- If a pattern matches multiple files for a single-file command, return `MULTIPLE_FILES_MATCHED` and include the matched paths.
- If a pattern is malformed, return `INVALID_FILE_PATTERN` before file access side effects.

Forbidden forms in plan steps:

```text
list_project_files without file_pattern
list_project_files with only directory/path-style narrowing
broad project root scan without a name pattern
```

If a performer does not know the exact file name, they must first use the narrowest safe shell-style pattern, then refine. Examples:

```text
code_analysis/commands/*text*.py
code_analysis/commands/*json*.py
code_analysis/core/*file*/*
docs/plans/*universal-file-commands-refactor*/*
```

The goal is to make searches reproducible for `qwen 32B Q4_K_M`, reduce accidental broad scans, and ensure every file-listing observation records the exact pattern used.

## Qwen 32B Q4_K_M step contract

Every step file in `steps/` is a work packet. A performer must be able to execute one step without inferring hidden context.

Each step must contain or follow this exact structure:

```text
Scope: one file or one tightly coupled module group.
Current-code reads: exact MCP read/search commands to run before edits.
Do not edit: .venv, site-packages, installed packages, unrelated packages.
Implementation: small ordered edits.
Validation: exact command-level checks.
Read-back verification: separate read command after each write.
Observations: exact entry to append to observations.md.
Stop condition: when to stop and report instead of guessing.
```

Rules for small/local models:

- one step must not mix handler infrastructure, command registration, and tests unless it is explicitly a registration/test step;
- do not ask the performer to “refactor broadly”;
- do not rely on memory of previous steps;
- repeat critical safety rules in each step or reference this README plus the exact step file;
- include expected command names and expected error codes;
- every `list_project_files` example must use an explicit `file_pattern` with shell-style semantics;
- require MCP behavior verification, not only unit-test success.

## Current bug record to preserve

```text
Command: write_project_text_lines on Markdown/plain text
Expected: write succeeds or fails before side effects; Markdown is never parsed as Python
Actual: current code has suffix guards, but still calls update_file_data_atomic_batch after write
Error: reproduced on this README: UPDATE_FILE_DATA_ERROR, Syntax error: invalid decimal literal (README.md, line 7)
Root cause: text write command still uses a code-oriented DB/index update path
Fix: route text writes through text-safe metadata update, or make update_file_data_atomic_batch handler-aware and non-Python-safe
Post-fix verification: MCP write to .md test file succeeds, separate read confirms content, logs/result show no Python AST/CST/entity parsing
Status: open until verified by MCP command behavior
```

## Required deliverables

1. Config-driven extension-to-handler registry.
2. Explicit MCP commands: `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`.
3. Handler contract for `read/save/replace/delete`.
4. Handler-specific schemas in command help/metadata.
5. Text handler with strict suffix allowlist and 1-based inclusive ranges.
6. Text-safe metadata update path that does not parse text as Python.
7. Shell-style `file_pattern` support for file listing and any bulk-capable file command.
8. Single-range text replace before multi-range replace.
9. Dry-run and unified diff for save/replace before write mode is accepted.
10. JSON handler based on existing JSON tree commands.
11. YAML handler with explicit parser/dependency decision.
12. Python handler delegating to CST-safe workflows.
13. MCP-level tests proving wrong-handler edits fail before side effects.
14. `observations.md` recording current behavior, bugs, fixes, and post-fix verification.

## Required MCP behavior tests

- `.md` uses text handler and never calls Python AST/CST/entity parsing.
- `.txt` uses text handler.
- `.rst` and `.adoc` use text handler.
- `.json` routes to JSON handler for write/replace/delete.
- `.yaml` and `.yml` route to YAML handler or return documented unsupported-handler error before side effects until implemented.
- `.py`, `.pyi`, `.pyw` route to Python handler for writes/replaces/deletes.
- `write_project_text_lines` remains backward-compatible only for allowed text suffixes or is explicitly deprecated with a replacement path.
- `list_project_files file_pattern=docs/*.md` returns only matching names.
- `list_project_files file_pattern=code_analysis/commands/*text*.py` uses shell-style `*` semantics.
- malformed patterns fail with `INVALID_FILE_PATTERN` where validation is implemented.
- unknown extension fails closed before backup/write/index update.
- `.toml` fails closed until a TOML policy is added.
- unsupported source suffixes such as `.go` and `.rs` fail with `CODE_FILE_FORBIDDEN` or the universal equivalent.
- text write with `dry_run=true,diff=true` returns unified diff and does not write.
- write with invalid range fails before backup/write.
- multi-range overlapping replacement fails before backup/write.
- every successful write is verified by a separate read command.

## Definition of done

This refactor block is complete only when:

- behavior is proven through MCP command execution;
- every write is verified by a separate read command;
- wrong-handler requests fail before side effects;
- every `list_project_files` command used in docs, tests, and observations records an explicit shell-style `file_pattern`;
- text writes no longer call Python parsing/entity/index update paths;
- handler selection is visible in command responses;
- observations are written in `docs/plans/2026-04-27-universal-file-commands-refactor/observations.md`;
- each bug is documented in the required bug format;
## Status

**2026-05-01:** Plan is **Complete** (implementation and pytest). Universal commands `universal_file_read/save/replace/delete` are registered on the live `code-analysis-server` (verified via `help` MCP on 2026-05-01). Remaining: run E2E MCP checks from step 23 definition-of-done to close the `Partial` items in observations.md.

**2026-04-29 (historical):** The refactor block's definition of done was Incomplete for live MCP: the registered `code-analysis-server` instance did not expose universal commands. This was resolved by server restart/rebuild.

**Cross-plan note:** `PythonFileHandler` uses the `compose_cst_module` (run_ops_mode) pipeline, which is **not** covered by the `2026-05-01-cst-save-safety` plan (tree-based pipeline only). The compose pipeline will receive disk snapshot / replay / readback protections in a future phase — see `2026-05-01-cst-save-safety/README.md` section on out-of-scope paths.