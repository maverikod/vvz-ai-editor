<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Formal inter-agent interaction protocol

This document defines the **canonical communication contract** for the multi-agent hierarchy used in this template.

The purpose of the protocol is to prevent role drift, hidden scope expansion, silent assumption-making, and untraceable side effects.

## 1. Why this protocol exists

The hierarchy is intentionally split by abstraction level:

- global orchestrator — strategy and global sequencing only
- tactical orchestrator — tactical coordination only
- planner — atomic decomposition only
- specialists — execution or verification only

Without a formal protocol, agents tend to:

- absorb work from neighboring roles
- hide blockers behind improvisation
- expand scope under the pretext of “helpfulness”
- return vague free-form text instead of actionable status

This protocol makes every handoff explicit, auditable, and bounded.

## 2. Canonical message families

## Meaning-level escalation rule

A lower layer must not invent missing meaning.

If a packet cannot be completed because of ambiguity in intent, scope, source priority, architecture allowance, or task interpretation, the receiver must emit `TASK_ESCALATION`, not improvise.

This rule applies to:
- tactical orchestrator
- planner
- coder
- tester
- researchers
- code checker
- conscience

Only the global orchestrator may resolve meaning-level uncertainty.


Every inter-agent interaction belongs to one of these message families.

### 2.1 `TASK_ASSIGN`

Downward delegation. Used to assign work to a lower layer or specialist.

Mandatory meaning:

- work starts only after a valid `TASK_ASSIGN`
- the receiver must stay within its stated scope
- missing fields are a blocker, not an invitation to guess

### 2.2 `TASK_RESULT`

Upward completion packet. Used when the assigned work unit is finished or as finished as possible within scope.

Mandatory meaning:

- the receiver gets a bounded result, not a narrative
- the parent can decide next steps without re-reading the whole branch
- outputs, checks, and risks are explicit

### 2.3 `TASK_BLOCKED`

Blocking condition packet. Used when the assigned work cannot continue safely.

Mandatory meaning:

- blockers are reported immediately
- the receiver must not substitute missing decisions with improvisation
- the parent must resolve or reroute

### 2.4 `TASK_RETURN`

Return-for-revision packet. Used when a downstream result fails a gate.

Typical producers:

- tester → coder
- code checker → coder
- conscience → orchestrator or tactical orchestrator
- tactical orchestrator → planner or specialist

### 2.5 `TASK_ESCALATION`

Escalation packet for policy, scope, hierarchy, or dependency violations.

Use this when the issue is not merely “blocked”, but needs a deliberate decision from the parent layer.

### 2.6 `TASK_CLOSE`

Formal closure packet. Used when the work unit is genuinely closed and all required gates passed.

## Execution questions vs meaning questions

### Execution questions
May be resolved below the global layer when already inside approved boundaries.

Examples:
- which file to change within assigned scope
- which researcher or tester is needed
- ordering of already-approved subtasks
- whether a local packet satisfies format requirements

### Meaning questions
Must be escalated upward.

Examples:
- what the user intended
- whether conflicting sources should be reconciled one way or another
- whether a scope expansion is justified
- whether architecture change is permitted
- whether a task should be reinterpreted

If there is doubt about which category applies, treat it as a meaning question and escalate.

## Branch-local context rule

Each lower-layer receiver should receive only the context needed for its branch.

The minimum packet must preserve:
- root goal
- parent chain IDs
- local objective
- constraints
- forbidden actions
- done criteria
- escalation path

The full project history must not be forwarded by default when a branch-local packet is sufficient.

## 3. Shared mandatory fields

All protocol messages must carry traceability fields.

Required shared fields:

- `message_type`
- `id`
- `parent_id`
- `goal_id`
- `sender_role`
- `receiver_role`
- `status`
- `objective` or `summary` depending on message family
- `constraints`
- `evidence`
- `next_action` or `requested_resolution` when applicable

Level-specific IDs must also be used where applicable:

- `step_id` for global step
- `task_id` for tactical task
- `atomic_step_id` for planner/coder/tester scope

## 4. Traceability and ID discipline

Recommended prefixes:

- `G-001` — global step
- `T-001.01` — tactical task under the global step
- `A-001.01.03` — atomic step under the tactical task
- `R-...` — result message
- `I-...` — incident, escalation, or deviation message

The exact format may vary, but the mapping to the tree must stay stable.

