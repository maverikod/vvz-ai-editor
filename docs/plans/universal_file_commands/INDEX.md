# Plan: universal_file_* Commands — Hardening Refactor

Author: Vasiliy Zdanovskiy  
Email: vasilyvz@gmail.com  
Created: 2026-05-01  
Status: IN PROGRESS

## Context

All four `universal_file_*` commands are **already implemented and working**.
This plan hardens them: missing backup guards in text-save, missing DB rollback
paths, validation gaps, and schema inconsistencies found during audit (Step 01).

## Real architecture (after audit)

```
code_analysis/
  core/
    file_handlers/
      registry.py       — resolve_handler(), validate_supported(), HANDLER_IDS
      base.py           — BaseFileHandler, FileHandlerRequest, FileHandlerResult,
                          standard_error_result(), validate_before_side_effects(),
                          mutating_precheck()
      text_handler.py   — TextFileHandler, read_lines_range_ok(),
                          compute_replace_lines_single_range(),
                          compute_replace_lines_multi(), lines_after_delete_range(),
                          persist_plain_text_file_metadata()
      json_handler.py   — JsonFileHandler
      yaml_handler.py   — YamlFileHandler
      python_handler.py — PythonFileHandler
    backup_manager.py   — BackupManager(root_dir).create_backup(path, command, comment)
    file_lock.py        — file_lock(path)  [context manager]
    path_normalization.py — normalize_path_simple(str)
  commands/
    universal_file_read_command.py    — UniversalFileReadCommand
    universal_file_save_command.py    — UniversalFileSaveCommand
    universal_file_replace_command.py — UniversalFileReplaceCommand
    universal_file_delete_command.py  — UniversalFileDeleteCommand
    base_mcp_command.py               — BaseMCPCommand
    project_text_file_guard.py        — reject_if_write_under_project_venv()
    registration.py                   — MCP_FILE_MANAGEMENT_REGISTRY_HELP,
                                        REGISTRY_SCHEMA_DISCOVERY_SHORT
mcp_proxy_adapter/commands/result.py  — SuccessResult, ErrorResult
```

## Steps

| # | File | Title | Status |
|---|------|-------|--------|
| 01 | [steps/01_audit.md](steps/01_audit.md) | Audit — реальная архитектура | ✅ DONE |
| 02 | [steps/02_schema.md](steps/02_schema.md) | Error-code glossary | TODO |
| 03 | [steps/03_base_handler.md](steps/03_base_handler.md) | base.py — добавить error-коды и mutating guard | TODO |
| 04 | [steps/04_registry.md](steps/04_registry.md) | registry.py — валидация и .log suffix | TODO |
| 05 | [steps/05_read_handler.md](steps/05_read_handler.md) | text_handler.py — read guard | TODO |
| 06 | [steps/06_save_handler.md](steps/06_save_handler.md) | text_handler.py — save + backup + DB rollback | TODO |
| 07 | [steps/07_replace_handler.md](steps/07_replace_handler.md) | text_handler.py — replace + backup + DB rollback | TODO |
| 08 | [steps/08_delete_handler.md](steps/08_delete_handler.md) | text_handler.py — delete + backup + DB | TODO |
| 09 | [steps/09_read_command.md](steps/09_read_command.md) | universal_file_read_command.py — schema + .log | TODO |
| 10 | [steps/10_save_command.md](steps/10_save_command.md) | universal_file_save_command.py — rollback path | TODO |
| 11 | [steps/11_replace_command.md](steps/11_replace_command.md) | universal_file_replace_command.py — backup guard | TODO |
| 12 | [steps/12_delete_command.md](steps/12_delete_command.md) | universal_file_delete_command.py — file-mode guard | TODO |
| 13 | [steps/13_tests.md](steps/13_tests.md) | Tests + comprehensive_analysis | TODO |

## Key invariants (must not be broken by any step)

1. `resolve_handler()` runs **before** any backup, write, DB, or indexing call.
2. `BackupManager(root_dir).create_backup(path, command, comment)` is called before
   every mutating filesystem write on an existing file unless `dry_run=True`.
3. If `create_backup()` returns falsy — abort with `code="BACKUP_REQUIRED"`.
4. `persist_plain_text_file_metadata()` runs **after** successful write; if it fails,
   the backup is restored via `bm.restore_file(rel, backup_uuid)`.
5. All `execute()` methods return `SuccessResult | ErrorResult` — never raise.
6. Python (`.py/.pyi/.pyw`) files are CST-only — `universal_file_save` routes them
   to `PythonFileHandler`, never raw text write.

## MCP tools for this plan

```text
read_project_text_file  — read any file by relative path + line range
cst_load_file           — load .py into CST tree
cst_modify_tree         — modify tree (use code_lines array for multi-line)
cst_save_tree           — atomic save with backup + DB update
compose_cst_module      — single-op CST patch (preview: apply=false first)
lint_code / format_code / type_check_code — post-edit quality checks
comprehensive_analysis  — full project quality scan (use_queue=True)
```