<!--
Tactical task — parent global step: simplify_comprehensive_analysis_pipeline
Status: active
-->

# Tactical Task: Batch duplicate check without second disk read

## Purpose

Remove redundant per-file disk I/O in the `comprehensive_analysis` batch path: `execute_batch.run_batch` already reads file contents into `source_code` before calling `analyze_one_file_in_batch`, but duplicate detection currently calls `DuplicateDetector.find_duplicates_in_file`, which opens and reads the same path again. Using an in-memory code path eliminates one full read per analyzed file when `check_duplicates` is enabled, improving latency and simplifying the data flow (single source of truth for file text in the batch loop).

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/simplify_comprehensive_analysis_pipeline.md`

## Scope

**Included:** `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py` (batch duplicate invocation only); `code_analysis/core/duplicate_detector.py` if a small public helper is required to accept `source_code: str` plus path for context; pytest additions or updates under `tests/` that assert behavior or prevent regression.

**Excluded:** Single-file `execute_single` path (already has its own read semantics); changing duplicate detection algorithms; flake8/mypy subprocess policy; DB schema; summary counting keys; `test_data/` direct edits (revalidation via `tester_ca` only if harness run is requested).

## Boundaries

- Do not change global `tech_spec.md` or global step files from this tactical file.
- `coder_auto` / `tester_auto` must not touch `test_data/vast_srv` code paths.

## Dependencies

none

## Parallelization note

Sequential: plan → code → tests → optional MCP harness.

## Expected outcome

1. When `check_duplicates` is true in batch mode, duplicate detection uses the same `source_code` string already read in `run_batch`, not a second `open`/`read_text` of `full_path`.
2. Semantics of reported duplicates unchanged for identical inputs.
3. `pytest` for comprehensive analysis batch/summary and related tests passes.
4. One git commit records this logical batch.

## Correction items

none

## Questions/escalation rule

Escalate if `DuplicateDetector` cannot safely accept pre-read `source_code` without breaking path-based heuristics (then document exact API gap).

---

## File inventory

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py` | Call duplicate detection with in-memory `source_code` |
| modify | `code_analysis/core/duplicate_detector.py` | Only if existing API lacks `find_duplicates_in_code`; align naming with researcher evidence |
| modify or create | `tests/test_comprehensive_analysis_batch_summary.py` or new test module | Regression: batch path still produces expected duplicate-related structure when mocked |

## Class/function inventory

- `analyze_one_file_in_batch(...)` in `code_analysis.commands.comprehensive_analysis_mcp.batch_one_file` — replace `find_duplicates_in_file(str(full_path))` with code-path that uses `source_code` and path string as needed.
- `DuplicateDetector` in `code_analysis.core.duplicate_detector` — use existing `find_duplicates_in_code` or equivalent per implementation; methods must keep return types unchanged for callers.

## Data structures

No new persisted models; in-memory only.

## Import map

Follow existing imports in touched files; no new third-party dependencies.

## Error handling map

If `source_code` is empty or invalid for AST, preserve existing duplicate-detection behavior (exceptions or empty results as today).

## Config dependency

none

## Test plan

- Run `tests/test_comprehensive_analysis_batch_summary.py` and `tests/test_comprehensive_analysis_mtime_gate.py`.
- Run `tests/test_analysis_commands_integration.py` if integration still valid for single-file command.
- Optional: test that duplicate branch does not call `open` on path when `source_code` provided (mock/spy).

## Concrete examples

- Input: `source_code` equals file contents on disk, `full_path` is `/proj/src/a.py`. Output: same duplicate list as before change when `find_duplicates_in_file` was used.

## Algorithm/logic description

1. In `analyze_one_file_in_batch`, when `check_duplicates` is true, invoke duplicate detection with `source_code` already passed into the function and the file path only as identifier/metadata for parsing.
2. Do not re-read from `full_path` for duplicates in batch mode.

## Forbidden approaches

- Do not read `test_data/vast_srv` with direct file tools.
- Do not widen scope to full AST unification across `ComprehensiveAnalyzer` in this batch.