Every artifact produced by the branch should be attributable to the message tree.

## 5. Fixed statuses

Use these canonical statuses:

- `planned`
- `in_progress`
- `done`
- `blocked`
- `failed`
- `returned_for_revision`
- `verified`
- `closed`

Do not invent synonyms such as “almost done”, “green”, “kinda blocked”, or “more or less complete”.

## 6. Downward protocol by layer

### 6.1 Global orchestrator → tactical orchestrator

The global layer transmits meaning and boundaries, not implementation.

Required fields in practice:

- `goal`
- `step_id`
- `boundaries`
- `definition_of_done`
- `constraints`
- `priority`
- `artifacts_in`
- `artifacts_out`

The global orchestrator must **not** send atomic instructions or code-edit directives.

### 6.2 Tactical orchestrator → planner / specialists

The tactical layer converts the global step into tactical work packets.

Required fields in practice:

- `task_id`
- `parent_step_id`
- `role`
- `objective`
- `inputs`
- `allowed_actions`
- `forbidden_actions`
- `expected_output`
- `acceptance_checks`
- `escalation_rule`

The tactical orchestrator is responsible for ensuring that each receiver sees only the work slice relevant to its role.

### 6.3 Planner → coder / downstream execution sequence

The planner creates atomic execution units and dependency order. It does not code.

Its `TASK_ASSIGN` packets must provide:

- single atomic step scope
- exact inputs
- exact allowed output area
- no architecture invention
- explicit dependency context

## 7. Upward protocol by role type

### 7.1 Planner upward result

Must report:

- atomic steps list
- dependencies
- what can run in parallel
- what blocks execution

### 7.2 Coder upward result

Must report:

- exact files changed
- exact symbols or behaviors implemented
- what was deliberately left untouched
- local risks or assumptions encountered

### 7.3 Tester upward result

Must report:

- what was run
- what passed
- what failed
- whether the failure is reproducible
- whether the issue is implementation or environment

### 7.4 Researcher upward result

Must report:

- findings
- evidence or sources
- conclusion
- confidence level
- open questions

### 7.5 Documentation writer upward result

Must report:

- documents changed
- sections added or updated
- mapping to plan/code/task context

### 7.6 Conscience / checker upward result

Must report:

- gate reviewed
- verdict
- exact violations or `None`
- what must change before proceeding

## 8. Escalation classes

These classes must not be buried in prose.

### 8.1 `missing_dependency`

A required artifact, decision, access, or result is missing.

### 8.2 `conflict`

Instructions conflict across levels or artifacts.

### 8.3 `deviation_detected`

Observed work diverges from the declared plan or scope.

### 8.4 `scope_breach_attempt`

A role or branch tries to add unrequested behavior, compatibility, fallback, architecture change, or unrelated cleanup.

### 8.5 `policy_violation`

A hierarchy, repository, security, or role-boundary rule would be violated.

## 9. Action-permission model

Every role must act under both:

- a **positive scope** — what it may do
- a **negative scope** — what it must not do

The protocol is therefore not complete without `allowed_actions` and `forbidden_actions` in assignment packets.

This is what prevents role collapse.

## 10. Anti-self-expansion rule

If an agent notices a useful improvement outside scope, it must not “just do it”.

It must return an `improvement_candidate` block with:

- `candidate`
- `why_not_in_scope`
- `risk_if_done_now`

This keeps the branch stable while preserving useful observations.

## 11. Return-for-revision contract

A `TASK_RETURN` must be specific enough for the receiver to act without guessing.

Required fields:

- `return_reason`
- `evidence`
- `required_changes`
- `keep_unchanged`
- `recheck_needed`

This prevents the common failure mode where a result is rejected but the implementer does not know what to preserve.

## 12. Closure rule

A branch unit may be marked closed only when:

- required lower-level work completed
- required gates passed
- unresolved blockers are absent
- final artifacts are identified
- the closure basis is explicit

“Looks done” is not enough.

## 13. Recommended templates

The canonical message templates are defined in [`common_agent_rules.md`](common_agent_rules.md) section A17 and must be reused by role files.

## 14. How role files embed this protocol

Each role file should explicitly define:

- what `TASK_ASSIGN` it may receive
- what `TASK_RESULT` it must return
- what events force `TASK_BLOCKED`
- what events force `TASK_ESCALATION`
- what it may treat as closure

This template now appends those role-local protocol sections directly into the agent role prompts.
