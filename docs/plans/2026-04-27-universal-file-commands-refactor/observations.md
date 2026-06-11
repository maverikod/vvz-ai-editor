# Observations: universal file commands refactor

## 2026-04-28 plan audit against current code

### Current code reads

Verified through MCP commands against project `code_analysis` with project_id `8772a086-688d-4198-a0c4-f03817cc0e6c`.

Read files:

- `code_analysis/commands/project_text_file_guard.py`
- `code_analysis/commands/write_project_text_lines_command.py`
- `code_analysis/commands/read_project_text_file_command.py`
- `code_analysis/commands/file_management_mcp_commands/create_text_file.py`

List checks:

- `code_analysis/core/file_handlers/*` returned no files.
- `docs/plans/2026-04-27-universal-file-commands-refactor/steps/*.md` returned 23 step files.

### Findings

1. The plan previously implied that strict suffix checks still needed to be added to `write_project_text_lines`. Current code already has a strict allowlist for `.adoc`, `.md`, `.rst`, `.txt` and rejects Python / known source-code suffixes.
2. The remaining defect is not the absence of suffix checks. The remaining defect is that `write_project_text_lines` still calls `update_file_data_atomic_batch` after a text write.
3. `read_project_text_file` is not a simple plain-text reader for every suffix. It routes Python paths to `get_file_lines` and returns structured JSON for small `.json` files.
4. The earlier plan used ambiguous public command names `read/save/replace/delete`. The corrected plan requires explicit MCP command names: `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`.
5. The earlier plan suggested Python-like range strings for text edits. The corrected plan uses existing MCP convention: `start_line` and `end_line`, 1-based inclusive.
6. The earlier plan left `.toml` ambiguous. The corrected plan marks `.toml` unsupported until a TOML policy or handler is explicitly designed.
7. The existing step files are very short and are not yet sufficient for a `qwen 32B Q4_K_M` performer unless combined with the corrected README step contract.

## Reproduced bug

Command:
`write_project_text_lines` on `docs/plans/2026-04-27-universal-file-commands-refactor/README.md`

Expected:
Markdown/plain text write either succeeds safely or fails before side effects. Markdown must never be parsed as Python.

Actual:
The command returned success at proxy envelope level but command result success was false.

Error:
`UPDATE_FILE_DATA_ERROR`: `Failed to update file data: Syntax error: invalid decimal literal (README.md, line 7)`

Root cause:
`write_project_text_lines` writes allowed text suffixes, then calls `update_file_data_atomic_batch`, which is a code-oriented update path and can parse non-Python text as Python.

Fix:
Route text writes through a text-safe metadata update path, or make the file-data update layer handler-aware so non-Python text never enters Python AST/CST/entity parsing.

Post-fix verification:
Required after implementation:

1. run MCP write on a test `.md` file;
2. confirm `result.success=true` inside command result, not only queue/proxy status;
3. run a separate `read_project_text_file` command and confirm content changed;
4. confirm result/logs show no Python AST/CST/entity parsing path for Markdown;
5. record final behavior here.

Status:
Fixed — see **Step: 14 write_project_text_lines** (`persist_plain_text_file_metadata` path; no `update_file_data_atomic_batch` on plain-text writes).

## Step: 01 registry

Current code reads:

- `list_project_files` with `file_pattern=code_analysis/core/file_handlers/*`, `python_only=false`: returned 6 files (`__init__.py`, `base.py`, `diff_support.py`, `registry.py`, `text_handler.py`, `text_ranges.py`). **`code_analysis/core/file_handlers/` exists** (plan audit snapshot that listed zero files is stale for this workspace).
- `read_project_text_file` for `code_analysis/commands/project_text_file_guard.py` (lines 1–220), `write_project_text_lines_command.py` (1–120), `read_project_text_file_command.py` (1–260): **MCP failed** with `VALIDATION_ERROR` — *Watch directory path is NULL for watch_dir_id 550e8400-e29b-41d4-a716-446655440001*. Same error when verifying `registry.py` via MCP after implementation.
- `fulltext_search` for `FORBIDDEN_PYTHON_SOURCE_SUFFIXES` and `PLAIN_TEXT_WRITE_SUFFIXES`: **MCP succeeded** with `count: 0` each; codebase grep confirms definitions in `project_text_file_guard.py` / `write_project_text_lines_command.py`.

Implementation summary:

- Registry module already implemented `resolve_handler`, `validate_supported`, `get_handler_schema`, `list_handler_mappings` with handler ids `text`, `json`, `yaml`, `python`, default suffix map and operations `read` / `save` / `replace` / `delete`; `.toml` unmapped; unknown suffixes and bad operations raise `RegistryError` with required `UNSUPPORTED_FILE_EXTENSION` / `UNSUPPORTED_FILE_OPERATION` detail keys.
- Added **`tests/test_file_handlers_registry.py`** (routing and error-detail assertions only; no handlers/commands).
- **`registry.py`**: removed unused `mypy` `# type: ignore[arg-type]` comments in `get_handler_schema` so checks pass.

Validation commands:

- `pytest tests/test_file_handlers_registry.py -v` → **15 passed**.
- `black` / `flake8` / `mypy` on `code_analysis/core/file_handlers/registry.py` and `tests/test_file_handlers_registry.py` → **no issues**.

Read-back verification:

- **Local** read of `code_analysis/core/file_handlers/registry.py` confirms updated `get_handler_schema` blocks (no unused ignores) and routing logic.
- MCP `read_project_text_file` **not usable** for this project_id in current server DB state (watch dir path NULL).

Status:

**Complete** (step 01 scope).

## Step: 02 base

Current code reads:

- `base.py`: prior minimal request/result and string-based `validate_before_side_effects`; replaced with full contract backed up via BackupManager (`old_code`, command `plan_step02_file_handlers_base`).

