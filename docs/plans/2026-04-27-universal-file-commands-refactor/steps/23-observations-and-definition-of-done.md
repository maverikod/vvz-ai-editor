# Step 23: observations and definition of done

## Scope

Finalize the refactor block only after behavior is verified through MCP commands and observations are complete.

Owned files:

- `docs/plans/2026-04-27-universal-file-commands-refactor/observations.md`
- final status notes for this plan only

Do not edit source code in this step.

## Current-code reads before edits

Run these MCP reads first:

```text
read_project_text_file docs/plans/2026-04-27-universal-file-commands-refactor/README.md lines 1-340
read_project_text_file docs/plans/2026-04-27-universal-file-commands-refactor/00-index.md lines 1-220
read_project_text_file docs/plans/2026-04-27-universal-file-commands-refactor/observations.md lines 1-260
read_project_text_file docs/plans/2026-04-27-universal-file-commands-refactor/steps/22-tests-mcp-universal_file_commands.md lines 1-260
```

## Required final MCP checks

Run the applicable MCP commands and inspect inner command results, not only proxy/queue status.

Minimum command set:

```text
list_projects include_deleted=true
list_project_files for universal command source files
help universal_file_read
help universal_file_save
help universal_file_replace
help universal_file_delete
help write_project_text_lines
list_trashed_projects
```

If queue is used for any command, check:

```text
queue_get_job_status
result.command.result.success
```

`status=completed` and `progress=100` do not prove command success.

## Definition of done

The refactor block is done only when all statements below are true:

1. `code_analysis/core/file_handlers/registry.py` exists and is verified by read-back.
2. Handler mapping is config-driven or explicitly centralized, not scattered in command bodies.
3. Public MCP command names are explicit:

```text
universal_file_read
universal_file_save
universal_file_replace
universal_file_delete
```

4. Universal command help/metadata exposes selected handler behavior or handler-specific schemas.
5. Universal command responses include:

```text
handler_id
operation
project_id
file_path
```

6. Unsupported extensions fail before backup/write/DB update/indexing/parsing.
7. `.toml` is unsupported until a TOML policy is explicitly implemented.
8. Text handler supports only `.md`, `.txt`, `.rst`, `.adoc` unless config is deliberately changed and documented.
9. Text write/replace uses 1-based inclusive `start_line/end_line`, not Python-like slice strings in the first implementation.
10. Text writes do not call Python AST/CST/entity extraction or code-oriented indexing.
11. `write_project_text_lines` no longer returns `UPDATE_FILE_DATA_ERROR` for Markdown/plain text.
12. JSON write/replace/delete uses JSON handler semantics, not raw text line replacement.
13. YAML handler behavior is implemented or returns documented unsupported-handler errors before side effects.
14. Python writes/replaces/deletes route to CST-safe behavior or documented unsupported-operation errors before side effects.
15. Dry-run for write-like commands does not create backups, write files, update DB rows, update indexes, or mutate lasting handler state.
16. Diff output is returned for `diff=true` where supported.
17. Every successful write-like MCP test has a separate read-back verification.
18. Every bug is documented in observations with the required format:

```text
Command:
Expected:
Actual:
Error:
Root cause:
Fix:
Post-fix verification:
Status:
```

19. Destructive tests used only dedicated test projects or temporary test data, never `vast_srv`.
20. All changed plan and source files were re-read after modification.

## Final observations format

Append a final block to `observations.md`:

```text
## Final verification YYYY-MM-DD

Commands run:
- ...

Passing behavior:
- ...

Remaining limitations:
- ...

Bugs fixed:
- ...

Bugs still open:
- ...

Definition of done status:
Complete | Incomplete
```

## Stop condition

Mark the block incomplete if any required MCP behavior is unverified, if any write lacks read-back verification, or if a proxy/queue envelope success hides an inner command failure.
