# Claude instructions — `code_analysis`

> **Scope:** This file is for claude.ai only. It does not replace or modify `.cursorrules`,
> `docs/PROJECT_RULES.md`, or `docs/agents/` files used by Cursor.
> Cursor rules remain authoritative for the Cursor environment.
> Common ground (CR-*, LAYOUT-*, NAME-*, standards) is described in the existing repo docs —
> this file only adds what is specific to Claude's access method.

---

## Project identity (CR-003)

- **Project slug:** `code_analysis`
- **UUID:** `8772a086-688d-4198-a0c4-f03817cc0e6c`
- **Root path:** `/home/vasilyvz/projects/tools/code_analysis`
- **Venv:** `.venv` at project root

Verify UUID via `list_projects` before any write operation. Missing UUID → stop and report.

## How Claude accesses this project

Claude does **not** have direct filesystem access. All operations go through **MCP-Proxy**:

```
MCP-Proxy URL : https://mcp.techsup.od.ua/mcp
server_id     : code-analysis-server
call pattern  : call_server(server_id="code-analysis-server", command="...", params={...})
```

Additional services reachable through the same proxy:
- `embedding-service` — vector embeddings
- `svo-chunker-prod` — semantic chunking

**Direct HTTP to the backend is forbidden.**
**bash_tool / filesystem tools are forbidden for project file access.**

## Existing rules Claude must respect

The following files in the repo define the canonical standards. Claude reads them via MCP when needed — never overrides them:

| File | Contents |
|------|----------|
| `docs/PROJECT_RULES.md` | CR-*, LAYOUT-*, NAME-*, profile §0 |
| `docs/agents/project_overlay.md` | Repo-specific paths and restrictions |
| `docs/agents/common_agent_rules.md` | Agent hierarchy and protocol |
| `docs/agents/universal_project_context.md` | Universal project context |
| `docs/standards/` | DRIVER_STANDARD, LOG_IMPORTANCE, PARAMS_VALIDATION, etc. |
| `.cursorrules` | Cursor IDE rules — **do not touch** |

## Sibling projects (CR-002) — do not touch without explicit approval

| Project | UUID |
|---------|------|
| `mcp_proxy_adapter` | `4b331a55-72ed-4e4a-ba35-d0f34ad90110` |
| `vast_srv` | `c86dded6-6f93-4fb0-be54-b6d7b739eeb9` |

## Claude-specific workflow rules

| ID | Rule |
|----|------|
| **CL-01** | All reads and writes go through MCP commands only. No bash_tool, no direct filesystem. |
| **CL-02** | For any unfamiliar MCP command — read its `help` first. Never guess parameters. |
| **CL-03** | Before any write: verify UUID via `list_projects`. |
| **CL-04** | Worker lifecycle via `start_worker` / `stop_worker` MCP commands only. |
| **CL-05** | Batch independent read-only calls via `read_only_batch` to minimize round-trips. |
| **CL-06** | Post-edit sequence for code files: `lint_code` → `format_code` → `type_check_code` → `update_indexes`. |
| **CL-07** | Log reads via `view_worker_logs` with `log_id`. |
| **CL-08** | Never hand-edit `data/*.db` — use MCP commands only. |
| **CL-09** | FAISS index managed via `rebuild_faiss` / `revectorize` only. |
| **CL-10** | Do not modify `.cursorrules`, `docs/PROJECT_RULES.md`, or any file under `docs/agents/` except `docs/agents/claude/`. |

## File view and edit workflow

**Trigger:** Before opening, reading, or editing any file — read the full rules:
- View rules: `docs/standards/FILE_VIEW_WORKFLOW.yaml`
- Edit rules: `docs/standards/FILE_EDIT_WORKFLOW.yaml`
- Python XPath in open session: `universal_file_search` — see `docs/commands/file_editing/universal_file_search.md`

Obsolete commands — do not use: `universal_file_save`, `create_text_file`, `replace_file_lines`, `write_project_text_lines`.
## Search and analysis workflow

**Trigger:** Before any search, code lookup, or entity locate operation — read the full rules:
- `docs/standards/SEARCH_WORKFLOW.yaml`
## Terminal workflow

**Trigger:** Before any terminal_session_create or terminal_run call — read the full rules:
- `docs/standards/TERMINAL_WORKFLOW.yaml`
## Pre-task checklist

- [ ] Verify UUID via `list_projects`: `8772a086-688d-4198-a0c4-f03817cc0e6c`
- [ ] Check worker health: `get_worker_status` for `vectorization` + `indexing` + `file_watcher`
- [ ] Check DB: `get_database_status`
- [ ] Confirm scope stays inside this project (CR-002)
- [ ] Plan parallel calls where independent — use `read_only_batch` for research phase
- [ ] CST edits: plan preview pass before apply pass
- [ ] Code edits: plan `lint → format → typecheck → update_indexes` sequence

## Language

- Chat: **Russian (ru)**

## Session log

### 2026-05-06 (UUID 8772a086)

**Done:**

- **Баг #2 XPath в `cst_find_node` [ЗАКРЫТ]** — `//`, `@attr`, `>=/<=/>/< `, `:not()`. 43/43 тестов ✅
- **XPath metadata [ЗАВЕРШЕНО]** — обновлены `descr`, `get_schema().query.description`, `metadata()` в `cst_find_node_command.py` с полным описанием всех 4 XPath-фич и примерами.
- **Баг #3 `kind: range` silent no-op [ЗАКРЫТ]** — fix в `patcher.py`:
  - Причина: ключ `(start_line, end_line)` пользователя не совпадал с `(pos.start.line, pos.end.line)` узла при многострочных операторах (напр. вызов с переносами строк).
  - Fix: `_narrowest_stmt_line_span_containing_range` — находит узкий оператор, чей диапазон строк **содержит** `[us, ue]`; в словарь кладётся разрешённый span узла; нет матча → `unmatched`, без ложного `replaced`.
  - `position_map` резолвится один раз до цикла по ops.
  - 5 регрессионных тестов в `tests/test_cst_module_patcher_range_trivia.py`, 22 в `test_compose_cst_module_ops.py`.

**Open:**

| # | Task | Status |
|---|------|--------|
| #4 | Delete debug files (`debug_classdef_replace.py` etc.) | Pending |
| #5 | Remove legacy tails in `cst_mcp_sandbox_*` | Pending |