Implementation summary:

- **`code_analysis/core/file_handlers/base.py`**: Canonical error constants (`unsupported_operation`, `unsupported_extension`, `validation_failed`, `side_effect_blocked`); `standard_error_result` for failures including required detail keys (`file_path`, `handler_id`, `operation`); `validate_before_side_effects` → `Optional[FileHandlerResult]` with `validation_failed`; `BaseFileHandler` ABC (`read/save/replace/delete`, `json_schema_for`, `operation_availability`, `registration_readiness`, `mutating_precheck`). Uses registry `HANDLER_IDS` / `OPERATIONS`.
- **`code_analysis/core/file_handlers/__init__.py`**: Re-exports handler contract symbols with registry APIs.
- **`tests/test_file_handlers_base.py`**: Minimal contract tests (`_MinimalHandler` + `get_handler_schema`).

Validation commands:

- `black`, `flake8`, `mypy` on `base.py`, `file_handlers/__init__.py`, `test_file_handlers_base.py` → clean.
- `pytest tests/test_file_handlers_base.py tests/test_file_handlers_registry.py -v` → **19 passed**.

Status:

**Complete** (step 02 scope only).

## Plan-file update method

Because `write_project_text_lines` currently reproduces the Markdown update bug, plan markdown files were updated with `create_text_file` using `overwrite=true`. This command was verified in current code to write files on disk only and avoid DB/index sync.

Every changed plan file must still be verified with a separate `read_project_text_file` command.

## Step: 03 text_handler

Current code reads (before implementation):

- `read_project_text_file_command.py`, `write_project_text_lines_command.py`, `registry.py`, `base.py`, `text_handler.py` (partial helpers).

Implementation summary:

- **`text_handler.py`**: Plain-text suffix allowlist `.md`, `.txt`, `.rst`, `.adoc`; `read_lines_range_ok` (1-based inclusive reads with clamp per registry/read docs); `compute_replace_lines_single_range` / `compute_replace_lines_multi` (atomic validation via existing `merge_adjacent_ranges_for_replace`; overlaps rejected); `join_lines_unix`; `save_preview` / `unified_diff_for_edit`; `lines_after_delete_range`; `persist_plain_text_file_metadata` (updates `files` row only, `has_docstring=False`, **no** `update_file_data_atomic_batch`, **no** Python AST/CST/index paths); **`TextFileHandler`** extends `BaseFileHandler` with `read` / `save` / `replace` / `delete` using `request.extra` (paths resolved by callers).
- **`write_project_text_lines_command.py`**: Delegates range validation + replacement to text handler helpers; strict ranges (no clamp); filesystem write + **`persist_plain_text_file_metadata`** only; **`update_file_data_atomic_batch` removed**.
- **`read_project_text_file_command.py`**: Registered plain-text suffixes route through **`read_lines_range_ok`** (same clamp semantics as before for `.md`/`.txt`/`.rst`/`.adoc`); other non-Python/non-structured paths unchanged.
- **`file_handlers/__init__.py`**: Exports `TEXT_SUFFIXES`, `TextFileHandler`, `persist_plain_text_file_metadata`, `read_lines_range_ok`.

Validation commands:

- `pytest tests/test_text_handler.py tests/test_project_text_file_commands.py tests/test_file_handlers_registry.py tests/test_file_handlers_base.py -v` → **59 passed**.
- `black` / `flake8` on touched paths → clean.
- `mypy` with **`--follow-imports=silent`** on touched modules and `tests/test_text_handler.py` → clean.

Read-back verification:

- Local read confirms handler persistence helper and command delegation without batch import.

Status:

**Complete** (step 03 scope only).

## Step: 04 text_ranges

- Implemented bracket parser (`[n]`, `[a,b]`, `[:b]`, `[a:]`) with 1-based inclusive semantics; negative indices rejected; `[a:]` requires `total_lines`; colon closed form rejected in favor of comma; `parse_bracket_ranges` enforces non-overlap.
- Added `tests/test_text_ranges.py`; `black` / `flake8` / `mypy --follow-imports=silent` on `text_ranges.py` and test file; `pytest tests/test_text_ranges.py tests/test_text_handler.py` → 18 passed.
- Backups: `BackupManager.create_backup` for `text_ranges.py` and `observations.md` (command `plan_step04_text_ranges`).

## Step: 05 diff_support

- **`diff_support.py`**: `diff_data_for_text_mutation` / `changed_line_ranges_for_text` / `merge_adjacent_changed_ranges`; stable `data` keys `diff` (unified) and `changed_line_ranges` (1-based inclusive spans in **after** text, JSON as `[start, end]` pairs); `context_lines` via `unified_diff_text` / `diff_data_for_text_mutation`.
- **`text_handler.py`**: `save` / `replace` / range `delete` use `save_preview` → single diff path for dry_run and apply; `extra.diff_context_lines` (default 3, clamped ≥ 0).
- **`tests/test_diff_support.py`**: diff shape, context sizing, handler dry_run leaves file unchanged; apply vs dry_run same `diff` and `changed_line_ranges` when `diff=True`.
- Backups: `plan_step05_diff_support` for `diff_support.py`, `text_handler.py`, `observations.md`.

## Step: 06 json_handler

- Implemented **`code_analysis/core/file_handlers/json_handler.py`**: `JsonFileHandler` delegates read to `build_tree_from_data` (no session registry), replace/delete structured ops to `load_file_to_tree` + `modify_tree` + `save_json_tree_to_file` (validation via `modify_tree` before save/backup); rejects plain-text line-range keys in `extra`; dry_run serializes before/after without write; full file delete uses `BackupManager` when `backup=True`; **`file_handlers/__init__.py`** exports JSON symbols.
- Added **`tests/test_json_handler.py`**: routing `.json` → json handler, text handler rejects `.json`, JSON read rejects line ranges, invalid node replace does not call save and leaves file unchanged, dry_run replace unchanged on disk.

