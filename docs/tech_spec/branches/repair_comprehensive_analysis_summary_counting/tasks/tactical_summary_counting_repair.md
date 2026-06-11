<!--
Tactical task — parent global step: repair_comprehensive_analysis_summary_counting
Status: closed per specialist evidence (researcher_code, coder_auto, tester_auto, tester_ca).
-->

# Tactical Task: Repair comprehensive_analysis summary counting (batch)

## Purpose

Restore trust in `comprehensive_analysis` batch summaries when the analysis path completes successfully but legacy counters (`files_analyzed` / `files_skipped`) looked implausible alongside per-file progress. The concrete fix adds explicit breakdown keys and counts previously invisible skip paths so totals reconcile with `files_total`.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/repair_comprehensive_analysis_summary_counting.md`

## Scope

**Included:** Server-side batch path only (`execute_batch.py`, `batch_summary.py`); pytest under `tests/` for summary keys and invariants; MCP revalidation on `vast_srv` after server restart.

**Excluded:** Broad `vast_srv` source fixes; edits under `test_data/` except via `tester_ca` revalidation (no direct repo edits there); single-file `execute_single.py` extended keys (unchanged by design).

## Boundaries

- Do not change global `tech_spec.md` or global step files from this tactical file (orchestrator-owned).
- `coder_auto` / `tester_auto` must not touch `test_data/vast_srv` code paths.

## Dependencies

none

## Parallelization note

Research → code → restart/tests → MCP revalidation is sequential.

## Expected outcome

1. Batch `summary` includes `files_skipped_up_to_date` and `files_skipped_unreadable_or_missing`.
2. Invariant for full scans: `files_analyzed + files_skipped + files_skipped_unreadable_or_missing == files_total`.
3. Legacy keys unchanged in meaning.
4. `vast_srv` queued `comprehensive_analysis` completes; arithmetic holds on live summary.

## Correction items

none (greenfield repair)

## Questions/escalation rule

Escalate to global orchestrator if product requires renaming legacy `files_skipped` or changing progress UX strings (separate from summary dict).

---

## Specialist evidence (execution record)

| Role | Outcome |
|------|---------|
| researcher_code | Counters built in `run_batch()` + `build_batch_summary()`; progress before gate caused perceived mismatch; missing/stat/read `continue` paths skipped both legacy counters. |
| coder_auto | Added `files_skipped_unreadable_or_missing` increments on early `continue` paths; `files_skipped_up_to_date` mirrors mtime gate skips; extended `build_batch_summary()`; tests `tests/test_comprehensive_analysis_batch_summary.py` (3 passed). |
| tester_auto | `server_manager_cli restart` exit 0, pid 547017; pytest batch summary file 3 passed. |
| tester_ca | `health` OK; job `comprehensive_analysis_ad0b04c7` completed; summary keys present; `0+598+0==598`. |

## File inventory (as implemented)

| action | path | purpose |
|--------|------|---------|
| modify | `code_analysis/commands/comprehensive_analysis_mcp/execute_batch.py` | Trust counters + logging |
| modify | `code_analysis/commands/comprehensive_analysis_mcp/batch_summary.py` | New summary keys + docstring invariant |
| create | `tests/test_comprehensive_analysis_batch_summary.py` | Regression tests |

## Checkpoint

**Broad `vast_srv` fix phase:** May resume from a **metrics/summary** perspective; this step did not unblock non-summary `vast_srv` defects.
