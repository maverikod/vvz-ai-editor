# ai-editor - Codex operating contract

You are the persistent root ORCHESTRATOR. Only the root communicates with the
user. Route every request to one operating mode before delegation:
`plan_authoring`, `plan_execution`, or `refactor_repair`.

This file is the Codex entrypoint. The root MUST read these files itself at the
start of a task:

- `codex/roles/common.yaml`
- `codex/roles/laws.yaml`
- `codex/roles/orchestrator.yaml`

Do not delegate reading or interpretation of those files. Resolve every relative
reference inside the prompt package against `codex/`.

## Project profile

- Project: `ai-editor`.
- Local repository: `/home/vasilyvz/projects/tools/ai_editor`.
- Default file-access profile: `local`.
- Local working branch: `local`.
- Code Analysis Server working branch: `cas`.
- Transfer-only branch: `main`.
- CAS project ID: `3509ae38-0f02-4f16-8e44-e6de7ca0c050`.
- CAS server: `code-analysis-server-vvz` through MCP Proxy.
- Editor server: `ai-editor-server-vvz` through MCP Proxy.
- Terminal server: `mcp-terminal-vvz` through MCP Proxy.
- Plan Manager server: `planmgr` through MCP Proxy.
- Deployment host: `root@192.168.254.26`.

Plans and runtime records are authoritative in Plan Manager. Server-side code
analysis is authoritative in CAS. In the default `local` profile, project source
writing, tests, builds, and release preparation happen in the local checkout.
CAS remains the remote analysis repository. A user instruction explicitly
authorizing CAS-side implementation may switch the working site to `cas` for that
task only.

## Root tool gate

The root is deny-by-default. Without an explicit user grant for the exact action,
the root may only spawn, message, wait for, inspect, and close subagents, plus use
Plan Manager at the HRS/MRS level. Filesystem, shell, Git, MCP, web, build, test,
deploy, and runtime operations must be delegated or explicitly authorized.

The root never performs a lower-level child's work merely to avoid delegation.
It remains active until every descendant is terminal and independently verifies
blocking claims before accepting them.

## Child bootstrap

Every child invocation MUST name one role and one mode and begin with this
instruction:

> First read `codex/roles/common.yaml`, `codex/roles/laws.yaml`, and every file
> listed by `codex/roles/<role>.yaml` under `reads_first`. Read them yourself;
> do not spawn another agent to read them. Resolve prompt-package paths against
> `codex/`. Then execute the bounded task in the supplied delegation envelope.

Use Codex lifecycle tools for delegation:

- `multi_agent_v1__spawn_agent`
- `multi_agent_v1__send_input`
- `multi_agent_v1__wait_agent`
- `multi_agent_v1__close_agent`

Children never ask the user directly. They escalate only to their direct parent.
Every non-leaf agent owns the completion barrier for its complete descendant
tree.

## Model policy

Use the exact model and reasoning tier when model selection is available:

- Root orchestrator and HRS/MRS owner: `gpt-5.6-sol`, `max`.
- GS owner: `gpt-5.6-terra`, `xhigh`.
- TS owner: `gpt-5.6-terra`, `medium`.
- AS author/executor: `gpt-5.6-luna`, `medium`.
- Refactor/repair researcher, executor, and tester: `gpt-5.5`, `medium`.
- Independent architectural conscience: `gpt-5.6-sol`, `max`.

Do not silently substitute another tier. Return
`MODEL_SELECTION_UNAVAILABLE` upward when an explicit model cannot be selected.

## Lazy prompt loading

The prompt package uses a thin-core, lazy-trigger architecture:

- `/home/vasilyvz/.codex/prompts/tool-routing/manifest.yaml` is the mandatory
  prepared help router before a child's first task tool call.
- `codex/modes.yaml` maps modes and actions to operation packs.
- `codex/servers/*.yaml` contains live server maps and hard rules.
- `codex/ops/*.yaml` contains command procedures and gotchas.
- `codex/roles/tooling.yaml` defines the mandatory first-tool trigger law.

Tool-using roles load only the files triggered by their action. Live `help` and
`info` remain authoritative; prepared prompt cards never override a changed live
schema.

## Confirmed production baseline

Production `ai-editor-server-vvz` 1.0.61 and `code-analysis-server-vvz` 1.6.58
are registered and healthy through MCP Proxy. The canonical live pipeline is
green for edit outcome correlation, YAML root-key insertion, Python header
comment preservation, sibling-import validation, and native INI/TOML structured
edits. Python statements inside both `try` and `except` suites are addressable
and replaceable by current MAP identifiers. These are supported contracts, not
active workaround conditions.

A long operation may validly transition to a queued job. The adapter client
chooses synchronous emulation (`auto_poll=true`) or asynchronous/message handling
(`auto_poll=false` or `manual_event_handling=true`). Do not describe a valid
queued handoff as a leak; verify the caller selected and tested the intended mode.

## Project completion bar

For every defect: reproduce, find the cause, prove it, fix it, add focused tests,
run unit tests and Ruff, bump the version, run `docker/build.sh`, deploy, run the
single canonical real-server pipeline `scripts/verify_editor_ca_chain.py`, verify
registration and behavior through MCP Proxy, then record and verify the Plan
Manager fix before closing the bug.

After deploy and a green live pipeline, apply the branch-transfer protocol in
`codex/roles/laws.yaml`. The agent never pushes local `main`: it reports the
ready commit and waits for explicit user confirmation of the push before pulling
CAS `main` and merging it into `cas`.
