# AI Tool Usage Rules

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This document defines rules for AI models on how to use the code analysis server and related tools in this project.

**CRITICAL PRINCIPLE**: **Viewing and editing project files** (Python, JSON, YAML, plain text, and other supported formats) MUST go through the **universal file command family** only:

| Step | Command | Role |
|------|---------|------|
| Inspect / navigate | `universal_file_preview` | Read-only structured view; obtain `node_ref` values for edits |
| Start session | `universal_file_open` | Open file (or create), get `session_id` and `format_group` |
| Search session tree | `universal_file_search` | XPath/CSTQuery on **open session CST tree only** (Python sidecar) |
| Mutate draft | `universal_file_edit` | Apply one or more operations to the in-memory draft |
| Persist | `universal_file_write` | Preview diff, then commit to disk |
| End session | `universal_file_close` | Release session; reconcile sidecar/draft artefacts |

The disk file is **not** updated by `universal_file_edit`. Changes reach disk only after **`universal_file_write` (commit)**.

**Discovery before edit:** use **`fulltext_search`** (exact tokens in the index) and **`semantic_search`** (meaning-based) to get `file_path` and context, then `universal_file_preview` and the edit session. See [§2.9](#29-fulltext-and-semantic-search).

**Deprecated for MCP (do not use)** — removed from server registration; not in `help()`:

- Legacy text: `read_project_text_file`, `write_project_text_lines`, `create_text_file`, `get_file_lines`
- Old per-format editors: `cst_*`, `json_*` tree commands, `list_cst_blocks`, `query_cst`, `cst_apply_buffer`
- Superseded one-shots: `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`

**Multi-line payloads**: For Python (`format_group` **sidecar**), prefer `code_lines` (array of strings) in `universal_file_edit` operations — avoids JSON escaping issues.

**Command parameters (source of truth)**: Project-scoped commands use **`project_id`** (UUID from `list_projects` or the `projectid` file in the project root). Authoritative schemas: `help(server_id="code-analysis-server", command="<name>")` via MCP, or `get_schema()` in code. See [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md), [COMMANDS_INDEX.md](COMMANDS_INDEX.md).

**Command metadata vs schema**: Validation and adapter `help` **schema** come from `get_schema()`. Extended AI fields live in `metadata()` — [standards/METADATA_SCHEMA_STANDARD.md](standards/METADATA_SCHEMA_STANDARD.md). Requires **`mcp-proxy-adapter>=8.10.13`**.

**Project-specific rules**: Code under `test_data/` — [TEST_DATA_AI_RULES.md](TEST_DATA_AI_RULES.md) (server-only read/write for test code).

**Related design**: [commands/file_editing/WORKFLOW.md](commands/file_editing/WORKFLOW.md), [plans/2026-05-16-universal-file-edit/source_spec.md](plans/2026-05-16-universal-file-edit/source_spec.md).

---

## 0. AI Prompt Rules (MANDATORY)

**These rules apply when server `code-analysis-server` is available via MCP Proxy.** When the server is unavailable, notify the user and do not silently edit project files with direct IDE tools unless the user explicitly approves fallback.

### 0.0 Quick Reference (For Prompt Insertion)

**IF server is available:**

1. **View or edit any supported project file → UNIVERSAL FILE COMMANDS ONLY**
   - ✅ **View / discover** → `universal_file_preview` (`project_id`, `file_path`, optional `node_ref`)
   - ✅ **Edit workflow** → `universal_file_open` → (`universal_file_search` optional, Python) → `universal_file_edit` → `universal_file_write` → `universal_file_close`
   - ✅ **Python multi-line** → `code_lines` in `universal_file_edit` (sidecar group)
   - ✅ **Quality after commit** → `format_code`, `lint_code`, `type_check_code`
   - ✅ **Project analysis** → `comprehensive_analysis`, `get_code_entity_info`, etc.
   - ❌ **FORBIDDEN**: `cst_*`, `json_*` tree MCP commands, legacy `read_project_text_file` / `write_project_text_lines` / `create_text_file` / `get_file_lines`
   - ❌ **FORBIDDEN**: `search_replace` / `write` on **existing** project files when the server is available
   - ❌ **FORBIDDEN**: Direct file tools for `test_data/` code (see TEST_DATA_AI_RULES)

2. **Search inside or across files** (read-only, separate from edit session):
   - ✅ **`fulltext_search`** — exact tokens / names in the DB index (FTS5, BM25)
   - ✅ **`semantic_search`** — meaning-similar chunks (embeddings + FAISS)
   - ✅ `fs_grep` — regex on disk when the index is missing or you need raw bytes
   - ✅ `search_ast_nodes`, `find_usages`, `get_ast`, … — structure and references  
   See [§2.9 Fulltext and semantic search](#29-fulltext-and-semantic-search).

3. **Error handling → USER DECISION**
   - Report server errors immediately; wait before using non-server fallbacks.

**Mandatory edit workflow (when server available):**

```
universal_file_preview  →  (optional) navigate with node_ref
universal_file_open      →  session_id, format_group
universal_file_search    →  (optional) XPath on session CST tree — Python sidecar only
universal_file_edit      →  one or more operations (repeat as needed)
universal_file_write     →  preview diff (tree-temp: write_mode=preview; sidecar/text: first call)
universal_file_write     →  commit (tree-temp: write_mode=commit; sidecar/text: second call when lock ready)
universal_file_close     →  release session
format_code / lint_code / type_check_code  →  on committed file
```

### 0.1 Core Principle

- Use server tools when available (validation, backups, handler routing).
- Report ALL errors to the user; do not silently switch to direct file editing.
- **One session per file** until `universal_file_close` (or server restart invalidates `session_id`).

### 0.2 Tool Selection (MANDATORY WHEN SERVER AVAILABLE)

| Task | Command(s) |
|------|----------------|
| See file structure / snippet | `universal_file_preview` |
| XPath search in open Python draft | `universal_file_search` (requires `session_id`) |
| Change file content | `open` → (`search` optional) → `edit` → `write` → `close` |
| Find exact text / symbol names (indexed) | `fulltext_search` |
| Find by meaning / concept | `semantic_search` |
| Find regex on disk (no index) | `fs_grep` |
| Split / extract refactor | `split_file_to_package`, `split_class`, … |
| Format / lint / types | `format_code`, `lint_code`, `type_check_code` |

**NEVER** use direct `search_replace` / `write` on existing tracked project files when the server is available.

### 0.3 Error Handling and Fallback

1. Report exact error, command name, and params to the user.
2. Do **not** auto-fallback to `search_replace` if `universal_file_edit` or `universal_file_write` fails.
3. User decides: retry, fix params, fix code, or approve rare direct edit.

### 0.4 When Direct Tools Are Allowed (EXCEPTIONS ONLY)

- ✅ Creating **new** files **only if** the user approves bypassing the server, or the server is down.
- ✅ Editing **this repository’s** `code_analysis/` package via normal IDE tools (not `test_data/`).
- ✅ Non-project assets (docs outside server scope) when no `project_id` applies.
- ❌ Existing project files under a registered `project_id` when the server is up.

### 0.5 Quick Decision Tree

```
Is code-analysis-server available?
├─ NO  → Notify user → fallback only with approval
└─ YES → Need to read or change a project file?
    ├─ YES → universal_file_preview (read)
    │        universal_file_open/edit/write/close (write)
    └─ NO  → Search / analysis / refactor commands as appropriate
```

---

## 1. Tool Priority Rules

### 1.1 Primary Interface: MCP

**Priority:**

1. ✅ **MCP** — `call_server(server_id="code-analysis-server", copy_number=1, command="...", params={...})`
2. ⚠️ **CLI** — fallback for humans or when MCP is unavailable

Use **`project_id`** in params (from `list_projects`), not host `root_dir`, unless the schema explicitly allows otherwise.

**Example:**

```python
call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="universal_file_open",
    params={
        "project_id": "<uuid-from-list_projects>",
        "file_path": "src/module.py",
    },
)
```

### 1.2 Server Management

Restart after changes under `code_analysis/` or new command registration:

```bash
cd /path/to/code_analysis
source .venv/bin/activate
casmgr --config config.json restart
```

---

## 2. Universal File Edit Workflow

**Canonical docs:** [commands/file_editing/README.md](commands/file_editing/README.md) · [WORKFLOW.md](commands/file_editing/WORKFLOW.md) · [PYTHON_EDIT_SEMANTICS.md](commands/file_editing/PYTHON_EDIT_SEMANTICS.md)

### 2.1 Format groups

`universal_file_open` returns **`format_group`** — it determines how `universal_file_edit` operations are shaped:

| format_group | Typical extensions | Draft model | `node_ref` in preview |
|--------------|-------------------|-------------|------------------------|
| **sidecar** | `.py`, `.pyi`, `.pyw` | `<file>.cst_sidecar` | CST stable UUID |
| **tree-temp** | `.json`, `.yaml`, `.yml` | `<file>.draft` + in-memory tree | JSON Pointer (e.g. `/timeout`) |
| **text** | `.md`, `.txt`, `.rst`, `.adoc`, … | `<file>.draft` | Zero-based line index string |

Always call `help` for the live schema; behaviour is documented in command `metadata()`.

### 2.2 Step 1 — Preview (read-only)

**Command:** `universal_file_preview`

- Works **without** an edit session.
- Omit `node_ref` for root view; pass `node_ref` from a previous response to drill down.
- Use returned **`node_ref`** values as targets in `universal_file_edit` (mapping depends on `format_group` — see §2.3).

```python
call_server(
    command="universal_file_preview",
    params={
        "project_id": "<uuid>",
        "file_path": "config/settings.yaml",
        "node_ref": "/database",  # optional
    },
)
```

### 2.3 Step 2 — Open

**Command:** `universal_file_open`

- Returns `session_id`, `format_group`, and related session metadata.
- Optional `create: true` when creating a new file (check schema).
- Sessions are lost on **server restart** — reopen if needed.

### 2.3b Step 2b — Search session tree (optional, Python sidecar)

**Command:** `universal_file_search`

- **Scope:** only the in-memory CST tree bound to `session_id` — not the project, not disk, not the index.
- **Format:** Python sidecar (`.py` / `.pyi` / `.pyw`) with structural editing; JSON/YAML/text sessions return `UNSUPPORTED_FORMAT`.
- **Use when:** you need CSTQuery / XPath over the **current draft** (e.g. `//FunctionDef[name='foo']`, `ClassDef//FunctionDef`) instead of manual drill-down via preview.
- **Results:** each match has `node_ref` (= `stable_id`) — pass as `node_id` in `universal_file_edit`.
- **Not a substitute for:** `fulltext_search`, `fs_grep`, `cst_find_node` (legacy `tree_id`), or `universal_file_preview` outline navigation.

```python
call_server(
    command="universal_file_search",
    params={
        "project_id": "<uuid>",
        "session_id": "<from universal_file_open>",
        "query": "ClassDef[name='Widget']//FunctionDef",
        "include_code": True,
    },
)
```

See [universal_file_search.md](commands/file_editing/universal_file_search.md).

### 2.4 Step 3 — Edit (draft only)

**Command:** `universal_file_edit`

- Params: `project_id`, `session_id`, `operations` (array).
- **Does not write** the canonical file on disk.

**sidecar (Python)** — use `node_id` from preview; prefer `code_lines`:

```python
"operations": [
    {
        "type": "replace",
        "node_id": "<uuid-from-preview>",
        "code_lines": [
            "def process(self, value: int) -> str:",
            '    """Process value."""',
            "    return str(value)",
        ],
    }
]
```

Insert/delete: see `help(universal_file_edit)` — container vs sibling `position`, `parent_node_id` (`__root__` for module level).

**Python batch:** multiple **sibling** targets in one `operations` array (class methods, nested functions under the same parent) preserve `stable_id` from preview — no re-preview between those ops. Do **not** combine **parent + child** in one batch (`NESTED_BATCH_FORBIDDEN`).

**Signature-only replace (Python):** single-line `code_lines` with parse stub (`def foo(...) -> T: pass`) updates the header and keeps body/docstring. Details: [PYTHON_EDIT_SEMANTICS.md](commands/file_editing/PYTHON_EDIT_SEMANTICS.md).

**tree-temp (JSON/YAML)** — use `json_pointer` (not `node_id` for pointers):

```python
"operations": [
    {"type": "replace", "json_pointer": "/timeout", "value": 60}
]
```

**text** — line ranges (1-based) on the **current draft**; map preview `node_ref` with `start_line = int(node_ref) + 1`:

```python
"operations": [
    {"type": "replace", "start_line": 10, "end_line": 12, "content": "New paragraph.\n"}
]
```

**Text line numbers go stale after every edit.** Do not reuse `start_line`/`end_line` from `fulltext_search` or from a preview taken before a prior `universal_file_edit` call — each successful edit shifts subsequent lines. Before **each** line-targeted operation:

1. Re-run `universal_file_preview` with the same `session_id` (reads the draft, not the on-disk file), **or**
2. Pass optional `anchor_head` + `anchor_tail` (first/last five non-whitespace characters of the target range's first/last lines) so the server rejects stale coordinates with `ANCHOR_MISMATCH`.

Multiple line-targeted operations in **one** `universal_file_edit` batch are sorted bottom-up automatically; sequential **calls** still require fresh line numbers between calls.

You may call `universal_file_edit` multiple times before write.

### 2.5 Step 4 — Write (preview then commit)

**Command:** `universal_file_write`

**tree-temp** — explicit modes:

- `write_mode: "preview"` — diff only, no disk write.
- `write_mode: "commit"` — backup, atomic write, index update path.

**sidecar / text** — two-phase **PID lockfile** on the canonical file:

1. First `universal_file_write` → preview diff (lockfile created).
2. Second `universal_file_write` (same session, lock valid) → commit with backup.

Always preview before commit when the change is non-trivial.

### 2.6 Step 5 — Close

**Command:** `universal_file_close`

- Releases `session_id`.
- Reconciles sidecar/draft vs source (may rebuild draft if out of sync — see response flags).

### 2.7 After commit — quality and indexes

1. `format_code` / `lint_code` / `type_check_code` on `file_path`
2. `comprehensive_analysis` after logically completed steps
3. Indexes for the saved file are updated on commit; run `update_indexes` only if project-wide rebuild is needed

### 2.8 Refactoring large Python files

Structural splits still use dedicated MCP commands (`split_file_to_package`, `split_class`, `extract_superclass`, `file_structure`) — not raw text editing. After refactor commands change files, use `universal_file_preview` / `open` if further manual edits are needed.

### 2.9 Fulltext and semantic search

Use indexed search to **discover** where to read or edit. Search commands do **not** modify files. After you have `file_path` (and optionally `line` from a hit), continue with `universal_file_preview` and, if needed, the edit session (`open` → `edit` → `write` → `close`).

**Detailed command docs:** [commands/search/fulltext_search.md](commands/search/fulltext_search.md), [commands/analysis/semantic_search.md](commands/analysis/semantic_search.md).

#### When to use which

| Command | Best for | Index / deps | Typical query |
|---------|----------|--------------|---------------|
| **`fulltext_search`** | Exact words, identifiers, `def foo`, class names, strings in code/docstrings | SQLite **FTS5** (`code_content_fts`); project DB must be built | `"ValidationError"`, `"def execute"`, `"MyClass"` |
| **`semantic_search`** | Concepts, paraphrases, “how is X done here?” without exact wording | **FAISS** + embedding service; run `update_indexes` / vectorization first | `"retry database connection"`, `"parse config yaml"` |
| **`fs_grep`** | Regex, unindexed paths, “what’s on disk right now” | None (scans files) | `pattern="register\\("`, `file_pattern="**/*.py"` |

**Rule of thumb:** start with **`fulltext_search`** for known symbols or literals; use **`semantic_search`** when you do not know the exact name; use **`fs_grep`** if FTS returns nothing but the file exists on disk, or you need line-accurate regex outside the index.

#### Prerequisites

1. `list_projects` → copy **`project_id`** (UUID).
2. Project must be **indexed**:
   - Empty or stale **`fulltext_search`** → run `update_indexes` with the same `project_id`, then retry.
   - **`semantic_search`** errors (`FAISS_INDEX_NOT_FOUND`, `EMBEDDING_SERVICE_ERROR`) → ensure indexes/vectors are built and embedding service is configured; see server logs.
3. After large external file changes, run `update_indexes` before relying on search again.

#### `fulltext_search`

**Purpose:** BM25-ranked search over indexed **chunk text**, docstrings, entity names, and symbol rows (variables, attributes).

**Parameters** (see `help` for the live schema):

| Parameter | Required | Notes |
|-----------|----------|--------|
| `project_id` | Yes | Project UUID |
| `query` | Yes | Free text; FTS tokenization (partial words, case-insensitive) |
| `entity_type` | No | Filter: `file`, `class`, `method`, `function`, `variable`, `attribute` |
| `limit` | No | Default **20** |

**Success payload (per hit):** `file_path`, `line`, `chunk_text`, `chunk_type`, `rank` (lower = more relevant), `chunk_uuid`.

**Example (MCP):**

```python
call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="fulltext_search",
    params={
        "project_id": "<uuid>",
        "query": "universal_file_edit",
        "entity_type": "function",
        "limit": 15,
    },
)
```

**Use cases:**

- Find all references to an error class or constant name.
- Locate functions whose docstring or body mentions a keyword.
- Narrow to classes: `entity_type="class"`, query=`"BaseMCPCommand"`.

#### `semantic_search`

**Purpose:** Find code chunks **semantically similar** to the natural-language query (embedding cosine similarity via FAISS).

**Parameters:**

| Parameter | Required | Notes |
|-----------|----------|--------|
| `project_id` | Yes | Project UUID |
| `query` | Yes | Natural language; **English** often matches indexed metadata best |
| `limit` | No | Default **10**, clamped **1–100** |
| `min_score` | No | Similarity threshold **0.0–1.0** (higher = stricter) |

**Success payload (per hit):** `file_path`, `line`, `text`, `score` (higher = better), `distance`, `chunk_type`, `chunk_uuid`.

**Example (MCP):**

```python
call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="semantic_search",
    params={
        "project_id": "<uuid>",
        "query": "validate command parameters against json schema",
        "limit": 20,
        "min_score": 0.55,
    },
)
```

**Use cases:**

- Explore unfamiliar codebase areas by intent (“where is backup before write?”).
- Find analogous implementations when names differ.
- Rank candidates with `min_score` to drop weak matches.

#### Combined workflow: search → preview → edit

```
list_projects
    → fulltext_search / semantic_search / fs_grep
    → note file_path (+ line) from results
    → universal_file_preview(project_id, file_path)   # optional node_ref drill-down
    → universal_file_open → edit → write → close      # if changes needed
```

**Tips:**

- Run **`fulltext_search`** and **`semantic_search`** with the same `project_id` for complementary hits (exact + conceptual).
- From a hit’s `line`, open preview at file root first; use surrounding context in `chunk_text` / `text` to choose edit targets.
- Do not use search results as a substitute for `universal_file_preview` when you need stable `node_ref` values for `universal_file_edit`.
- Search does not replace **`find_usages`** / **`find_dependencies`** for precise reference graphs—use those when you need symbol-level edges, not text similarity.

---

## 3. Code Validation Rules

### 3.1 Automatic validation

- Python commits through **sidecar** path run project validators (syntax, docstrings, type hints per server config) before persisting.
- Failed validation returns an error — fix `universal_file_edit` payload and retry write; do not bypass with direct tools.

### 3.2 Manual checks

```python
format_code(project_id=..., file_path=...)
lint_code(project_id=..., file_path=...)
type_check_code(project_id=..., file_path=...)
```

### 3.3 Docstrings

Canonical standard: [standards/PYTHON_DOCSTRING_STANDARD.md](standards/PYTHON_DOCSTRING_STANDARD.md). Plan new Python nodes with docstrings and type hints before commit.

---

## 4. File Organization Rules

### 4.1 Directory structure

| Content | Location |
|---------|----------|
| Source | `code_analysis/` |
| Docs | `docs/` |
| Scripts | `scripts/` |
| Logs | `logs/` |
| Data | `data/` |
| Pytest | `tests/` |
| Test projects | `test_data/` |

### 4.2 File size

- Prefer files **under 400 lines**; use `list_long_files` / `comprehensive_analysis` to detect violations.
- Split with MCP refactor commands rather than manual copy-paste.

---

## 5. Code Analysis Workflow

### 5.1 Before changes

1. `list_projects` → `project_id`
2. Locate targets: `fulltext_search` / `semantic_search` (indexed) or `fs_grep` (disk); then `universal_file_preview` or `get_code_entity_info`
3. `file_structure` before large refactors

### 5.2 After changes

1. `universal_file_write` commit
2. `universal_file_close`
3. `format_code`, `lint_code`, `type_check_code`
4. `comprehensive_analysis` when appropriate

---

## 6. Available MCP Commands (summary)

### 6.1 Universal file (view + edit) — **PRIMARY FOR FILE CONTENT**

Per-command docs: [commands/file_editing/](commands/file_editing/)

| Command | Purpose |
|---------|---------|
| `universal_file_preview` | Read-only navigation and snippets |
| `universal_file_open` | Start edit session |
| `universal_file_search` | XPath/CSTQuery on open session CST tree (Python sidecar) |
| `universal_file_edit` | Mutate draft |
| `universal_file_write` | Preview diff / commit to disk |
| `universal_file_close` | End session |

### 6.2 Search (read-only; no session required)

| Command | Purpose |
|---------|---------|
| **`fulltext_search`** | FTS5 over indexed code, docstrings, names — [fulltext_search.md](commands/search/fulltext_search.md) |
| **`semantic_search`** | Embedding similarity (FAISS) — [semantic_search.md](commands/analysis/semantic_search.md) |
| `fs_grep` | Regex on disk (no DB index) |
| `list_yaml_blocks` | YAML node listing in one file |
| `search_ast_nodes` | AST node search by type |
| `find_usages` / `find_dependencies` | Reference graph |

Use **`fulltext_search`** / **`semantic_search`** / `fs_grep` to **find** locations; use **`universal_file_*`** to **view and change** content. See [§2.9](#29-fulltext-and-semantic-search).

### 6.3 Analysis, AST, refactor, quality

- Analysis: `comprehensive_analysis`, `analyze_complexity`, `find_duplicates`, `update_indexes`, …
- AST: `get_ast`, `list_code_entities`, `get_code_entity_info`, `list_project_files`, …
- Refactor: `file_structure`, `split_class`, `extract_superclass`, `split_file_to_package`
- Quality: `format_code`, `lint_code`, `type_check_code`

### 6.4 File management (lifecycle, not content editing)

`delete_file`, `fs_copy`, `fs_move`, `fs_remove`, trash/restore commands, `project_file_*` locks and transfers — see `help` per command.

### 6.5 Removed from MCP catalog (historical)

Do not document or call via MCP: `cst_load_file`, `cst_modify_tree`, `cst_save_tree`, `cst_apply_buffer`, `query_cst`, `list_cst_blocks`, `json_load_file`, …, `read_project_text_file`, `write_project_text_lines`, `create_text_file`, `get_file_lines`, `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`.

---

## 7. Error Handling

### 7.1 Process

1. Read error code and message from server response.
2. Check `logs/` if needed.
3. Fix params or operation shape (`format_group` mismatch is a common cause).
4. Restart server after `code_analysis/` code changes.
5. Do not continue with broken committed state.

### 7.2 Universal file fallback table

| Situation | Action |
|-----------|--------|
| Wrong `node_ref` / no match in preview | Re-run `universal_file_preview`; confirm `format_group` |
| `json_pointer` vs `node_id` confusion (tree-temp) | Use RFC 6901 pointer in `json_pointer`, not CST UUID |
| Text line off-by-one | `start_line = int(node_ref) + 1` from preview |
| Text edit at wrong position / file bloated | Stale line numbers — re-run `universal_file_preview` with `session_id` before each edit; optional `anchor_head`/`anchor_tail` |
| Validation error on commit (Python) | Fix docstrings/types in `code_lines`; retry `write` |
| `session_id` invalid | Server restarted — `open` again |
| Parse error on open | Fix syntax via small `edit`+`write` or report to user; do not use removed `get_file_lines` |
| Need find-before-edit | `fulltext_search` / `semantic_search` / `fs_grep` → `universal_file_preview` at `file_path` |

Do **not** fall back to deprecated `cst_*` or legacy text commands.

---

## 8. Code Writing Standards

### 8.1 Docstrings and types

Follow [standards/PYTHON_DOCSTRING_STANDARD.md](standards/PYTHON_DOCSTRING_STANDARD.md). File, class, and public method docstrings are enforced on Python commit when validation is enabled.

### 8.2 Imports

Prefer letting the server normalize imports on Python save where applicable; otherwise keep imports grouped and explicit in `code_lines` replacements.

---

## 9. Workflow Examples

### 9.1 Inspect a YAML key

```python
# 1. Preview root
universal_file_preview(project_id, file_path="config/app.yaml")
# 2. Preview child
universal_file_preview(project_id, file_path="config/app.yaml", node_ref="/database")
```

### 9.2 Change a Python method

```python
# 1. Preview to get node_id
universal_file_preview(project_id, file_path="pkg/service.py", node_ref=None)
# 2. Open
open_result = universal_file_open(project_id, file_path="pkg/service.py")
session_id = open_result["data"]["session_id"]
# 3. Edit
universal_file_edit(
    project_id,
    session_id,
    operations=[{"type": "replace", "node_id": "<uuid>", "code_lines": ["..."]}],
)
# 4. Write preview → write commit (sidecar two-phase)
universal_file_write(project_id, session_id)
universal_file_write(project_id, session_id)
# 5. Close
universal_file_close(project_id, session_id)
# 6. Quality
format_code(...); lint_code(...); type_check_code(...)
```

### 9.3 Fulltext then semantic (discover APIs)

```python
# Exact symbol or string
ft = call_server(
    command="fulltext_search",
    params={"project_id": pid, "query": "EditSession", "entity_type": "class", "limit": 10},
)
# Same topic, different wording
sem = call_server(
    command="semantic_search",
    params={"project_id": pid, "query": "in-memory draft for file editing", "limit": 10, "min_score": 0.5},
)
# Pick file_path from ft or sem results["data"]["results"]
call_server(command="universal_file_preview", params={"project_id": pid, "file_path": hit["file_path"]})
```

### 9.4 Find then edit

```python
# Indexed literal
fulltext_search(project_id, query="TODO", limit=30)
# Or disk regex if needed
fs_grep(project_id, pattern="TODO", file_pattern="**/*.py", max_results=20)
# For each hit: universal_file_preview → open → edit → write → close
```

---

## 10. Technology Notes

### 10.1 Code as structured nodes, not raw patches

Edits target **stable node references** from preview (UUID, JSON Pointer, or line index), not ad-hoc string offsets in the IDE. Serialization and validation happen server-side on commit.

### 10.2 `code_lines` vs `code`

- ✅ **`code_lines`**: array of strings, one line per element (recommended for Python).
- ⚠️ **`code`**: single string — only for truly single-line edits.

### 10.3 test_data

All read/write of code under `test_data/` must use the server (MCP), per [TEST_DATA_AI_RULES.md](TEST_DATA_AI_RULES.md) — same universal workflow.

---

## 11. Best Practices Summary

### 11.1 Always do

- ✅ MCP as primary interface
- ✅ `fulltext_search` / `semantic_search` (or `fs_grep`) before editing unknown code; `update_indexes` if search is empty
- ✅ `universal_file_preview` before non-trivial edits
- ✅ `open` → `edit` → `write` (preview) → `write` (commit) → `close`
- ✅ `code_lines` for multi-line Python
- ✅ `format_code` / `lint_code` / `type_check_code` after commit
- ✅ Report errors; wait for user on fallback
- ✅ Restart server after changing `code_analysis/`

### 11.2 Never do

- ❌ `cst_*`, legacy text commands, or unregistered `universal_file_read/save/replace/delete`
- ❌ Direct `search_replace` / `write` on existing project files when server is up
- ❌ Skip preview/write commit and leave sessions open indefinitely
- ❌ Ignore validation errors on commit
- ❌ Use CLI for routine automation when MCP works

---

## 12. Quick Reference

| Goal | Commands |
|------|----------|
| **View file** | `universal_file_preview` |
| **XPath in open Python draft** | `universal_file_search` (with `session_id`) |
| **Edit file** | `open` → (`search` optional) → `edit` → `write` → `close` |
| **Find exact text (index)** | `fulltext_search` |
| **Find by meaning** | `semantic_search` |
| **Find regex on disk** | `fs_grep` |
| **Quality** | `format_code`, `lint_code`, `type_check_code` |
| **Project health** | `comprehensive_analysis` |

**Interface priority:** MCP `call_server` → CLI (fallback).

---

**Remember**: This project is built for AI-driven development through the code-analysis server. File viewing and editing go through **`universal_file_preview`**, **`universal_file_open`**, **`universal_file_search`** (optional XPath on session tree), **`universal_file_edit`**, **`universal_file_write`**, and **`universal_file_close`** — not legacy CST or plain-text MCP commands.
