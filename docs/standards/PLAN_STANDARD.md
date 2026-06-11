# Plan Standard

**Version:** 1.0  
**Author:** Vasiliy Zdanovskiy  
**Applies to:** All development plans in `docs/plans/`

---

## 1. Purpose

This standard defines how to structure, write, and store development plans so that:

- Any AI model can execute a single atomic step with no more than the spec, the global step, the tactical step, and the atomic step as context.
- Steps are maximally independent — a failure in one does not block others.
- The plan is human-readable at the top levels and machine-executable at the bottom level.
- The directory tree on disk mirrors the logical hierarchy of the plan.

---

## 2. Four-Level Hierarchy

```
Spec (ТЗ)          — what and why. Human readable. OOP-based design.
  Global Step (G)  — independent deliverable. Human readable. 1–10 per plan.
    Tactical Step (T) — operation on a structure. Human readable. 1–50 per G.
      Atomic Step (A)  — one file of code. Machine readable. ≤ 8k tokens.
```

Each level must be self-contained given its parent levels:

| Level | To understand it, reader needs |
|-------|-------------------------------|
| Global | Spec |
| Tactical | Spec + its Global step |
| Atomic | Spec + its Global step + its Tactical step |

---

## 3. Directory Layout

```
docs/plans/<YYYY-MM-DD>-<plan-slug>/
│
├── README.md                        ← Spec (ТЗ): concept, OOP design, invariants
│
├── G-001-<global-step-name>/        ← Global step directory
│   ├── README.md                    ← Global step description (human readable)
│   │
│   ├── T-001-<tactical-step-name>/  ← Tactical step directory
│   │   ├── index.md                 ← Tactical step description (human readable)
│   │   ├── A-001-<atomic-step>.md   ← Atomic step: one file of code
│   │   ├── A-002-<atomic-step>.md
│   │   └── ...
│   │
│   ├── T-002-<tactical-step-name>/
│   │   ├── index.md
│   │   ├── A-001-<atomic-step>.md
│   │   └── ...
│   └── ...
│
├── G-002-<global-step-name>/
│   └── ...
└── ...
```

### Naming rules

- Plan directory: `YYYY-MM-DD-<kebab-slug>` (date = planning date)
- Global step: `G-NNN-<kebab-name>` (NNN = zero-padded 3-digit number, e.g. `G-001`)
- Tactical step: `T-NNN-<kebab-name>` (same numbering within its G)
- Atomic step: `A-NNN-<kebab-name>.md` (same numbering within its T)
- All names lowercase kebab-case, no spaces

---

## 4. Spec (README.md at plan root)

The spec is the authoritative description of what the plan delivers. It is written
before any steps are defined. It follows OOP design order:

```markdown
# <Plan Title>

## Context
Why this plan exists. What problem it solves. Links to ERRORS.md entries if relevant.

## Contract (Invariants)
What the system must guarantee externally after this plan is complete.
These are non-negotiable. List as bullet points.

## OOP Design

### 1. Entities
Named things in the domain. Described in plain text, no code.

### 2. Classification
How entities group and relate. What varies, what is stable.

### 3. Base Classes
Abstract types that capture shared behaviour. Described in plain text.

### 4. Concrete Classes
Specific implementations. One paragraph each. No code.

## Constraints
File size limits, backward compatibility requirements, driver portability, etc.
```

---

## 5. Global Step (G-NNN/README.md)

A global step is an independently deliverable unit. It must:

- Be completable without executing any other global step first
- Produce a verifiable result (tests pass, command works, file exists)
- Be described in plain English with no assumed context beyond the Spec

```markdown
# G-NNN: <Title>

## What this step delivers
One paragraph. What exists after this step that did not exist before.

## Why it is independent
Which other steps depend on it (downstream), which it depends on (upstream, if any).
If it has no upstream dependencies, say so explicitly.

## Acceptance criteria
Bullet list. Concrete and verifiable.

## Tactical steps in this global step
| # | Name | What it does |
|---|------|-------------|
| T-001 | ... | ... |
```

### How many global steps

- Minimum: 1. Maximum: 10.
- Divide into the maximum number of **independent** blocks.
- If two things can be done in parallel by different models, they must be separate global steps.
- If one thing must happen before another, they may be in the same global step or in sequence.

---

## 6. Tactical Step (T-NNN/index.md)

A tactical step is one operation on one or more structures defined in the global step.
It either:

- **Detailing** — breaks down a complex structure into sub-parts (used when the structure is non-trivial)
- **Operation** — describes one action: create, modify, delete, test, document

