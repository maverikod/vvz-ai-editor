<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step: Batch duplicate check uses in-memory `source_code`

## Executor role

`coder_auto`

## Execution directive

In `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py`, inside the `check_duplicates` branch of `analyze_one_file_in_batch`, replace the duplicate-detection call so it uses the `source_code` argument already passed into the function and passes the filesystem path only as the `filename` context for `ast.parse`, matching existing `DuplicateDetector.find_duplicates_in_code` behavior. Do not add or change any other file in this step.

## Parent links (mandatory)

1. Global step: `docs/tech_spec/steps/simplify_comprehensive_analysis_pipeline.md`
2. Tactical task: `docs/tech_spec/branches/simplify_comprehensive_analysis_pipeline/tasks/tactical_batch_avoid_duplicate_file_reread.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file (full path from repo root):** `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py`
- **action:** modify

## Dependency contract

- **Depends on:** none (first wave).
- **Blocks:** `add_tests_batch_duplicate_no_disk_reread.md` until merged (tests assert the new call path).

## Required context

- `run_batch` in `code_analysis/commands/comprehensive_analysis_mcp/execute_batch.py` reads each file with `full_path.read_text(encoding="utf-8")` and passes that string as `source_code` into `analyze_one_file_in_batch`. The duplicate branch must consume that same string so the file is not opened again.
- `DuplicateDetector.find_duplicates_in_file(file_path: str)` reads UTF-8 from disk then delegates to the same AST path as `find_duplicates_in_code`.

## Read first (exact paths)

1. `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py` — full module; edit only the duplicates branch.
2. `code_analysis/core/duplicate_detector.py` — read method signatures for `find_duplicates_in_file`, `find_duplicates_in_code`, and `find_duplicates_in_ast` (confirm no new API is required).

## Reference symbols (exact names; no implementation copied here)

**`batch_one_file.py`**

- Function: `analyze_one_file_in_batch(`
  - `full_path: Path`
  - `file_path_str: str`
  - `source_code: str`
  - `file_id: Any`
  - `file_record: Dict[str, Any]`
  - `proj_id: Optional[str]`
  - `analyzer: Any`
  - `project_mypy_errors: Dict[str, List[str]]`
  - `timings_sec: Dict[str, float]`
  - `check_placeholders: bool` … `check_docstrings: bool`
  - `duplicate_min_lines: int`
  - `duplicate_min_similarity: float`
  - `set_step_desc: Optional[Callable[[str], None]] = None`
  - `) -> Tuple[Dict[str, Any], Dict[str, Any], Any]`

**`duplicate_detector.py` — `DuplicateDetector`**

- `find_duplicates_in_file(self, file_path: str) -> List[Dict[str, Any]]`
- `find_duplicates_in_code(self, source_code: str, file_path: str = "<string>") -> List[Dict[str, Any]]`

## Expected file change

- In the `if check_duplicates:` block, after constructing `detector = DuplicateDetector(...)`, replace the call that reads from disk with a call that passes the in-memory string and the path string used for parse context.
- **Before (conceptual):** invoke instance method that opens `full_path` from disk.
- **After (conceptual):** invoke instance method with first argument equal to the parameter `source_code` and second argument equal to the string form of `full_path` suitable for `ast.parse(..., filename=...)`.
- Preserve: `DuplicateDetector` constructor arguments (`min_lines=duplicate_min_lines`, `min_similarity=duplicate_min_similarity`, `use_semantic=False`), timing accumulation, loop that sets `occ["file_path"] = file_path_str`, and all other branches unchanged.

## Forbidden alternatives

- Do not modify `code_analysis/core/duplicate_detector.py` in this step (existing `find_duplicates_in_code` is sufficient).
- Do not change `execute_single` or other call sites.
- Do not change duplicate-detection thresholds, `use_semantic`, or result shaping.
- Do not add logging, new dependencies, or refactors outside the duplicates branch.

## Atomic operations

1. Open `batch_one_file.py`.
2. Locate the `if check_duplicates:` block (after `set_step_desc("duplicates")` and timing `t0`).
3. Keep `detector = DuplicateDetector(...)` as today.
4. Replace the single duplicate-discovery assignment so it calls `find_duplicates_in_code` on `detector` with `(source_code, str(full_path))` instead of `find_duplicates_in_file` with `str(full_path)` only.
5. Leave the subsequent `for group in duplicates:` loop unchanged.

## Method / branch logic (step-by-step)

**Branch: `if check_duplicates:`**

1. Optionally call `set_step_desc("duplicates")` if provided (unchanged).
2. Record start time `t0` (unchanged).
3. Instantiate `DuplicateDetector` with existing kwargs (unchanged).
4. **New behavior:** Compute `duplicates` by calling `find_duplicates_in_code` on the detector with the function parameter `source_code` as the first argument and `str(full_path)` as the second argument (path for `ast.parse` filename and snippet context).
5. Add elapsed time to `timings_sec["duplicates"]` (unchanged).
6. For each group and occurrence, set `occ["file_path"] = file_path_str` (unchanged).
7. Assign `file_results["duplicates"]` (unchanged structure).

## Error handling

- `find_duplicates_in_code` catches `SyntaxError` from `ast.parse` and returns `[]` — same as `find_duplicates_in_file`. No new try/except in `batch_one_file.py`.
- Do not swallow exceptions that were not swallowed before; behavior must match the previous call path’s outward behavior.

## Return value specification

- `analyze_one_file_in_batch` return value unchanged: same tuple shape; `file_results["duplicates"]` remains `List[Dict[str, Any]]` with the same nested structure as today.

## Edge cases

- **Empty `source_code`:** Same as empty file read previously; `find_duplicates_in_code` parses and proceeds or returns `[]` on syntax error — align with `find_duplicates_in_file`.
- **Invalid Python:** `[]` duplicates list — unchanged semantics.
- **Non-ASCII UTF-8:** Caller already used UTF-8 `read_text`; passing the same string preserves semantics vs prior disk read.

## Constants and literals

- No new constants. Reuse existing constructor literals: `use_semantic=False`.

## Imports

**Complete import list for the target file after edit (must match unchanged top of file):**

- `import logging`
- `import time`
- `from pathlib import Path`
- `from typing import Any, Callable, Dict, List, Optional, Tuple`
- `from ...core.duplicate_detector import DuplicateDetector`

No new imports.

## Class/function skeleton

- **Module:** keep existing module docstring (author Vasiliy Zdanovskiy, email vasilyvz@gmail.com, description) unchanged.
- **Single function** `analyze_one_file_in_batch` — signature and body unchanged except the one call site in the duplicates branch as specified.

## Forbidden patterns (LLAMA)

- Do not rename `analyze_one_file_in_batch` or alter its parameter list.
- Do not call `open` or `Path.read_text` inside the duplicates branch.
- Do not use `Any` for new variables (no new variables required).
- Do not modify files other than the target file.

## Mandatory validation

Run from repository root with project venv active (see `docs/PROJECT_RULES.md` CR-005, CR-007):

1. `black code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py`  
   **Success:** message contains `reformatted` or `1 file left unchanged`.
2. `flake8 code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py`  
   **Success:** exit code 0, no output.
3. `mypy code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py`  
   **Success:** output contains `Success: no issues found`.
4. `pytest tests/test_comprehensive_analysis_batch_summary.py tests/test_comprehensive_analysis_mtime_gate.py -v`  
   **Success:** all tests PASSED.

**Completion condition:** all tests in step 4 pass.

## Decision rules

- If `find_duplicates_in_code` is missing from `DuplicateDetector`, stop and escalate per tactical task (should not occur in current tree).

## Blackstops

- Any flake8 or mypy regression on the target file.
- Any failure in the pytest modules listed above.

## Handoff package

- Diff limited to `batch_one_file.py` duplicates branch call site.
- Confirmation that validation commands succeeded and all listed tests passed.

## Expected deliverables

- One committed-ready change: batch duplicate path uses in-memory `source_code` with no second disk read for duplicates.
