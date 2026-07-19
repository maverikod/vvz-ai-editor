# Universal file edit workflow

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

> **Documentation tiers:** `list_servers` card (brief) → server **help** (quick start) → command **`info`** (full guide with JSON examples). See [EDITOR_GUIDE.md](EDITOR_GUIDE.md).

## Thin-server model

AI Editor is a **thin MCP server**: it holds a workspace draft and orchestrates CA lock/upload. The agent obtains `session_id` from **Code Analysis Server `session_create`** and passes the same id to every `universal_file_*` call. `universal_file_open` does **not** generate `session_id`.

Changes reach CA **only** on `universal_file_write` (`write_mode=commit`). `universal_file_edit` mutates the workspace draft only.

## Lifecycle (registered commands)

```
CA: session_create  →  session_id

universal_file_open(project_id, file_path, session_id)
universal_file_preview(project_id, file_path, session_id)   # repeat after edits
universal_file_edit(project_id, session_id, operations)     # repeat 2–3 as needed
universal_file_write(..., write_mode=preview)               # diff only, no validation
universal_file_write(..., write_mode=commit)                # validate → CA upload
universal_file_close(project_id, session_id)                # always
```

| Step | Command | Effect |
|------|---------|--------|
| 0 | CA `session_create` | Agent gets `session_id` |
| 1 | `universal_file_open` | CA lock + download → workspace draft; returns `format_group` |
| 2 | `universal_file_preview` | Read draft structure; `node_ref` for edits (no validation) |
| 3 | `universal_file_edit` | Mutate draft only |
| 4a | `universal_file_write` preview | Unified diff vs origin; no CA upload |
| 4b | `universal_file_write` commit | Pre-write validation, then CA upload if changed |
| 5 | `universal_file_close` | CA unlock (best-effort) + workspace cleanup |

**Multi-file:** one CA `session_id` may hold several files. Pass `file_path` on edit / write / close when `multi_file_bundle.open_file_count > 1`.

**Read-only without open:** `universal_file_preview(project_id, file_path)` — one-shot CA `download_without_lock` (no lock, no workspace session). If the file is already open, pass `session_id` or you get `OPEN_FILE_USE_WORKSPACE_PREVIEW`.

**Not registered** in the current thin server (legacy / optional): `universal_file_search`, `universal_file_save`, CST tree commands. Use preview drill-down for navigation.

## Format groups

Returned by `universal_file_open` as `format_group`:

| format_group | Extensions | Preview `node_ref` | Edit address field |
|--------------|------------|--------------------|--------------------|
| **sidecar** | `.py`, `.pyi`, `.pyw` | CST stable UUID | `node_id` |
| **tree-temp** | `.json`, `.yaml`, `.yml`, `.jsonl`, `.ndjson` | JSON Pointer, e.g. `/timeout` | `json_pointer` (not `node_id`) |
| **text** | `.md`, `.txt`, `.rst`, `.adoc`, … | MD: slug path; plain: zero-based line index | `node_ref` or `start_line`/`end_line` |

## Preview with an open session

After `universal_file_open`, pass the same `session_id` to `universal_file_preview`:

- Reads the **current draft** (not CA canonical file).
- **Python (sidecar):** `node_ref` (`stable_id`) is preserved across sibling ops in one batch.
- **Text:** line numbers and section slugs go stale after each edit — re-preview before the next line-targeted op.

## Write

### Explicit modes (recommended)

- `write_mode=preview` — unified diff; **no** flake8/Ruff/mypy/docstring checks; **no** CA upload.
- `write_mode=commit` — compare draft vs origin; if equal → `unchanged=true` (no CA RPC); if diff → pre-write validation then `upload_session_file_content`.

Pre-write validation order (commit): temp serialize → quality tools (Python: black-parseable, flake8, Ruff, mypy) → handler validator (docstrings, JSON/YAML parse). On failure: `VALIDATION_ERROR`, origin and draft unchanged.

### Sidecar legacy (`.py`, `write_mode` omitted)

Two-phase PID lockfile: first call → preview + lock; second call (same server PID) → commit. Prefer explicit `write_mode=preview` then `write_mode=commit`.

## Parse-error fallback

If a structured file cannot be parsed on open, the session opens with `is_invalid: true` and **line-based** editing until a successful commit restores structural editing.

## Discovery before edit

Use read-only search to find `file_path`:

- `fulltext_search`, `semantic_search`, `fs_grep` — project-wide (when registered on CA/editor)

Then `universal_file_preview` (with or without open) for edit targets.

## Sessions

- One open bundle entry per `(project_id, file_path)` until `universal_file_close`.
- Local bundles are **lost on server restart** — re-open required.
- `session_id` = CA session id (not a separate editor-generated uuid).

## Related docs

- Per-command: [COMMANDS.md](COMMANDS.md)
- AI rules: [FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)
- Coder brief: [UNIVERSAL_FILE_EDIT_CODER.yaml](../../standards/UNIVERSAL_FILE_EDIT_CODER.yaml)
- Python replace semantics: [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)
