<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# `docs/agents/` file index

| File | Contents |
|------|----------|
| [`universal_project_context.md`](universal_project_context.md) | Map → `PROJECT_RULES.md` (Profile + sections 1–5). |
| [`project_overlay.md`](project_overlay.md) | This repository: paths, server/test_data rules, restrictions. |
| [`common_agent_rules.md`](common_agent_rules.md) | Shared rules for all hierarchy subagents. |
| [`formal_interaction_protocol.md`](formal_interaction_protocol.md) | Canonical inter-agent message types, fields, states, escalation classes, and closure rules. |
| [`../PROJECT_RULES.md`](../PROJECT_RULES.md) | Profile (concrete values), `CR-*`, `LAYOUT-*`, `NAME-*`. |
| [`MAINTAINERS.md`](MAINTAINERS.md) | Human-only fork notes (do not load into agents). |
| `.cursor/agents/` (repo root) | Cursor subagent definitions (`orchestrator_debug` / `orchestrator_tactical_debug` for informal work). Includes **`tester_ca`** — MCP-only programmer–tester for **`test_data/`** and server-watched projects, **`conscience`** — pre-handoff reviewer for task-to-solution alignment, and **`code_checker`** — tactical post-test conformity reviewer for scope/minimal-diff/architecture checks. |
| `spec_*.md` | Optional per-role long specs if present. |
