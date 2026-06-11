<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic steps index — tactical_batch_avoid_duplicate_file_reread

## Tech spec and parents

- `docs/tech_spec/tech_spec.md`
- Global step: `docs/tech_spec/steps/simplify_comprehensive_analysis_pipeline.md`
- Tactical task: `../tactical_batch_avoid_duplicate_file_reread.md`

## Atomic summary

- **Goal:** In `comprehensive_analysis` batch mode, duplicate detection must use the `source_code` string already read in `run_batch`, not `DuplicateDetector.find_duplicates_in_file` (second disk read).
- **Steps:** 2
- **Order:** (1) modify `batch_one_file.py` → (2) add `tests/test_batch_one_file_duplicates.py`
- **Waves:** See `parallel_waves.md`

## Atomic step index

| Step ID | File | Target | Depends on |
|---------|------|--------|------------|
| BATCH-DUP-01 | `modify_batch_one_file_use_find_duplicates_in_code.md` | `code_analysis/commands/comprehensive_analysis_mcp/batch_one_file.py` | — |
| BATCH-DUP-02 | `add_tests_batch_duplicate_no_disk_reread.md` | `tests/test_batch_one_file_duplicates.py` | BATCH-DUP-01 |

## Notes

- `DuplicateDetector.find_duplicates_in_code(source_code, file_path)` already exists in `code_analysis/core/duplicate_detector.py`; no detector API change required for this batch.
