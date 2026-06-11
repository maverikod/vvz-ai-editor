<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Atomic parallel waves — tactical_batch_avoid_duplicate_file_reread

## Tech spec and parents

- `docs/tech_spec/tech_spec.md`
- Global step: `docs/tech_spec/steps/simplify_comprehensive_analysis_pipeline.md`
- Tactical task: `docs/tech_spec/branches/simplify_comprehensive_analysis_pipeline/tasks/tactical_batch_avoid_duplicate_file_reread.md`

## Waves

| Wave | Step files | Notes |
|------|------------|--------|
| 1 | `modify_batch_one_file_use_find_duplicates_in_code.md` | Production change only; unblocks tests |
| 2 | `add_tests_batch_duplicate_no_disk_reread.md` | Depends on Wave 1 implementation |

Steps within a single wave may not run in parallel if your process requires tests immediately after code; Wave 2 logically depends on Wave 1.