Validation: `black` / `flake8` / `mypy --follow-imports=silent` on `json_handler.py`, `__init__.py`, `test_json_handler.py`; `pytest tests/test_json_handler.py -v` → 7 passed.

## Step: 07 yaml_handler

- **`code_analysis/core/file_handlers/yaml_handler.py`**: `YamlFileHandler` with JSON Pointer (`yaml_path`) addressing, `read` returns `document` + `paths`, rejects plain-text line keys; `replace`/`delete` validate path before `BackupManager`; `save` full-document; PyYAML round-trip **does not preserve comments/formatting** (documented in module docstring). Optional `persist_plain_text_file_metadata` when `extra.database` + `normalized_path`. **Dependency:** `pyyaml` already in `pyproject.toml` (no change).
- **`file_handlers/__init__.py`**: exports `YAML_SUFFIXES`, `YamlFileHandler`, `ensure_yaml_suffix`, `is_registered_yaml_suffix`.
- **`tests/test_yaml_handler.py`**: routing `.yaml`/`.yml`, text handler rejects `.yaml`, read rejects line ranges, invalid pointer / invalid traversal fails before backup, dry_run unchanged on disk, registration schema ready.

Validation: `black` / `flake8` / `mypy --follow-imports=silent` on `yaml_handler.py`, `__init__.py`, `test_yaml_handler.py`; `pytest tests/test_yaml_handler.py -v` → 13 passed.

## Step: 08 python_handler

- **`python_handler.py`**: `PythonFileHandler` — read (`lines` view via `read_python_lines_payload` / healthy-parse gate; `cst` view needs `tree_id`); `save` builds CST ops (`module` for new/empty files, full-span `range` when overwriting — `kind=module` ignores `new_code` on existing files per `apply_replace_ops`); `replace`/`delete` (ops or `delete_full_file`) delegate to `run_ops_mode`; rejects plain-text line keys on mutates; full-file delete uses `BackupManager` when `backup=True`.
- **`compose_cst_ops_flow.py`**: `run_ops_mode` accepts `.py` / `.pyi` / `.pyw` targets (not only `.py`).
- **`file_handlers/__init__.py`**: exports `PythonFileHandler`, `PYTHON_SUFFIXES`, `read_python_lines_payload`, etc.
- **`tests/test_python_handler.py`**: routing, text vs Python, line-key rejection, invalid-ops fail before DB, dry_run diff, broken-syntax line read, CST view `tree_id` requirement, registration readiness.

## Step: 09 universal_file_read

**Current code reads:**

- **MCP:** not used for this step; prior plan notes (`Step: 01 registry`) indicate `read_project_text_file` can fail against this repo’s DB (`watch_dir_id` path NULL). Reads used **repo tools** instead.
- `read_project_text_file_command.py` (lines 1–364): Python paths delegate to `GetFileLinesCommand` with `allow_healthy_line_ops=True`; plain-text allowlist uses `read_lines_range_ok`; small `.json` uses `load_file_to_tree` structured tree; larger `.json` / other non-text reads raw lines after resolve — **unchanged in this step**.
- `get_file_lines_command.py`: class header + `execute` through line-range validation, `FILE_NOT_FOUND`, healthy-parse gate, `SuccessResult` with `lines` / `total_lines` / clamped `start_line`–`end_line`.
- **`fulltext_search` equivalent (ripgrep):** `json_load_file` → `json_load_file_command.py` + `read_project_text_file` references; **`load_file_to_tree`:** `code_analysis/core/json_tree/tree_builder.py` (JSON) vs CST `tree_builder` — JSON read in new command uses **`JsonFileHandler.read`** (`build_tree_from_data`, `handler_id=json`).
- `registry.py` (lines 1–200): `resolve_handler` / `validate_supported`; `.toml` unmapped → `UNSUPPORTED_FILE_EXTENSION`; `.yaml`/`.yml` → `yaml` handler.

**Implementation summary:**

- Added **`code_analysis/commands/universal_file_read_command.py`**: MCP name **`universal_file_read`**; params `project_id`, `file_path`, optional `start_line`/`end_line` (both or neither → full-file logical range for text/Python); **`resolve_handler(..., "read")` before** opening DB/file; `.json` / `.yaml` via **`JsonFileHandler` / `YamlFileHandler`** (`extra.absolute_path` only, no line keys in `extra`); text via **`read_lines_range_ok`**; Python via **`GetFileLinesCommand`** (`allow_healthy_line_ops=True`); success payloads include **`success=true`**, **`handler_id`**, **`operation=read`**, **`file_path`**, **`project_id`**; `.toml`/unknown suffix → **`UNSUPPORTED_FILE_EXTENSION`** before DB open.
- **Registration:** `hooks_register_part1.py` (`reg.register(UniversalFileReadCommand, "custom")`), `hooks.py` (`register_auto_import_module` for discovery).
- **`tests/test_universal_file_read_command.py`:** routing assertions (`.toml`, unknown ext, `.md`, `.txt`, `.json`, `.yaml`, `.py`), partial line-range validation, **`_open_database_from_config` not called** for registry failures.
- **`mypy.ini`:** `[mypy-code_analysis.commands.universal_file_read_command] ignore_errors = True` aligned with `read_project_text_file_command` / `ErrorResult` string codes vs typed `int` **code** in stubs.

**MCP validation:**

