# Python edit semantics (sidecar / CST)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

How `universal_file_edit` applies replacements to Python CST nodes. Applies to the **sidecar** path (`format_group: sidecar`). Internal `cst_modify_tree` shares the same modifier core.

Parent workflow: [WORKFLOW.md](WORKFLOW.md). Command reference: [universal_file_edit.md](universal_file_edit.md).

---

## Node identity

- Each structural node gets a stable **`stable_id`** (UUID) at parse time; persisted in `.cst/<stem>.tree` sidecar metadata.
- `universal_file_preview` exposes it as **`node_ref`**; pass it as **`node_id`** in edit operations.
- Preview also returns metadata: `type`, `kind` (`function`, `method`, `class`, …), `name`, line range, optional `docstring`.
- **`node_id` in edit params is the stable UUID** — the server resolves it to the current span before each op. Sibling targets in one batch keep the same `node_ref`; re-preview is optional unless an op failed or you need drill-down after structural change.

---

## Full replace vs header-only replace

When `type: replace` targets a **`FunctionDef`** or **`ClassDef`**:

| Replacement snippet | Behaviour |
|---------------------|-----------|
| **Single non-empty line**, no indented body lines | **Header-only** — signature / class line updated; **body and docstring preserved** |
| Multiple non-empty lines, or any indented line | **Full replace** — entire node replaced by parsed snippet |

### Header-only examples

Change signature only:

```json
{
  "type": "replace",
  "node_id": "<function-uuid>",
  "code_lines": ["def foo(x: int) -> str: pass"]
}
```

The `pass` makes the snippet parseable; it is **not** written into the function body. Only the `def …:` header is patched.

Rename class in header:

```json
{
  "type": "replace",
  "node_id": "<class-uuid>",
  "code_lines": ["class WidgetRenamed:"]
}
```

### Force full replace

Send the **complete** function or class including body (multiple `code_lines`, with proper indentation). That replaces the whole node.

---

## Docstrings

Docstrings are **not** part of the function/class header line. To change a docstring:

- **Full replace** the function/class node including the new docstring in `code_lines`, or
- Replace the **statement node** that holds the docstring (preview drill-down to the docstring/simple statement scope).

Header-only replace does **not** change an existing docstring.

---

## Insert and delete

| Action | Fields |
|--------|--------|
| Insert at module level | `parent_node_id: "__root__"`, `position: "first"` \| `"last"`, `code_lines` |
| Insert before/after sibling | `target_node_id`, `position: "before"` \| `"after"`, `code_lines` |
| Delete node | `type: "delete"`, `node_id` |

Do not use `IndentedBlock` as insert parent — use the enclosing `FunctionDef` / `ClassDef` or `__root__`.

---

## Batch rules

- Operations in one request run **in order**; later ops see the tree after earlier ones.
- **Allowed in one batch:** siblings and unrelated nodes — e.g. two class methods, or `inner_a` insert + `inner_b` replace inside the same `outer` function. `stable_id` is preserved; re-preview between those ops is **not** required.
- **Forbidden in one batch:** **ancestor and descendant together** (e.g. `outer` + `inner_a`) → `NESTED_BATCH_FORBIDDEN`. Split into separate calls or edit only the outermost node.
- Across **separate** `universal_file_edit` calls: re-preview if an op failed or you need fresh drill-down after a full parent replace.

---

## Fine-grained nodes (Param, Name, Annotation)

Preview may surface inner-node refs for small spans. `universal_file_edit` **promotes** leaf refs (Name, Integer, …) to the enclosing **`SimpleStatementLine`** for replace/delete — you cannot reliably edit a bare `Param` through the universal edit API.

For parameter-level edits, use the internal **`cst_modify_tree`** API (developer tooling) with `FINE_GRAINED_REPLACE_NODE_TYPES`, or replace the whole function signature via header-only / full replace.

---

## `replace_all_child_nodes` (internal CST API)

The **`cst_modify_tree`** command accepts optional `replace_all_child_nodes: true` on replace ops to force full node replacement even for a one-line snippet. Default is **`false`** (header-only when applicable).

This flag is **not** exposed on `universal_file_edit` — header-only vs full replace is inferred from snippet shape only.

Documented in [../cst/cst_modify_tree.md](../cst/cst_modify_tree.md) for server developers.

---

## Draft preview (diff)

When `session_id` is passed to `universal_file_preview` and the draft differs from disk:

- Module-level `focus.text` may show a **unified diff** (committed → draft).
- Drill-down focus (class, function) shows a diff slice for **that node only** — unrelated edits elsewhere in the file are excluded.

---

## Structural search in open session

**Command:** [`universal_file_search.md`](universal_file_search.md)

XPath / CSTQuery over the **in-memory CST tree of one `universal_file_open` session** — the same draft tree that edits mutate. **Not** project-wide; **not** disk; **not** legacy `cst_find_node` (`tree_id`).

Typical flow:

1. `universal_file_open` → `session_id`
2. `universal_file_search` with `query` (e.g. `ClassDef[name='Widget']//FunctionDef`)
3. `universal_file_edit` using `matches[].node_ref` as `node_id`

Re-run search after structural edits if selectors may match different nodes. For outline navigation without a selector, use `universal_file_preview` drill-down instead.

---

## See also

- [universal_file_search.md](universal_file_search.md) — session-scoped XPath
- [cst_modify_tree.md](../cst/cst_modify_tree.md) — internal CST batch API
- [plans/2026-05-18-tree-sidecar/source_spec.md](../../plans/2026-05-18-tree-sidecar/source_spec.md)
