# Verification Task: Plan Consistency Check

**Plan:** `docs/plans/2026-05-18-tree-sidecar/`  
**Standards:** `docs/plans/2026-05-18-tree-sidecar/` does not yet contain standard files — use the project-level standards from the project context.

## Your role

You are a **verification model**. Your sole job is to run cycle_1 and cycle_2
of the consistency verification standard against the plan artifacts listed below.
You do not implement, plan, or write code. You read, check, and report findings.

## Files to read (mandatory, in this order)

Read every file completely before starting checks. Show `total_lines` for each
after reading.

1. `docs/plans/2026-05-18-tree-sidecar/source_spec.md` (HRS)
2. `docs/plans/2026-05-18-tree-sidecar/spec.yaml` (MRS)
3. `docs/plans/2026-05-18-tree-sidecar/G-001-tree-node-and-sidecar/README.yaml`
4. `docs/plans/2026-05-18-tree-sidecar/G-002-source-parsers/README.yaml`
5. `docs/plans/2026-05-18-tree-sidecar/G-003-sha-sync-and-session/README.yaml`
6. `docs/plans/2026-05-18-tree-sidecar/G-004-universal-file-integration/README.yaml`
7. `docs/plans/2026-05-18-tree-sidecar/G-005-tests/README.yaml`

Use `universal_file_preview` to read YAML files and `get_file_lines` to read
the `.md` file and verify specific line ranges.

## Verification procedure

### Cycle 1 — Source-to-Machine Alignment

For every concept in `spec.yaml`:

- **c1**: locate the `source_ranges` lines in `source_spec.md` and confirm they
  actually justify what the concept claims. Report any mismatch.
- **c2**: for every binding line of `source_spec.md` (all lines outside
  `<!-- non-binding -->` blocks), confirm at least one concept covers it.
  Report uncovered lines.
- **c3**: confirm every relation type is one of the seven allowed:
  `uses`, `owns`, `implements`, `extends`, `depends_on`, `produces`, `consumes`.
- **c4**: confirm every concept qualifies as an entity with behaviour or
  invariant (not a plain property of another entity).

Cycle 1 must be GREEN before proceeding to Cycle 2.

### Cycle 2 — Global Step Triple Autonomy

For every G-step (G-001 through G-005), reading `source_spec.md + spec.yaml +
G-NNN/README.yaml` together as the triple:

- **c5**: every concept_id listed in the G-step exists in `spec.yaml`.
- **c6**: every `source_ranges` entry in the G-step points to lines that are
  relevant to that step's scope.
- **c7**: a reader of the triple can name every entity the step creates or
  modifies and every action it performs, without reading sibling G-steps.
- **c8**: `depends_on` expresses execution order only; no cross-step content
  references in the description text.
- **c9**: description adds tactical detail beyond what is already in
  `source_spec.md` or `spec.yaml`; no bare paraphrase.

After all five G-steps, run:

- **I1a**: union of all concepts across G-steps == all concepts in `spec.yaml`.
- **I1b**: union of all relations across G-steps covers all relations in `spec.yaml`.
- **I1c**: union of all `source_ranges` across G-steps covers all binding lines
  of `source_spec.md`.

## Output format

Report findings in a table:

| ID | Cycle | Check | Severity | Description |
|----|-------|-------|----------|-------------|
| F-NN | C1/C2 | c1..c9/I1a..c | High/Medium/Low | exact description |

If no findings: state `Cycle 1: GREEN` and `Cycle 2: GREEN` explicitly.

If findings exist: list them, state which cycle is blocked, and propose the
minimal correction for each finding.

## Zero-trust rule

Do not rely on memory of any prior reading. Re-read each file from disk before
each check pass. Every claim must cite the exact line numbers from the files.