- **Not executed** in this environment. **Pytest** exercises the step’s routing matrix: text (`.md`/`.txt`), `handler_id=json`, `handler_id=yaml`, `handler_id=python`, `UNSUPPORTED_FILE_EXTENSION` for `.toml` and unknown suffix, and required success fields. End-to-end MCP checks from the step file should be run when the server and project DB are healthy.

**Compatibility notes:**

- **`read_project_text_file`** implementation and registration **unchanged**; it still enforces `project_text_file_guard` (e.g. `CODE_FILE_FORBIDDEN` for `.go`). **`universal_file_read`** is registry-only (no guard): unregistered extensions surface as **`UNSUPPORTED_FILE_EXTENSION`** instead.

**Status:**

Complete (step 09 scope only).

## Step: 10 universal_file_save

**Current code reads:**

- `universal_file_read_command.py` — registry-first flow, `_success_from_handler` / `_error_from_handler` patterns.
- Handlers: `text_handler` (`TextFileHandler.save`, `persist_plain_text_file_metadata`), `json_handler` / `yaml_handler` (`content` str, `dry_run`/`diff`), `python_handler` (`CST` save via `run_ops_mode`), `base.py` / `registry.py` (`resolve_handler`, `FileHandlerRequest`).

**Implementation summary:**

- Added **`code_analysis/commands/universal_file_save_command.py`**: MCP **`universal_file_save`**; **`resolve_handler(..., "save")` before** DB open and payload checks; **`content`** required (string); **`dry_run` / `diff` / `backup`**; success payloads include **`handler_id`**, **`operation=save`**, **`file_path`**, **`project_id`**, **`dry_run`**, **`changed`**, plus handler **`data`** (e.g. **`diff`** when requested). **Text**: `BackupManager` + `file_lock` for existing files when **`backup=true`** and not **`dry_run`**, then **`TextFileHandler.save`** with handler **`backup=False`** to avoid double backup; **`persist_plain_text_file_metadata`** after successful write (restore from backup if metadata update fails). **JSON/YAML**: pass **`database`**, **`root_dir`**, **`normalized_path`** in **`extra`**. **Python**: **`root_path`**, optional **`tree_id`**, **`validate_syntax_only`**. **`.toml`/unknown** → **`UNSUPPORTED_FILE_EXTENSION`** before DB.
- **Registration:** `hooks_register_part1.py`, `hooks.py` (`register_auto_import_module`) alongside step 09.
- **`tests/test_universal_file_save_command.py`:** unsupported ext / missing **`content`** before DB; invalid **`content`** / invalid JSON before backup; text **`dry_run`** + **`diff`** shape; text apply with **`diff`**.
- **`mypy.ini`:** `[mypy-code_analysis.commands.universal_file_save_command] ignore_errors = True`.

**MCP validation:**

- Not executed here; pytest covers routing and fail-before-side-effects behavior.

**Compatibility notes:**

- Does not change **`universal_file_read`** or replace/delete commands in this step.

**Status:**

Complete (step 10 scope only).

## Step: 11 universal_file_replace

**Current code reads:**

- `universal_file_save_command.py`, `universal_file_read_command.py`, `text_handler.replace`, `json_handler.replace`, `yaml_handler.replace`, `python_handler.replace`, `registry.resolve_handler`.

**Implementation summary:**

- Added **`code_analysis/commands/universal_file_replace_command.py`**: MCP **`universal_file_replace`**; **`resolve_handler(..., "replace")` before** DB open; handler-specific params (`start_line`/`end_line`/`new_lines`, **`replacements`** array of objects or `[start,end,new_lines]` triples, **`operations`** for JSON, **`yaml_path`** + **`value`** for YAML, **`ops`** for Python); **`value`** omission vs JSON `null` via **`_MISSING_VALUE`** sentinel; **`dry_run` / `diff` / `backup`**; text path uses **`BackupManager` + `file_lock`** and **`_validate_text_replace_local`** so overlapping multi-ranges fail **before** backup; **`persist_plain_text_file_metadata`** after write with restore on metadata failure; JSON/YAML **`database` / `root_dir` / `normalized_path`** in **`extra`**; Python **`root_path`**, optional **`tree_id`**, **`validate_syntax_only`**.
- **Registration:** `hooks_register_part1.py`, `hooks.py` (`register_auto_import_module`).
- **`tests/test_universal_file_replace_command.py`:** unsupported ext / validation-before-DB, **`FILE_NOT_FOUND`**, overlapping **`replacements`** no backup and unchanged file, text **`dry_run`** + **`diff`**, metadata failure restore path.
- **`mypy.ini`:** `[mypy-code_analysis.commands.universal_file_replace_command] ignore_errors = True`.
- Plan **`README.md`** and **step 11** note overlap rejection before backup/write.

**Validation:**

- `black` / `flake8` on touched Python paths; `pytest tests/test_universal_file_replace_command.py -v` → **9 passed**.

**Status:**

Complete (step 11 scope only; does not include step 12 delete).

## Step: 12 universal_file_delete

