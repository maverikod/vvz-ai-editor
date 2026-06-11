<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Tactical task: implementation_plan Step 16 + parent repair_cst_save_tree_persist_logging_path.
Resynchronized with docs/tech_spec/steps/repair_cst_save_tree_persist_logging_path.md
-->

# Tactical Task: Repair and instrument `cst_save_tree` persist/logging path

## Purpose

Repair the first failing `cst_save_tree` persist/logging path (including prior `LogRecord` / `extra` collision class) and add focused diagnostic logging along that path so future failures are traceable. `vast_srv` remains verification-only via `tester_ca`.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_cst_save_tree_persist_logging_path.md` (**authoritative for this resync**)
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`
- `docs/tech_spec/implementation_plan.md` (Step 16)

## Scope

**Included:** Server-side `cst_save_tree` command path, atomic save/backup/DB sync path, unified logging; minimal repair; **focused diagnostic logs** (safe for `LogRecord`); git commit; `tester_ca` revalidation of guarded `vast_srv` save sequence.

**Excluded:** `SERVER_NOT_FOUND` as primary until this path is addressed; broad `vast_srv` backlog; direct edits to `test_data/vast_srv` except via `tester_ca`.

## Boundaries

- Narrow: save/persist/logging around `cst_save_tree` only.
- No `extra={"importance": ...}` or other reserved `LogRecord` keys in `extra`.
- `coder_auto` / `tester_auto` must not touch guarded `vast_srv` code.

## Dependencies

- Step 15 command-boundary capture (narrative) satisfied.

## Parallelization note

Research → code → `tester_ca` revalidation serialized.

## Expected outcome

- Root cause or residual blocker documented with evidence.
- Repair + **instrumentation** committed; `tester_ca` confirms revalidation and whether path is more stable and better instrumented.

## Correction items

- Prior batch removed conflicting `extra` importance; this batch adds diagnostic logging per parent step.

## Questions/escalation rule

- Escalate to global orchestrator if spec or global-step boundaries must change.

## File inventory

- Populated from `researcher_code` / `coder_auto` delivery for this batch (expect `cst_save_tree` command and/or `tree_saver` save path).

## Specialist routing

- `researcher_code`: insertion points and safe logging pattern (no reserved `extra` keys).
- `coder_auto`: implement repair/instrumentation; commit.
- `tester_ca`: MCP-only `vast_srv` `cst_load_file` → `cst_save_tree` revalidation.