```markdown
# T-NNN: <Title>

## Operation type
One of: create / modify / delete / test / document / investigate

## What this step does
One paragraph. Which files or structures are affected and how.

## Inputs
What must exist before this step runs (from Spec, from G-NNN, or from earlier T steps).

## Outputs
What this step produces or changes.

## Atomic steps in this tactical step
| # | File | What it does |
|---|------|-------------|
| A-001 | path/to/file.py | ... |
```

### How many tactical steps

- Minimum: 1. Maximum: 50 per global step.
- One tactical step = one logical operation (create a class, add a method, write tests for X).
- Do not combine unrelated operations into one tactical step.

---

## 7. Atomic Step (A-NNN-name.md)

An atomic step is a machine-executable instruction for writing or modifying **one file**.
It is the only level that contains code or pseudo-code.

### Size constraint

**One atomic step ≤ 8000 tokens** (approximately 500–600 lines of content including code).
If a single file exceeds this, split into A-001-<name>-part1.md, A-002-<name>-part2.md.
Exception: multiple small files of the same module may share one atomic step if total ≤ 8k.

### Required sections

```markdown
# A-NNN: <file path relative to project root>

## Purpose
One sentence: what this file does and why it exists.

## Contract
Public interface: class names, method signatures, return types.
Written as typed Python signatures or equivalent. No implementation.

## Implementation notes
Key decisions, edge cases, constraints the implementor must know.
Not a tutorial — assume the implementor has read the Spec and parent steps.

## Dependencies
Imports required. Which other atomic steps must be complete first.

## Verification
How to confirm this step is done: command to run, assertion to check, output to expect.
```

---

## 8. Plan Authoring Process

A model writing a plan must follow this sequence strictly:

**Step 1 — Write the Spec**  
Write `README.md` at the plan root using the OOP design order:  
context → contract → entities → classification → base classes → concrete classes → constraints.  
No global steps yet.

**Step 2 — Enumerate Global Steps**  
List G-001 through G-NNN (max 10) with one-line descriptions.  
Verify each is independent. If two depend on each other, merge or reorder.  
Do not write tactical steps yet.

**Step 3 — For each Global Step, enumerate Tactical Steps**  
List T-001 through T-NNN (max 50) for that G with one-line descriptions.  
Verify each is a single operation. Do not write atomic steps yet.

**Step 4 — For each Tactical Step, write Atomic Steps**  
Write A-NNN files. One file of code = one atomic step.  
Apply the 8k token limit. Split if needed.

**This sequence is mandatory.** A model must not write atomic steps before
global and tactical steps are enumerated and reviewed.

---

## 9. Independence Rules

A global step is independent if:

1. It can be assigned to a different model/agent than all other global steps
2. Its inputs exist in the repo before the plan starts, OR come only from the Spec
3. Its outputs do not depend on the outputs of other global steps

If rule 3 is violated, the steps must be sequenced (add an explicit dependency
in the README of the downstream step) or merged.

Tactical steps within a global step may have sequential dependencies on each other.  
Atomic steps within a tactical step are assumed sequential unless marked parallel.

---

## 10. Example: minimal plan

```
docs/plans/2026-05-05-buffer-file-api/
├── README.md                          ← Spec
├── G-001-buffer-core/
│   ├── README.md
│   ├── T-001-buffer-model/
│   │   ├── index.md
│   │   ├── A-001-buffer-model.md
│   │   └── A-002-address-model.md
│   └── T-002-buffer-operations/
│       ├── index.md
│       ├── A-001-read-op.md
│       ├── A-002-write-op.md
│       └── A-003-insert-delete-op.md
├── G-002-undo-redo/
│   ├── README.md
│   └── T-001-operation-stack/
│       ├── index.md
│       └── A-001-op-stack.md
└── G-003-flush-and-diff/
    ├── README.md
    └── T-001-flush-with-validation/
        ├── index.md
        └── A-001-flush-command.md
```

---

## 11. What goes where

| Content | Location |
|---------|----------|
| Concept, motivation, OOP design | `README.md` (Spec) |
| What a deliverable is and why | `G-NNN/README.md` |
| What operation to perform | `T-NNN/index.md` |
| Actual code / pseudo-code | `A-NNN-*.md` |
| Cross-cutting notes, audit | `G-NNN/README.md` or Spec |
| Parallelization map | `README.md` appendix or separate `parallelization.md` at plan root |

---

## 12. Relation to existing plans

Existing plans in `docs/plans/` predate this standard and use varied structures.
They are not required to be retrofitted.  
New plans created after this standard is merged must follow it.

When referencing an existing plan from a new plan, note that it may not follow
this structure and read its own README for navigation.