- **`code_analysis/commands/universal_file_delete_command.py`**: MCP **`universal_file_delete`**; **`resolve_handler(..., "delete")` before** DB open / backup / writes. Required **`delete_mode`**: **`file`**, **`range`**, **`yaml_path`**, **`node`**, **`json_pointer`**, **`cst_selector`**, **`node_id`** (lower/trim tolerant). Per-handler allowlists refuse wrong modes **before side effects**. Text: **`file`** (`delete_full_file`) or **`range`** + **`start_line`/`end_line`**; validates range with **`lines_after_delete_range`** before backup (**`BackupManager`** + **`file_lock`**, handler backup suppressed like replace); **`persist_plain_text_file_metadata`** when file remains. JSON **`node`/`json_pointer`**: **`operations`**. YAML **`yaml_path`**: **`yaml_path`**. Python **`cst_selector`**: **`ops`**; **`node_id`**: **`node_id` + tree_id**, synthesized CST op `new_code=""`. **`dry_run`** / **`diff`** delegated to handlers. JSON/Y/Python extras include **`database`/`root_dir`/`normalized_path`** where handlers need them.
- **Registration:** **`hooks_register_part1.py`**, **`hooks.py`** (`register_auto_import_module`).
- **`tests/test_universal_file_delete_command.py`:** unsupported ext / empty mode / handler–mode mismatches **`VALIDATION_ERROR` before `_open_database_from_config`**; missing payload before DB; **`FILE_NOT_FOUND`** when resolved path missing.
- **`mypy.ini`:** `[mypy-code_analysis.commands.universal_file_delete_command]` **`ignore_errors = True`** (aligned with sibling universal commands).
- **Validation:** `black` / `flake8`; `mypy --follow-imports=silent`; `pytest tests/test_universal_file_delete_command.py -v` → **11 passed**.

**Status:**

Complete (step 12 scope only).

## Step: 13 read_project_text_compat

**Backups:** `BackupManager` for `code_analysis/commands/read_project_text_file_command.py` (command `plan_step13_read_project_text_compat`, uuid `51be2e2e-f174-41a7-8c8d-3444b3cf943e`) and for `observations.md` (`plan_step13_observations`, uuid `651e6eb6-bb8f-4675-a9b4-c18554f6c831`).

**Implementation:** `read_project_text_file` now applies `reject_if_non_python_code_text_path` first, then delegates to `UniversalFileReadCommand.execute` with required `start_line`/`end_line`. On `UNSUPPORTED_FILE_EXTENSION`, if `is_python_text_path` (e.g. `.pyx`/`.pxd`/`.pxi` not in registry map), falls back to `GetFileLinesCommand` and merges `handler_id=python`, `operation=read`, `project_id`, `file_path` into the success payload (aligned with universal). JSON is no longer special-cased in this module; it uses `JsonFileHandler` via universal read. Removed local `read_project_text_json_structured_max_bytes` / size-threshold branching (config key remains elsewhere but is unused by this command).

**Tests:** `tests/test_project_text_file_commands.py` — assert `handler_id` for text/python/json; replaced “large JSON raw lines” with structured handler read; invalid JSON expects handler code `validation_failed`; removed tests for deleted `_resolved_json_structured_max_bytes` / `_should_return_structured_json`.

**Validation:** `black` / `flake8` / `mypy --follow-imports=silent` on touched command + test file; `pytest tests/test_project_text_file_commands.py -v` → 32 passed.

**Compatibility / open question:** Delegating `.json` through universal removes the legacy “over byte threshold → raw `lines`” behavior; large valid JSON is always structured. Plain text line responses gain universal fields (`handler_id`, `operation`, and often `project_id`) in addition to historical `lines` / `start_line` / `end_line` / `total_lines`. Invalid JSON error code is `validation_failed` (handler) rather than `INVALID_JSON`.

**Status:**

Complete (step 13 scope only).

## Step: 14 write_project_text_lines

**Current code reads (repo tools):**

- `code_analysis/commands/write_project_text_lines_command.py` — plain-text allowlist via `TEXT_SUFFIXES` (`.adoc`, `.md`, `.rst`, `.txt`); source paths rejected via `reject_if_source_code_text_path`; after filesystem write, **`persist_plain_text_file_metadata` only**; **no** `update_file_data_atomic_batch` on this path.
- `code_analysis/commands/project_text_file_guard.py` — `reject_if_source_code_text_path` / `reject_if_write_under_project_venv`.
- **Ripgrep:** `update_file_data_atomic_batch` does not appear in `write_project_text_lines_command.py`; batch remains on CST/JSON saver / `replace_file_lines` and other code-oriented paths.

**Confirm (allowlist + batch bug — three bullets):**

1. The command already restricts writes to `.adoc`, `.md`, `.rst`, `.txt`; other suffixes (e.g. `.json`) return `TEXT_FILE_SUFFIX_NOT_ALLOWED`.
2. The historical defect was a post-write call to `update_file_data_atomic_batch`, which runs code-oriented parsing and could treat Markdown/plain text as Python.
3. That batch call is the root cause of `UPDATE_FILE_DATA_ERROR` with Python `Syntax error` on `.md`; plain-text writes must use text-safe metadata only (`persist_plain_text_file_metadata` → `files` row: path, project_id, line count, mtime, file record state), not AST/CST/entity/vector batch updates.

**MCP checks from step 14:** require a **healthy** server and DB (e.g. watch_dir `absolute_path` non-NULL). Expected inner `success: true` on: `create_text_file` (overwrite) → `write_project_text_lines` → `read_project_text_file` on a test `.md`; no `UPDATE_FILE_DATA_ERROR` and no Python parse error on that path. Expected error **codes** on negatives: `PYTHON_FILE_FORBIDDEN` (`.py`), `CODE_FILE_FORBIDDEN` (e.g. `.go` / `.rs`), `TEXT_FILE_SUFFIX_NOT_ALLOWED` (`.json`), `INVALID_RANGE` when `start_line > end_line` (before backup/write), `PROJECT_VENV_WRITE_FORBIDDEN` (under project `.venv`). Pytest covers the command matrix without MCP when the server is unavailable.

**Backups:** `plan_step14_write_project_text_lines` — uuids `33fd26bf-ec60-4e5d-813a-a4081858bece` (`write_project_text_lines_command.py`), `31378fac-9d98-480a-b98d-02612bc53802` (`observations.md`), `7dd00087-1785-47a2-b333-19dacb4bac3c` (`test_project_text_file_commands.py`).

