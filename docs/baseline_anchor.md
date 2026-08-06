# AI Editor CAS Baseline Anchor Record

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Plan: `24271419-4dc6-44f2-8613-f350310f5c12`, step G-026/T-001/A-002
(`baseline-anchor-record`).

## 1. Purpose

This record declares the single, immutable AI Editor CAS baseline that all
compatibility analysis and ported contract tests for the new tree engine
(`src/tree_engine/`) must target, per requirement `p004`. It is the
authoritative pin: any downstream document, test, or check that needs "the
baseline commit" points here, not to a value copied independently.

## 2. The pinned baseline

- **Branch:** `cas`
- **Commit:** `8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a`
- **Commit message (subject):** `Bump version to 1.0.83`
- **Author:** Vasiliy Zdanovskiy <vasilyvz@gmail.com>
- **Commit date:** 2026-07-30 (`2026-07-30T12:42:20+03:00`)
- **Project version at this commit:** `1.0.83` (`pyproject.toml`,
  bumped from `1.0.82` by this exact commit)

All compatibility analysis and every ported contract test target exactly
this revision. A later change to `cas` is a separate, explicitly approved
baseline update, never a silent edit of this record or of the value it
pins.

## 3. How this was measured

Every value above was obtained by running a command against the repository
history, not copied from the plan text unverified. Commands were run from
worktree `/home/vasilyvz/projects/tools/ai_editor_wt/j-docs-baseline`
(branch `exec/j-docs-baseline`, fast-forwarded onto `local` at commit
`a62201d` before this record was written).

| # | Fact | Command | Result |
|---|------|---------|--------|
| 1 | Commit sha, subject, author, date | `git show -s --format='%H%n%s%n%ad%n%an' --date=short 8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` | `8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` / `Bump version to 1.0.83` / `2026-07-30` / `Vasiliy Zdanovskiy` |
| 2 | Full timestamp | `git show 8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a --stat` | `Date: Thu Jul 30 12:42:20 2026 +0300` |
| 3 | Commit is the tip of `cas` | `git rev-parse cas` vs `git rev-parse 8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` | both resolve to `8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` — the baseline commit is exactly the current head of `cas`, not just an ancestor |
| 4 | `cas` contains the commit | `git branch -a --contains 8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` | lists `cas` (plus this worktree's `exec/*` lineage, all descended from it) |
| 5 | Version bump content | `git show 8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a -- pyproject.toml` | `-version = "1.0.82"` / `+version = "1.0.83"` |
| 6 | Current checkout descends from baseline | `git merge-base --is-ancestor 8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a HEAD` | exit 0 — confirmed ancestor of this worktree's `HEAD` (`a62201d`) |

## 4. Independent corroboration in the codebase

`pipeline/checks/check_boundary.py` (the mechanical enforcer of the C-001
`PackageBoundary` contract, requirement `p003`) independently hard-codes
the same commit as its own reference point:

```
BASELINE_COMMIT = "8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a"
```

This was read directly from the file, not assumed. Running the check live
against this worktree confirms it is wired up and passing:

- Command: `python -c "from pipeline.checks import check_boundary; print(check_boundary.check_boundary())"` (with `PYTHONPATH=src`, using
  `/home/vasilyvz/projects/tools/ai_editor/.venv/bin/python`)
- Result: `CheckResult(status=<CheckStatus.PASS: 'pass'>, message='no
  PackageBoundary violations across 50 module(s) under src/tree_engine
  (baseline 8fb05d1f4cfa)', output='')`

The module count (50) was cross-checked independently with
`find src/tree_engine -type f -name "*.py" | wc -l`, which also returned
50. For reference, `find ai_editor -type f -name "*.py" | wc -l` (the
legacy code this baseline anchors against) returned 319.

Note: the pipeline CLI's own `list`/dispatch entry point
(`python -m pipeline.cli list`) reported "no checks registered" at the time
of this measurement — the check module was not auto-discovered through
that entry point in this worktree. This is recorded as observed, not
papered over; it does not change the fact that `check_boundary()` itself
runs and passes when invoked directly, and it is out of scope for this
single-file record to fix.

## 5. Supporting environment facts (measured, informational only)

These do not change the baseline pin; they record the state of the
environment the pin was verified in, since the plan's own dependency
pins (`p032`) turned out to be partly wrong and needed correction here per
the task laws.

| Package | Measured version | Command |
|---|---|---|
| `tree-sitter` | `0.25.2` | `pip show tree-sitter` |
| `tree-sitter-bsl` | `0.1.6` | `pip show tree-sitter-bsl` |
| `libcst` | `1.8.6` | `pip show libcst` |
| Python interpreter | `3.14.4` | `python --version` (`.venv/bin/python`) |

The plan text (requirement `p032`) states tree-sitter-bsl `0.1.6` requires
"the supported tree-sitter 0.24.x branch." The installed `tree-sitter` is
`0.25.2`, not `0.24.x`. This is a discrepancy between the plan's stated
dependency pin and the environment actually installed and in use; it is
recorded here as measured fact, not silently reconciled. The pairing was
then exercised rather than argued about: `tree-sitter 0.25.2` with
`tree-sitter-bsl 0.1.6` parses real 1C sources and renders them back
byte-identically, including a 1.1 MB module of 127,719 nodes, so the pin
that actually works is `0.25.x`. The plan's `0.24.x` is the wrong number
(0.24 speaks ABI 13-14 while this grammar needs 15) and the packaging step
must record `0.25.x`, not the plan's value. `libcst` is
`1.8.6`, not the `1.9.x` the plan states; likewise recorded as measured,
not corrected here.

Full test suite, run against this worktree with the command specified for
this unit:

```
PYTHONPATH=src /home/vasilyvz/projects/tools/ai_editor/.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

Result: `1971 passed, 26 skipped, 6 xfailed in 68.84s (0:01:08)`.

This confirms the suite is green in the environment this baseline record
was authored in; it is not itself part of the baseline pin (the pin is the
commit identity in section 2), it corroborates that the anchored state is
usable.

## 6. Immutability and update discipline

- The baseline commit `8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` is
  **immutable**. It is not rewritten, rebased, or reinterpreted.
- This document, `docs/baseline_anchor.md`, is the **single source of
  truth** for the pin. Any other document, check, or test that needs the
  baseline commit reads it from here (or from a value that is itself
  verified against this record); no independent copy is authoritative.
- Any change to the pinned commit is a **separate, explicitly approved
  baseline update**. Such an update:
  - is visible in version-control history as its own commit that edits
    this file (never a silent edit that leaves no trace of the old
    value — the diff itself is the approval record);
  - is authorized by the plan owner before the file changes, not
    inferred by an executing agent from repository state;
  - restates the full measurement procedure in section 3 against the new
    commit — a baseline update is not valid until it is re-measured, not
    just re-typed.
- `pipeline/checks/check_boundary.py`'s `BASELINE_COMMIT` constant (section
  4) must be updated in the same change as this file when the baseline
  moves, so the mechanical check and this record never diverge silently.

## 7. Unmeasured items

None of the facts required by this step's verification criteria (branch,
commit, commit message, date, version, immutability statement, update
discipline, single-source-of-truth statement) were left unmeasured; all
were obtained by the commands in section 3. Section 5's ABI-compatibility
question (whether `tree-sitter` 0.25.2 is safe for `tree-sitter-bsl`
0.1.6's stated `0.24.x` requirement) is explicitly left unresolved here —
answering it needs a BSL parse/round-trip run, not a metadata read, and is
out of scope for this single-file record.
