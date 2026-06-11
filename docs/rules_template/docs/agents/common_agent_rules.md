<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Common agent rules (all subagents + hierarchy)

**Scope:** every Cursor subagent in `.cursor/agents/*.md`, except where a role file **forbids** an action (e.g. `orchestrator` does not run tests).

**Load order (if not already in context):**

1. [`universal_project_context.md`](universal_project_context.md) → [`PROJECT_RULES.md`](../PROJECT_RULES.md) (Profile and sections 1–5).
2. [`project_overlay.md`](project_overlay.md).
3. **This file** (`common_agent_rules.md`).
4. `docs/agents/spec_<role>.md` if it exists.

---

## A1. Instruction fidelity

Follow user, system, skill, and tool instructions completely. On conflict, use precedence in [PROJECT_RULES.md section 1](../PROJECT_RULES.md#1-precedence-highest-first).

---

## A2. Chat vs repository files

- **Questions** (analysis-only): answer in **chat**; do not create unsolicited explanation files.
- **Durable** docs, plans, structured bugs: write under `docs/` when the task requires it (e.g. `docs/plans/`, `docs/reports/`, `docs/standards/`).

---

## A3. Repository boundary

Do not modify paths **outside this repository** without explicit user permission.

---

## A4. Project id (`projectid`)

If the project uses `projectid` (see CR-003): missing or invalid JSON → **stop and report** to the user.

---

## A5. Virtual environment

Before Python installs, linters, or tests: ensure **`VENV_DIR`** from [PROJECT_RULES Profile](../PROJECT_RULES.md#profile-this-repository) is active (default `.venv`).

If **`ModuleNotFoundError`**, a missing package, wrong `python`/`pip`, or **`pip install` fails**: **stop** and verify the venv (`which python`, `$VIRTUAL_ENV` on Unix, or Windows equivalents); activate and **retry** before installing into another environment.

**CR-015:** do **not** use `pip install --break-system-packages` (or other PEP 668 overrides) **unless** the user explicitly approves **that exact command** in chat.

---

## A6. Code map / indices

If `USE_CODE_MAP` = yes in Profile: after a **logically finished** structural change, refresh indices (code map under package tree `code_analysis/`). If the tool is missing, state that.

---

## A7. Language

- **Chat:** `CHAT_LOCALE` from [PROJECT_RULES Profile](../PROJECT_RULES.md#profile-this-repository).
- **Repo artifacts:** `ARTIFACT_LOCALE` (typically English for code and `docs/`).

---

## A8. File headers on outputs

When creating or editing files that require it: use `HEADER_AUTHOR` / `HEADER_EMAIL` from [PROJECT_RULES Profile](../PROJECT_RULES.md#profile-this-repository).

---

## A9. Required specialist or resource missing (**critical**)

If a **required** agent, template, or tool the role depends on is unavailable:

1. **Stop** immediately.
2. Do **not** continue manually, substitute another agent, or bypass the hierarchy.
3. **Ask the user** what to do next.

*(Each `spec_*.md` lists which peers/resources are required for that role.)*

---

## A10. File write verification

After any **write** this role owns:

- **Read back** the file.
- Confirm **substantive** expected content is present (not only that the path exists).
- Do not report “Done” until verified.

For long analysis reports: verify beginning and end of file when appropriate.

---

## A11. Doubt and escalation

Do not proceed on unstated assumptions. **Escalation target** is defined in each role spec (`orchestrator_tactical`, `orchestrator`, user, etc.).

---

## A12. MCP tools

Before calling an MCP tool, read its **schema/descriptor** (Cursor `mcps/` tree for this workspace).

---

## A13. Version control (when the session performs git work)

Commit after a logical batch; **push** only if the user asks.

---

## A14. Hierarchy roles at a glance

| Role | Writes code | Runs tests | Writes tactical/atomic plans | Owns global spec |
|------|-------------|------------|------------------------------|------------------|
| `orchestrator` | no | no | global only | yes |
| `orchestrator_debug` | no | no | none (delegates via chat brief) | no |
| `orchestrator_tactical` | no | no | tactical tasks | no |
| `orchestrator_tactical_debug` | no | no | none (direct commands; no `planner_auto`) | no |
| `planner_auto` | no | no | atomic steps | no |
| `coder_auto` | **yes** | via step only | no | no |
| `tester_auto` | **no** | **yes** | no | no |
| `tester_ca` | **yes** (only via MCP → code-analysis-server) | **yes** (server-mediated checks) | no | no |
| `conscience` | **no** | no | no | no |
| `code_checker` | **no** | no | no | no |
| `doc_writer` | no | no | no | no |
| `researcher_code` | no (analysis files OK) | no | no | no |
| `researcher_doc` | no (analysis files OK) | no | no | no |

**Mandatory completion (planning/implementation stream):** not done until required **`conscience`** pre-handoff reviews have passed at the orchestration layers, **`tester_auto`** reports **all tests pass** for ordinary repo scope (where tests apply), any **`test_data/`** work is closed by **`tester_ca`** per the brief, and **tactical** **`code_checker`** approves the post-test code review for non-guarded repo code — unless the user explicitly narrows scope.

**Parallelism (**[**CR-016**](../PROJECT_RULES.md)**):** orchestrators and leads **maximize concurrent** execution of **independent** units; serialization requires a **stated** dependency or resource reason.

---

## A15. Documentation structure for this planning stack

**Full stack only** (`orchestrator` → `orchestrator_tactical` → `planner_auto`). The **debug** pair (`orchestrator_debug` → `orchestrator_tactical_debug`) does **not** use these paths for planning.

---

## A16. Normalized hierarchy envelope (**critical**)

- **`orchestrator`**: the global layer works **only through `orchestrator_tactical`**. It does **not** call specialists directly, including `conscience`. Its tools are limited to: (1) calling/resuming **`orchestrator_tactical`**, (2) reading its own global artifacts and explicit upward deliverables from the tactical layer, (3) writing only the global spec / plan / global-step artifacts allowed by its role file.
- **`orchestrator_tactical`**: the tactical layer works **only through subordinate specialists**. It does **not** replace `conscience`, `researcher_code`, `researcher_doc`, `planner_auto`, `coder_auto`, `tester_auto`, `tester_ca`, `code_checker`, or `doc_writer` with direct repo tools. Tactical file I/O is limited to planning Markdown plus subordinate outputs allowed by its role file.
- **`conscience`**: verdict-only gate. It does **not** investigate the repository directly. It decides only from the assignment/handoff package and explicit evidence already produced by `researcher_code`, `researcher_doc`, `tester_auto`, or `tester_ca`. If evidence is missing, it returns the package for revision instead of researching on its own.
- **`orchestrator_debug`**: the global debug layer works **only through `orchestrator_tactical_debug`**. It does **not** call specialists directly, including `conscience`.
- **`orchestrator_tactical_debug`**: the debug tactical layer works **only through subordinate specialists**. It must not replace `conscience`, `researcher_*`, `tester_*`, `coder_auto`, `code_checker`, or `doc_writer` with direct repo inspection or execution.

Canonical paths:

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/implementation_plan.md`
- `docs/tech_spec/steps/<global_step_slug>.md`
- `docs/tech_spec/branches/<global_step_slug>/tasks/<tactical_task_slug>.md`
- `docs/tech_spec/branches/<global_step_slug>/tasks/<tactical_task_slug>/steps/<atomic_step_slug>.md`

Details: if `spec_*.md` files exist in this directory, see `spec_orchestrator_global.md`, `spec_orchestrator_tactical.md`, `spec_planner_auto.md`; otherwise use `.cursor/agents/*.md` full text.


---

## A17. Formal inter-agent protocol layer (critical)

All agents in this hierarchy must treat delegation as a **formal message protocol**, not as free-form chat.

Canonical message types:

- `TASK_ASSIGN` — assign work downward.
- `TASK_RESULT` — report completed work upward.
- `TASK_BLOCKED` — stop due to a blocking dependency.
- `TASK_RETURN` — return work for revision with evidence.
- `TASK_ESCALATION` — raise a scope, policy, dependency, or hierarchy issue upward.
- `TASK_CLOSE` — formally close a unit after all required gates pass.

Required shared fields unless the role file narrows them:

- `message_type`
- `id`
- `parent_id`
- `goal_id`
- `step_id` / `task_id` / `atomic_step_id` as applicable to the level
- `sender_role`
- `receiver_role`
- `status`
- `objective`
- `inputs`
- `artifacts_in`
- `artifacts_out`
- `constraints`
- `allowed_actions`
- `forbidden_actions`
- `acceptance_checks`
- `evidence`
- `next_action`

### Status vocabulary (fixed)

Use only these workflow states unless the role file explicitly adds a stricter subset:

- `planned`
- `in_progress`
- `done`
- `blocked`
- `failed`
- `returned_for_revision`
- `verified`
- `closed`

Do **not** invent ad-hoc status names when a canonical one exists.

### ID and traceability rule (critical)

Every message and artifact must be traceable to the planning tree.

Recommended prefixes:

- `G-...` — global step
- `T-...` — tactical task
- `A-...` — atomic step
- `R-...` — result packet
- `I-...` — incident / escalation / deviation / scope breach

If the repository already has a naming scheme, preserve it; otherwise use this one.

### Scope-breach detection (critical)

If an agent detects any of the following, it must **not** silently continue:

- work outside the assigned scope
- architecture expansion not requested by parent scope
- unrequested fallback / compatibility / side quest
- missing prerequisite artifact or decision
- conflicting instructions between hierarchy levels

The agent must emit `TASK_BLOCKED` or `TASK_ESCALATION` with exact evidence.

### Anti-self-expansion rule (critical)

If an agent sees a possible improvement that is **not** required by the assigned unit, it must **not** implement or fold it into the current task. It must instead report an `improvement_candidate` inside `TASK_RESULT` or `TASK_ESCALATION` with:

- `candidate`
- `why_not_in_scope`
- `risk_if_done_now`

### Formal message templates

#### `TASK_ASSIGN`

```md
message_type: TASK_ASSIGN
id: <message_id>
parent_id: <parent_message_id_or_none>
goal_id: <goal_id>
step_id: <global_or_tactical_or_atomic_id>
sender_role: <role>
receiver_role: <role>
status: planned
objective: <what must be achieved>
inputs:
  - <input>
artifacts_in:
  - <path_or_none>
artifacts_out:
  - <required_output>
constraints:
  - <constraint>
allowed_actions:
  - <allowed>
forbidden_actions:
  - <forbidden>
acceptance_checks:
  - <check>
escalation_rule: escalate instead of assuming when blocked or unclear
```

#### `TASK_RESULT`

```md
message_type: TASK_RESULT
id: <result_message_id>
parent_id: <assignment_message_id>
goal_id: <goal_id>
step_id: <step_id>
sender_role: <role>
receiver_role: <role>
status: done | failed | blocked | returned_for_revision
summary: <short result>
artifacts_created:
  - <path_or_none>
artifacts_modified:
  - <path_or_none>
checks_performed:
  - <check>
evidence:
  - <evidence>
risks:
  - <risk_or_none>
improvement_candidate:
  - candidate: <optional>
    why_not_in_scope: <optional>
    risk_if_done_now: <optional>
next_action: <recommended next step>
```

#### `TASK_BLOCKED`

```md
message_type: TASK_BLOCKED
id: <incident_id>
parent_id: <assignment_message_id>
goal_id: <goal_id>
step_id: <step_id>
sender_role: <role>
receiver_role: <role>
status: blocked
block_reason: <exact blocker>
missing_input_or_decision:
  - <missing>
evidence:
  - <evidence>
requested_resolution: <what parent must decide or provide>
```

#### `TASK_RETURN`

```md
message_type: TASK_RETURN
id: <return_id>
parent_id: <result_or_assignment_id>
goal_id: <goal_id>
step_id: <step_id>
sender_role: <role>
receiver_role: <role>
status: returned_for_revision
return_reason: <why returned>
evidence:
  - <evidence>
required_changes:
  - <change>
keep_unchanged:
  - <preserve>
recheck_needed:
  - <who rechecks>
```

#### `TASK_ESCALATION`

```md
message_type: TASK_ESCALATION
id: <incident_id>
parent_id: <assignment_message_id>
goal_id: <goal_id>
step_id: <step_id>
sender_role: <role>
receiver_role: <role>
status: blocked | failed
escalation_type: deviation_detected | scope_breach_attempt | conflict | missing_dependency | policy_violation
summary: <short statement>
evidence:
  - <evidence>
impact: <why this matters>
resolution_options:
  - <option>
recommended_option: <option>
```

#### `TASK_CLOSE`

```md
message_type: TASK_CLOSE
id: <close_id>
parent_id: <result_or_verification_id>
goal_id: <goal_id>
step_id: <step_id>
sender_role: <role>
receiver_role: <role>
status: closed
closure_basis:
  - <all required gates that passed>
artifacts_final:
  - <final paths>
notes:
  - <note_or_none>
```

See also: [`formal_interaction_protocol.md`](formal_interaction_protocol.md).