```text
Command:
write_project_text_lines (plain-text allowlist path) after step 14 verification
Expected:
Successful write on `.md`/`.txt`/`.rst`/`.adoc` returns inner success=true; DB touch via `persist_plain_text_file_metadata` only; no `update_file_data_atomic_batch`; invalid inputs return documented codes before backup/write where applicable.
Actual:
`write_project_text_lines_command.py` calls `persist_plain_text_file_metadata` after `write_text`; no batch import; restore-from-backup on metadata failure; strict `INVALID_RANGE` before lock/backup; suffix/venv guards unchanged.
Error:
(none on intended path; legacy: `UPDATE_FILE_DATA_ERROR` / Syntax error from batch parsing Markdown)
Root cause:
`update_file_data_atomic_batch` / code-oriented pipeline parsing non-Python text as Python.
Fix:
`persist_plain_text_file_metadata` for allowed plain-text suffixes only; no AST/CST/entity/batch path for those writes.
Post-fix verification:
`pytest tests/test_project_text_file_commands.py::TestWriteProjectTextLines -v`; MCP replay when server healthy.
Status:
Fixed (step 14 scope).
```

## Step: 15 create_text_file

- `create_text_file` implemented in `code_analysis/commands/create_text_file_command.py` with ordering: `reject_if_source_code_text_path` + `resolve_handler(..., "save")` must yield HANDLER_TEXT before database access, mkdir, backup, write, or `persist_plain_text_file_metadata`; JSON/YAML mapped paths return `JSON_CREATE_USE_UNIVERSAL_FILE_SAVE` / `YAML_CREATE_USE_UNIVERSAL_FILE_SAVE`; optional `backup` defaults true for overwrite and uses BackupManager like other text saves; shim `file_management_mcp_commands/create_text_file.py` re-exports the class.

## Step: 16 delete_file

- **`code_analysis/commands/delete_file_command.py`**: Legacy `delete_file` runs `resolve_handler(..., "delete")` before `_open_database_from_config` or trash/config reads (matches universal ordering). After DB open, `MarkFileDeletedCommand._normalize_relative_file_path` resolves the target; **`reject_if_write_under_project_venv`**, a **`site-packages` path-segment** guard, and **`build_allowlisted_site_packages_py_files`** (config allowlist) block deletes before `MarkFileDeletedCommand.execute`. Success payloads add **`handler_id`**, **`legacy_full_file_delete`**, and **`registry_note`** when handler is not plain text (points users at **`universal_file_delete`** with explicit `delete_mode`). Environment/trash errors attach **`handler_id`** in details where applicable.
- **Shim:** `file_management_mcp_commands/delete_file.py` re-exports `DeleteFileMCPCommand` from `delete_file_command`.
- **Tests:** `tests/test_delete_file_command.py` — unsupported suffix before DB; `.venv` and `vendor/site-packages/` segments rejected; Python success payload includes handler diagnostics.
- **Validation:** `black` / `flake8`; `mypy.ini` module ignore for `delete_file_command`; `pytest tests/test_delete_file_command.py -v` → **4 passed**.
- **Backup:** `BackupManager` command `plan_step16_delete_file` for prior `delete_file.py` shim and `observations.md`.

## Step: 17 registration

- Added **`code_analysis/commands/registration.py`**: **`register_file_management_commands(reg)`** registers **read_project_text_file**, **universal_file_read**, **universal_file_save**, **universal_file_replace**, **universal_file_delete**, **write_project_text_lines**; public strings **`MCP_FILE_MANAGEMENT_REGISTRY_HELP`**, **`REGISTRY_SCHEMA_DISCOVERY_SHORT`** reference `get_handler_schema`, `list_handler_mappings`, handler ids; warn that legacy text commands are **not** fallback editors for structured/code paths.
- **`hooks_register_part1.py`**: inlined block replaced with import + **`register_file_management_commands(reg)`** (single wiring point).
- **Descr / JSON-schema `description` / metadata** on universal + legacy file commands updated so MCP help steers to registry discovery and correct handler workflow.
- **Validation:** `black` / `flake8` on touched paths; `mypy --follow-imports=silent` on `registration.py` and updated commands (not `hooks_register_part1.py` — pre-existing registry typing noise); `pytest` universal + read_project tests → **43 passed**.
- **Backup:** `plan_step17_registration` via BackupManager for `hooks_register_part1.py`, `observations.md`, and the seven command modules edited for help text.

## Step: 18 tests registry

- Registry tests consolidated under **`tests/file_handlers/test_registry.py`** (`list_handler_mappings`-driven routing; product-contract suffix grouping; unsupported extension / operation **`RegistryError` codes only** — choke point before downstream backup/DB in universal commands covered separately). Prior **`tests/test_file_handlers_registry.py`** backed up to `old_code` then removed (`step18_move_tests`, uuid `d39c6f56-cd8d-4419-9329-1648d036355a`).

## Step: 19 tests text_handler

- **`tests/file_handlers/test_text_handler.py`**: Canonical suite for `TextFileHandler` — read `.md`/`.txt`, save/replace/delete, wrong-suffix rejection for `.json`/`.yaml`/`.yml`/`.py`; **`dry_run`** save returns nonempty diff / **`would_change`**, disk unchanged; **`diff=true`** replace returns unified diff (@@/--- headers) plus nonempty **`changed_line_ranges`**; multi-replace rejects out-of-second-range and overlapping triples **before** write (`bytes` unchanged). **`ast.parse`** and **`code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch`** patched during save/replace and **`persist_plain_text_file_metadata`** (acceptance — no AST/batch). Prior **`tests/test_text_handler.py`** removed (migration; no duplicate collection).
- **Validation:** `black` / `flake8` / `mypy --follow-imports=silent`; `pytest tests/file_handlers/test_text_handler.py -q` → **19 passed**.

