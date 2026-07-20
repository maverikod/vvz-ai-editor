# ai-editor Codex prompt package

`AGENTS.md` is the entrypoint. This directory contains the lazily loaded role,
mode, server, and operation cards used by that contract.

## Layout

- `modes.yaml`: exact router for `plan_authoring`, `plan_execution`, and
  `refactor_repair`.
- `roles/common.yaml`, `roles/laws.yaml`, `roles/orchestrator.yaml`: mandatory
  core read by the root.
- `roles/<role>.yaml`: level, authority, model, and escalation contract for one
  child role.
- `servers/*.yaml`: thin maps for the registered MCP services.
- `ops/*.yaml`: lazy procedures loaded only when their trigger matches.

The root and every child must read referenced files explicitly. Relative package
references resolve from `codex/`.

## Project bindings

- Project: `ai-editor`
- Local checkout: `/home/vasilyvz/projects/tools/ai_editor`
- CAS project ID: `3509ae38-0f02-4f16-8e44-e6de7ca0c050`
- CAS: `code-analysis-server-vvz`
- Editor: `ai-editor-server-vvz`
- Terminal: `mcp-terminal-vvz`
- Plan Manager: `planmgr`
- Local working branch: `local`
- CAS working branch: `cas`
- Transfer branch: `main`
- Deployment host: `root@192.168.254.26`

## Models

- Root and HRS/MRS: `gpt-5.6-sol`, `max`
- GS: `gpt-5.6-terra`, `xhigh`
- TS: `gpt-5.6-terra`, `medium`
- AS: `gpt-5.6-luna`, `medium`
- Refactor/repair researcher, executor, tester: `gpt-5.5`, `medium`

Never silently substitute a requested tier. Every non-leaf parent forms one
common context plus one specific delta for each child and owns the complete
descendant completion barrier.

## Tool routing

Before a child's first task tool call, read
`/home/vasilyvz/.codex/prompts/tool-routing/manifest.yaml`, select the
highest-precedence matching trigger, and load only its referenced help cards.
Package cards supplement that router. Live downstream `help` and `info` override
prepared metadata when schemas differ.

Project code is written and verified locally on `local` by default. CAS remains
authoritative for its registered server-side copy and remote analysis. All plan
truth lives in Plan Manager through MCP Proxy.

## Editor baseline

Production `ai-editor-server-vvz` 1.0.61 supports correlated edit outcomes,
YAML root-key insertion, preservation of Python class/def trailing comments,
addressable statements inside `try/except`, sibling-import validation, and native
structured INI/TOML editing. The canonical production pipeline covers every item
except `try/except`, which was additionally verified live through node resolution,
two statement replacements, and preview diff.

Valid queued fallback is normal adapter behavior. A caller selects synchronous
poll-and-unwrap or asynchronous/message handling; queue handoff itself is not a
defect.

## Delivery

For defects, the required chain is: reproduce, identify cause, prove, fix, add
focused unit coverage, run unit tests and Ruff, align versions, run
`docker/build.sh`, deploy to `root@192.168.254.26`, run the single
`scripts/verify_editor_ca_chain.py` production pipeline, verify registration and
changed behavior through MCP Proxy, and record a verified Plan Manager fix.

Build and verify from the active working branch. After success, merge it into
local `main`, report the exact commit, and wait for the user to push. Only after
push confirmation does CAS pull `main` and merge it into `cas`. Direct
`local <-> cas` merges and agent pushes of `main` are forbidden.

## Validation

```bash
python3 -c "import glob,yaml; [yaml.safe_load(open(f)) for f in glob.glob('codex/**/*.yaml', recursive=True)]"
rg -n '\{\{' AGENTS.md codex
```

The second command must return no unresolved placeholders in this project-bound
package.
