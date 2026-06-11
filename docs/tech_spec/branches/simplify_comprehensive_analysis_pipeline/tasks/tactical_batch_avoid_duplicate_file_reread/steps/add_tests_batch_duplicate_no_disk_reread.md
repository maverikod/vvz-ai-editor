<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic step: Tests — batch duplicate path uses `find_duplicates_in_code`, not disk read

## Executor role

`coder_auto`

## Execution directive

Create `tests/test_batch_one_file_duplicates.py` with focused unit tests that prove `analyze_one_file_in_batch`, when only duplicate checking is enabled, calls `DuplicateDetector.find_duplicates_in_code` with the passed-in `source_code` and path string, and does not call `find_duplicates_in_file`. Do not modify production code in this step.

## Parent links (mandatory)

1. Global step: `docs/tech_spec/steps/simplify_comprehensive_analysis_pipeline.md`
2. Tactical task: `docs/tech_spec/branches/simplify_comprehensive_analysis_pipeline/tasks/tactical_batch_avoid_duplicate_file_reread.md`
3. Technical specification: `docs/tech_spec/tech_spec.md`

## Step scope

- **Target file (full path from repo root):** `tests/test_batch_one_file_duplicates.py`
- **action:** create

## Dependency contract

- **Depends on:** `modify_batch_one_file_use_find_duplicates_in_code.md` implemented (production must call `find_duplicates_in_code`; otherwise tests for “not calling `find_duplicates_in_file`” still pass but the primary assertion may fail).
- **Blocks:** none.

## Required context

- `analyze_one_file_in_batch` lives in `code_analysis.commands.comprehensive_analysis_mcp.batch_one_file`.
- Tests patch `DuplicateDetector` on the module under test: `code_analysis.commands.comprehensive_analysis_mcp.batch_one_file.DuplicateDetector` so the patches apply to instances created inside the function.

## Read first (exact paths)

1. `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py` — function signature and parameter order for `analyze_one_file_in_batch`.
2. `code_analysis/core/duplicate_detector.py` — confirm `find_duplicates_in_code` and `find_duplicates_in_file` exist on `DuplicateDetector`.
3. `tests/test_comprehensive_analysis_batch_summary.py` — style reference for pytest, `tmp_path`, `MagicMock`.

## Expected file change

- New file `tests/test_batch_one_file_duplicates.py` containing two test functions (names below) and module docstring.

## Forbidden alternatives

- Do not read or edit files under `test_data/`.
- Do not add integration tests that require a running MCP server.
- Do not modify `batch_one_file.py` or `duplicate_detector.py` in this step.
- Do not assert internal timing values beyond “call happened”.

## Atomic operations

1. Create `tests/test_batch_one_file_duplicates.py`.
2. Add module docstring (see File header below).
3. Implement `test_analyze_one_file_in_batch_duplicates_calls_find_duplicates_in_code_with_source_and_path`.
4. Implement `test_analyze_one_file_in_batch_duplicates_does_not_call_find_duplicates_in_file`.

## File header (exact module docstring)

First lines of the new file (triple-quoted string):

- Line 1: `"""`
- Line 2: `Tests for comprehensive_analysis batch per-file duplicate detection using in-memory source.`
- Line 3: blank
- Line 4: `Author: Vasiliy Zdanovskiy`
- Line 5: `email: vasilyvz@gmail.com`
- Line 6: `"""`

## Imports

**Complete import list (exact order recommended):**

- `from __future__ import annotations`
- `from pathlib import Path`
- `from typing import Any, Dict`
- `from unittest.mock import MagicMock, patch`
- `import pytest`
- `from code_analysis.commands.comprehensive_analysis_mcp.batch_one_file import analyze_one_file_in_batch`
- `from code_analysis.core.duplicate_detector import DuplicateDetector`

## Class/function skeleton

- No classes.
- **Function 1:** `def test_analyze_one_file_in_batch_duplicates_calls_find_duplicates_in_code_with_source_and_path(tmp_path: Path) -> None:`  
  - **Summary:** Asserts `find_duplicates_in_code` is invoked once with `(source_code, str(full_path))` and returns propagate to `file_results["duplicates"]`.
- **Function 2:** `def test_analyze_one_file_in_batch_duplicates_does_not_call_find_duplicates_in_file(tmp_path: Path) -> None:`  
  - **Summary:** Asserts `find_duplicates_in_file` is never called when duplicates run.

## Method logic — test 1 (step-by-step)