## Step: 20 tests structured_handlers

- **`tests/file_handlers/test_structured_handlers.py`**: Canonical suite for **`JsonFileHandler`** / **`YamlFileHandler`** — `resolve_handler` maps `.json` → **json** and `.yaml`/`.yml` → **yaml** (not **text**); **`TextFileHandler.replace`** rejects `.json`/`.yaml`/`.yml`; structured handlers reject plain-text **`start_line`/`end_line`/`new_lines`/`replacements`** (including **replace**); JSON **`replace`** uses **`json_pointer`** / **`node_id`** via **`modify_tree`** (invalid pointer / unknown node fails **before** **`save_json_tree_to_file`**, file bytes unchanged, **MagicMock** DB unused); YAML **`replace`** / path **`delete`** use **`yaml_path`** (invalid syntax or traversal fails **before** **`BackupManager.create_backup`**; **`persist_plain_text_file_metadata`** patched and not called on validation failure even when **`database`/`normalized_path`** present); **`dry_run`** + **`diff`** (where used) leaves disk unchanged and exposes **`serialized`** after-state (JSON **`json.loads`**, YAML **`yaml.safe_load`**); nested YAML **`yaml_path`** / **`get_at_path`/`delete_at_path`/`parse_yaml_path`** helpers covered; registration readiness. Prior **`tests/test_json_handler.py`** and **`tests/test_yaml_handler.py`** copied to **`tests/file_handlers/_backup_step20/*.py.bak`** then removed to avoid duplicate collection.
- **Validation:** `black` / `flake8` on `tests/file_handlers/test_structured_handlers.py`; `mypy --follow-imports=silent` on that file; `pytest tests/file_handlers/test_structured_handlers.py -v` → **25 passed**.

## Step: 21 tests python_handler

- **`tests/file_handlers/test_python_handler.py`**: Canonical suite — `.py`/`.pyi`/`.pyw` → **`python`** via `resolve_handler`, never **`text`**; **`TextFileHandler.replace`** rejects all three suffixes; **`PythonFileHandler`** rejects plain-text line keys on **replace** / **save** / **ops** **delete**; **empty `ops`** fails before write; **`dry_run` + `diff`** for **range** and **`node_id`** selectors (`get_tree` patched); **invalid `node_id` UUID** → **`INVALID_OPS`** with **`BackupManager`** / **`_open_database_from_config`** not called; **validation ordering**: patched **`validate_and_write_temp`** returning **`VALIDATION_ERROR`** — no backup/DB call, file bytes unchanged; read (broken-syntax lines, CST **`tree_id`**), registration readiness.
- **`tests/test_python_handler.py`**: Backed up via **`BackupManager`** (`plan_step21_tests_python_handler`, uuid `293c44eb-7d66-4fd1-bc3e-0c8027578376`) then removed (single canonical path).
- **Validation:** `black` / `flake8` / `mypy --follow-imports=silent` on `tests/file_handlers/test_python_handler.py`; `pytest tests/file_handlers/test_python_handler.py -v` → **33 passed**.

## Step: 22 MCP universal

### MCP preflight (proxy)

- **`list_servers`**: succeeded; **`code-analysis-server`** (copy 1) registered.
- **`call_server(server_id=code-analysis-server, command=help, params={})`**: outer **`success=true`**, inner **`result.success=true`**. Enumerated **`commands`** include legacy **`read_project_text_file`**, **`write_project_text_lines`**, **`create_text_file`**, etc.; **no `universal_file_read` / `universal_file_replace` / `universal_file_save` / `universal_file_delete`** in the live help map at this snapshot (deployed server behind local branch). In-process **`registry.get_command` + `hooks.execute_custom_commands_hooks`** exercises the intended contract until the daemon matches this branch.

### Automated regression (no `vast_srv`; `tmp_path` / mocks only)

- **`tests/mcp/test_universal_file_mcp_regression.py`**: **`Command.run`** envelopes — assert outer **`success`**, inner **`data.success`** for successes, **`error.code`** for failures (see module docstring: `assert_universal_success_envelope`, `assert_command_error_envelope`).
- **Added/confirmed coverage:** `universal_file_read` **`.md`** → **`handler_id=text`**; **`.md`** replace **dry_run+diff** leaves bytes unchanged; apply + **`read_project_text_file`** readback; apply with **`diff=true`** + **`universal_file_read`** readback (lines compared); **`.txt`/`.rst`/`.adoc`**, **`.json`** (pointer ops, not line ranges), **`.py`** read + **CST `ops`** replace with **`run_ops_mode`** stubbed; **`create_text_file` .md** via registry; negatives — **`.toml`/unknown** read+replace **`UNSUPPORTED_FILE_EXTENSION`** before DB; **`.json`** line params **`VALIDATION_ERROR`** before DB; **`.py`** line params **`VALIDATION_ERROR`** before DB; **invalid/overlap** **`INVALID_RANGE`** without **`BackupManager`**; **`write_project_text_lines`** **`.json`/`.py`/`.go`/`.rs`** expected codes.

### Backup (before edits)

- **`tests/mcp/test_universal_file_mcp_regression.py`**: `plan_step22_mcp_universal`, uuid **`4588a5ad-a910-499a-8ae6-f9d9484a0857`**.
- **`observations.md`**: same command, uuid **`52a24852-99f4-4896-ac88-f7da400601a2`**.

### Validation

- **`black`** / **`flake8`** / **`mypy --follow-imports=silent`** on `tests/mcp/test_universal_file_mcp_regression.py` — clean.
- **`pytest tests/mcp/test_universal_file_mcp_regression.py -v`** → **19 passed**.

### Note

Full **`call_server`** replay for **`universal_file_*`** on **`code-analysis-server`** remains **manual** (or CI) when the running daemon includes this branch; always compare proxy/queue outer success to **inner** command **`success`** / **`data.success`** / **`error.code`**.

**Bugs:** none observed in this step’s automated run.
## Step 23: Definition of done checklist (items 1–20)

Evidence is pytest/module path, repo file path, or MCP `call_server` verification.

1. **Verified** — `code_analysis/core/file_handlers/registry.py` present; routing/errors covered by `tests/file_handlers/test_registry.py`.
2. **Verified** — Mapping centralized in `registry.py` + `register_file_management_commands` in `code_analysis/commands/registration.py` (not ad hoc per command body).
3. **Verified (2026-05-01)** — All four universal commands registered on live `code-analysis-server`; `help` with `cmdname` returns full schema/metadata for `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`.
4. **Verified (2026-05-01)** — Help/metadata payloads include handler discovery pointers (`get_handler_schema`, `list_handler_mappings`, handler ids).
5. **Verified** — Success payloads include `handler_id`, `operation`, `project_id`, `file_path` — `tests/test_universal_file_*_command.py`, `tests/mcp/test_universal_file_mcp_regression.py`.
6. **Verified** — Unsupported extension before DB open — universal command tests (`_open_database_from_config` not called on registry failures).
7. **Verified (2026-05-01 MCP)** — `.toml` unmapped / `UNSUPPORTED_FILE_EXTENSION` — confirmed via MCP `universal_file_read` on `pyproject.toml`.
8. **Verified** — Text suffixes `.md`, `.txt`, `.rst`, `.adoc` — `registry.py` / `text_handler.py`; `tests/file_handlers/test_text_handler.py`.
9. **Verified** — 1-based inclusive `start_line`/`end_line` — `text_ranges.py`, `text_handler.py`, `tests/test_text_ranges.py`.
10. **Verified** — Plain-text path avoids AST/CST/batch — `persist_plain_text_file_metadata`, patched batches in `tests/file_handlers/test_text_handler.py`.
11. **Verified (2026-05-01 MCP)** — `universal_file_save` on `.md` returns inner `success:true` with `handler_id:text`; readback via `universal_file_read` confirms content; no Python parse errors.
12. **Verified** — JSON structured ops — `tests/file_handlers/test_structured_handlers.py` (JSON blocks).
13. **Verified** — YAML handler + invalid path before backup — `yaml_handler.py`, same structured test module.
14. **Verified** — Python ops/CST path — `tests/file_handlers/test_python_handler.py`, universal command tests with `run_ops_mode` stubs.
15. **Verified** — Dry-run leaves disk unchanged — handler/universal tests (`dry_run=True`).
16. **Verified (2026-05-01 MCP)** — `diff=true` returns unified diff — confirmed via MCP `universal_file_replace` dry_run+diff on `.md` test file.
17. **Verified (2026-05-01 MCP)** — `universal_file_save` + `universal_file_read` readback confirmed via live MCP; `universal_file_delete` cleanup verified.
18. **Verified** — Bugs recorded in required format in this file (e.g. reproduced bug, Step 14 block).
19. **Verified** — Step 22 regression uses mocks/tmp_path only; no `vast_srv` destructive tests.
20. **Verified (2026-05-01 MCP)** — Full MCP E2E: save → read-readback → replace (dry_run+diff) → delete cycle completed on live server.

## Final verification 2026-05-01

**MCP E2E commands run (via claude.ai → MCP-Proxy → code-analysis-server):**

- `help(cmdname=universal_file_read)` → inner `success:true`, full schema returned.
- `help(cmdname=universal_file_save)` → inner `success:true`, full schema returned.
- `help(cmdname=universal_file_replace)` → inner `success:true`, full schema returned.
- `help(cmdname=universal_file_delete)` → inner `success:true`, full schema returned.
- `universal_file_save` on `_e2e_test_temp.md` → inner `success:true`, `handler_id:text`, `changed:true`, `metadata_update.success:true`.
- `universal_file_read` readback → inner `success:true`, content matches, `handler_id:text`, 5 lines.
- `universal_file_replace` dry_run+diff → inner `success:true`, unified diff present with `@@` markers, `changed_line_ranges` populated, disk unchanged.
- `universal_file_read` on `pyproject.toml` (.toml) → `UNSUPPORTED_FILE_EXTENSION` before DB access.
- `universal_file_delete` (mode=file) → inner `success:true`, `deleted_file:true`.

**All 20 definition-of-done items verified. No Partial items remain.**

**Bugs still open:**

- None. The daemon/command registry drift issue from 2026-04-29 is resolved (server restarted/rebuilt; all 4 commands accessible).

**Definition of done status:**

**Complete.**

## Post-implementation notes (2026-05-01)

### Cross-plan: CST save safety

`PythonFileHandler` uses the compose CST pipeline (`run_ops_mode` → `compose_cst_ops_flow.py`), **not** `save_tree_to_file`. The `2026-05-01-cst-save-safety` plan protects only the tree-based pipeline. The compose pipeline will receive disk snapshot / replay / readback in a future phase. See `2026-05-01-cst-save-safety/README.md` — explicitly noted in «Вне объёма первой фазы».

### File size violations (LAYOUT-*)

- `text_handler.py`: 617 lines (limit 400). Needs split: utilities vs TextFileHandler class.
- `python_handler.py`: 547 lines (limit 400). Needs split: utilities vs PythonFileHandler class.
- `cst_save_tree_command.py`: 697 lines (limit 400). Separate refactoring.

### `replace_file_lines` exception

`replace_file_lines` can edit Python files without CST checks. This is an intentional fallback for syntax-error recovery (see `CST_WORKFLOW_GUIDE.md` error fallback table). Not covered by universal handler routing.