1. Create `full_path = tmp_path / "sample.py"` and write a short UTF-8 Python body (at least one line; content need not contain real duplicates).
2. Set `source_code = full_path.read_text(encoding="utf-8")` so it matches what `run_batch` would pass.
3. Build `timings_sec: Dict[str, float]` with at least key `"duplicates": 0.0` (other keys optional if unused).
4. `analyzer = MagicMock()`.
5. `file_record: Dict[str, Any] = {"project_id": "p_test"}`.
6. Use `patch.object(DuplicateDetector, "find_duplicates_in_code", return_value=[])` as context manager, capturing the mock as `mock_in_code`.
7. Call `analyze_one_file_in_batch(`  
   `full_path=full_path`,  
   `file_path_str="sample.py"`,  
   `source_code=source_code`,  
   `file_id=1`,  
   `file_record=file_record`,  
   `proj_id="p_test"`,  
   `analyzer=analyzer`,  
   `project_mypy_errors={}`,  
   `timings_sec=timings_sec`,  
   all `check_*` flags `False` **except** `check_duplicates=True`,  
   `duplicate_min_lines=5`,  
   `duplicate_min_similarity=0.8`,  
   `set_step_desc=None`,  
   `)`.
8. Assert `mock_in_code.call_count == 1`.
9. Assert first positional args: `mock_in_code.call_args[0][0] == source_code` and `mock_in_code.call_args[0][1] == str(full_path)`.
10. Unpack return as `file_results, _summary, _pid` and assert `file_results["duplicates"] == []`.

## Method logic — test 2 (step-by-step)

1. Same setup as test 1 for path, `source_code`, `timings_sec`, `analyzer`, `file_record`, and `analyze_one_file_in_batch` arguments (only `check_duplicates=True`).
2. Nest patches:  
   - `patch.object(DuplicateDetector, "find_duplicates_in_code", return_value=[])`  
   - `patch.object(DuplicateDetector, "find_duplicates_in_file")` as `mock_in_file`
3. Call `analyze_one_file_in_batch` as in test 1.
4. Assert `mock_in_file.call_count == 0`.

## Error handling (tests)

- No try/except in tests; let assertion failures surface.
- Do not catch and silence exceptions from the code under test.

## Return value specification

- Test functions return `None` (pytest void tests).

## Edge cases

- **Mock return `[]`:** Ensures no dependency on real duplicate groups; summary keys still computed from empty list.
- **`proj_id`:** Use a fixed string `"p_test"` consistent with `file_record["project_id"]` so the third return value is deterministic.

## Constants and literals

- `encoding="utf-8"` for `read_text` and `write_text`.
- `duplicate_min_lines=5`, `duplicate_min_similarity=0.8` — match typical defaults from `execute_batch` ctx.
- File name string `"sample.py"` for `file_path_str`.
- `file_id=1` (integer).

## Exact test expectations

| Test name | Asserts |
|-----------|---------|
| `test_analyze_one_file_in_batch_duplicates_calls_find_duplicates_in_code_with_source_and_path` | `find_duplicates_in_code` once; args `(source_code, str(full_path))`; `file_results["duplicates"] == []` |
| `test_analyze_one_file_in_batch_duplicates_does_not_call_find_duplicates_in_file` | `find_duplicates_in_file` call count 0 |

## Forbidden patterns (LLAMA)

- Do not patch `open` or `Path.read_text` unless required (not required if test 2 covers `find_duplicates_in_file`).
- Do not use bare `except:`.
- Do not add `pytest.mark.asyncio` (function under test is synchronous).

## Mandatory validation

From repository root with venv active:

1. `black tests/test_batch_one_file_duplicates.py`  
   **Success:** reformatted or unchanged message.
2. `flake8 tests/test_batch_one_file_duplicates.py`  
   **Success:** exit code 0.
3. `mypy tests/test_batch_one_file_duplicates.py`  
   **Success:** `Success: no issues found`.
4. `pytest tests/test_batch_one_file_duplicates.py tests/test_comprehensive_analysis_batch_summary.py tests/test_comprehensive_analysis_mtime_gate.py -v`  
   **Success:** all PASSED.

**Completion condition:** all tests in command 4 pass.

## Decision rules

- Patch target must be `DuplicateDetector` as imported in `batch_one_file` (patch the class in the `batch_one_file` module namespace: `patch("code_analysis.commands.comprehensive_analysis_mcp.batch_one_file.DuplicateDetector.find_duplicates_in_code", ...)` **or** `patch.object` on that imported class — use one consistent approach; prefer patching via the module under test:  
  `patch.object(batch_one_file.DuplicateDetector, ...)` after `import code_analysis.commands.comprehensive_analysis_mcp.batch_one_file as batch_one_file` **or** string path `code_analysis.commands.comprehensive_analysis_mcp.batch_one_file.DuplicateDetector`.

## Blackstops

- Patch not applied to class used inside `analyze_one_file_in_batch` (wrong import path).
- Flake8/mypy failures on the new test file.

## Handoff package

- New test module path and green pytest output for the validation command.
- Confirmation that production step already merged so both tests pass.

## Expected deliverables

- Regression tests preventing reintroduction of `find_duplicates_in_file` in the batch duplicate branch.
