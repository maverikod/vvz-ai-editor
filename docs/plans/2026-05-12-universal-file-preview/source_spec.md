# Universal File Preview — Source Specification

## 1. Purpose

The system shall provide a single MCP command that returns a structured preview
of a project file. The preview lets a caller see the top-level structure of the
file (or of a node within it) and slice through that structure without reading
the whole file or learning a separate command for every file type.

The preview is read-only. It never modifies the project, the database, the
file watcher state, or any tree session that it did not create.

## 2. Outward shape

From outside, there is exactly one MCP command. Its name is
`universal_file_preview`. Its input has a fixed JSON Schema. Its output has a
fixed envelope. Behaviour varies internally by file type, but the contract a
caller sees is uniform.

The command joins the read-only batch whitelist so that it can be combined
with code-analysis queries in a single batch call.

## 3. Internal shape

Internally, the command is a package. The package has a dispatcher that picks
a handler by file extension. Each handler is responsible for opening one
family of files and producing a uniform in-memory node representation that
the rest of the command navigates without knowing the file type. New file
types are added by adding handlers; the public command schema does not change.

The command does not have multiple internal "engines". It has one navigation
procedure that works against the uniform node representation. The procedure
recurses: it answers the same questions at every level of depth, on the
current focus node and on each of its children when those become the focus
in a follow-up request.

## 4. Uniform node representation

Every node the command works with — the root of a file, a child of a tree
node, an element of a sequence, a line of a text file — has the same kind of
metadata:

- a **node kind**, which is one of: `scalar`, `lines`, `mapping`, `sequence`,
  `tree_node`. `tree_node` is the combined kind used for nodes that have both
  named attributes and an ordered child set, such as CST function and class
  definitions.
- a **sliceability** flag: true when the node exposes an ordered, indexable
  set of children that the `slice` parameter can address; false otherwise.
- a **child preview rule** that depends on the node's own kind, not on the
  parent's kind, and that defines how this node is summarised when it appears
  as a child in some other node's slice.

A handler turns a file into a tree of such nodes lazily: only the root and
the children needed by the current request are materialised. Children are
themselves uniform nodes, so the same navigation procedure can drill down
into any of them in a follow-up request.

## 5. Slice as a level-local question

`slice` is a single string parameter, Python-style, zero-based, half-open.
Examples: `"0:5"` for the first five elements, `":3"` for the first three,
`"-5:"` for the last five, `":"` for the whole set (capped by
`preview_lines`).

On every preview request, the command performs one navigation step:

1. Resolve the focus node from `project_id`, `file_path`, and optional
   `node_ref` (default focus is the file root).
2. Ask the focus node whether it is sliceable.
3. If `slice` is set and the focus node is not sliceable, return an input
   error. If `slice` is set and the focus node is sliceable, apply it to the
   focus node's ordered child set. If `slice` is omitted, return the first
   `preview_lines` children of the focus node (capped).
4. For each child in the result, build its summary according to the child's
   own kind via its child preview rule.

Slice is not a property of the file type; it is a property of the current
focus node. The same file may be sliceable at one focus and not at another:
a JSON object root is sliceable (keys in file order), but the focus is then
on one of those values, which may be a scalar (not sliceable). A Python
module is sliceable (top-level statements); the focus on a particular
function inside it is also sliceable (statements in the function body).

This zero-based half-open semantics is local to this command. Other commands
in the project that work with file line numbers (`get_file_lines`,
`cst_get_node_by_range`, `replace_file_lines`) continue to use their existing
one-based inclusive semantics. The discrepancy is intentional: this command
is for navigation; the others are for precise edits.

## 6. Sliceability by node kind

The sliceability flag of a node follows from its kind:

- `scalar` is never sliceable. A scalar has no children.
- `lines` is sliceable. Children are the lines, in file order.
- `sequence` is sliceable. Children are the elements, in order.
- `mapping` is sliceable. Children are the key-value pairs, in file order
  when the source format preserves order (JSON, YAML mappings), or in
  declaration order for in-memory structures that have a definite ordering.
- `tree_node` is sliceable. Children are the ordered substatements or
  sub-elements of the node (for example, the body of a CST function).

Every node kind except `scalar` is sliceable. Whether a particular node is
indexable in a meaningful way depends on the handler that produced it; the
handler is responsible for honoring the order the file imposes.

## 7. Child preview rule

When a node appears as a child in some other node's slice, its preview is
shaped by its own kind:

- `scalar`: the value, truncated by `value_preview_len`.
- `lines`: a count of lines and the first line truncated by
  `value_preview_len`.
- `sequence`: the length and a coarse summary of element kinds (for example,
  "10 objects" or "mixed: 4 numbers, 2 objects").
- `mapping`: a count of keys and a short list of key names truncated by
  `value_preview_len`.
- `tree_node`: a type label, an optional name, a compact dictionary of
  attributes appropriate to the type (for example, `params` and `returns`
  for a function), and a count of children.

A child preview never includes the child's own children's content. To see
inside a child, the caller issues a follow-up request with that child's
`node_ref`.

## 8. Stable identifiers

The command does not invent identifiers. It reuses the identifiers already
produced by the project's existing tree infrastructure:

- For Python files, the stable identifier of a node is the `stable_id` field
  returned by `cst_load_file` in its `outline_nodes` array. This is a UUID
  that the project persists in node-id blocks inside source files. It is
  stable across reloads as long as the project's CST infrastructure keeps it
  stable. No new identifier scheme is introduced.
- For JSON files, the stable identifier of a node is the `node_id` returned
  by `list_json_blocks`. JSON pointers (`/foo/bar`) are also accepted by the
  JSON handler as an alternative spelling, since the same infrastructure
  produces both.
- For YAML files, the stable identifier scheme depends on whether the project
  already has a YAML tree infrastructure. If it does, those identifiers are
  reused. If it does not, the YAML handler accepts JSON-pointer-style paths
  derived from the loaded YAML document. Planned YAML tree integration under
  `code_analysis.core.yaml_tree` aligns RFC 6901 JSON Pointer paths on the loaded
  document with opaque stable ids via `stable_node_id_for_pointer`, preserving
  the same interchange between pointer strings and `node_id` values as for JSON.
  The optional MCP command `list_yaml_blocks` mirrors `list_json_blocks` for
  `.yaml` and `.yml` files so callers can discover those pairs before focusing
  with `node_ref`.
- For text files (`.md`, `.txt`, `.rst`, `.adoc`) and JSONL files (`.jsonl`,
  `.ndjson`), the root is a `lines` node. Children are addressed by their
  zero-based index in the file. No separate identifier scheme is needed.

The caller passes a stable identifier in the `node_ref` parameter to focus
the preview on a specific node. When `node_ref` is omitted, the focus is the
root of the file.

## 9. Tree sessions

Some callers will work with this command in isolation. Others will already
have a CST or JSON tree loaded in memory via `cst_load_file` or
`json_load_file`, and they will want this command to read from that
in-memory tree rather than reparse the file.

The command supports both:

- If the caller passes only `project_id` and `file_path`, the command may
  open and close any tree session it needs internally. It does not leak
  tree sessions to the caller.
- If the caller passes an existing `tree_id`, the command reads from that
  session and does not create or close anything.

When the command creates a tree session internally and that session is
useful for the caller's next step, the command returns its `tree_id` in
the response so the caller can pass it back next time.

The command never invalidates a `tree_id` it did not create.

## 10. Response envelope

The response has a uniform envelope. It always tells the caller:

- the focus node: its `node_kind`, its `node_ref` (the identifier the caller
  can pass back to focus on it again), and the node's own metadata (type,
  name, attributes when applicable);
- whether the focus node was sliceable, and the slice that was applied;
- the total size of the focus node's child set, so the caller knows what
  they did not see;
- the list of children for the slice, each rendered through its own child
  preview rule and each carrying its `node_ref` for further drill-down;
- when the command created a tree session internally, the `tree_id` for
  reuse.

There is no per-kind ResponseEnvelope variant. The envelope shape is
constant; the `node_kind` field tells the caller how to interpret the
children.

## 11. Truncation and preview budget

A preview must not return more data than necessary to orient the caller.
Three numeric parameters limit the response size:

- `slice` bounds which part of the focus node's child set is included;
- `preview_lines` caps how much the command returns when `slice` is omitted
  (default: a small first chunk of the child set);
- `value_preview_len` caps the length of any single scalar value or name
  shown inline in the response.

When the response, after these caps, still exceeds the read-only batch size
threshold, the read-only batch overflow-to-file mechanism applies as usual.
The command itself does not implement file overflow.

## 12. Error model

The command surfaces three classes of error distinctly:

- input errors (unknown file type, malformed `slice`, unknown `node_ref`,
  `slice` requested on a non-sliceable focus node, conflicting parameters)
  return a deterministic error code per class;
- file-structure errors (a `.json` file that does not parse, a `.yaml` file
  with a syntax error) return a single error code that names the failing
  parser and points to the line range that failed, when possible;
- handler-internal errors (a CST node cannot be resolved, a JSON pointer
  refers outside the document) return a code that names the handler.

The command never silently falls back to a different file type. A failed
preview returns an error; the caller decides whether to retry with different
parameters or use a different command.

## 13. Boundaries

The command does not write to files, the database, or tree sessions it did
not create.

The command does not return raw file bytes. All output is structured JSON.

The command does not accept globs or wildcards in `file_path`. One call
operates on exactly one file.

The command does not include XML or HTML in its initial scope. Those file
types are deferred to a later plan.

## 14. Integration with the read-only batch whitelist

After the command is implemented and its handlers stabilise, the command
name is added to `READ_ONLY_BATCH_WHITELIST` in
`code_analysis/commands/read_only_batch_whitelist.py`. From that moment
the command is callable inside `read_only_batch` invocations alongside
the existing analysis queries.

The whitelist edit is its own step in the plan, not part of the command
package. The whitelist edit happens only after the command and its tests
are green.

## 15. Python handler structured text rendering

The Python file handler produces a structured text rendering of any node,
suitable for direct consumption by AI models. This rendering replaces the
generic JSON child-count summary for Python `tree_node` nodes with a
human-readable text block.

The rendering follows these rules by node type:

- **Module (file root):** The rendering includes the module docstring, followed
  by one line per top-level entity: import lines with their stable identifier
  and line range, constant assignments, class signatures with class docstrings
  and method signatures with method docstrings, and module-level function
  signatures with docstrings. Each entity is prefixed with its stable
  identifier in brackets and its line range.

- **ClassDef:** The rendering includes the class signature and docstring,
  followed by each method's signature and docstring. Method bodies are not
  included.

- **FunctionDef / AsyncFunctionDef:** The rendering includes the full function
  signature, full docstring, and the first-level body. Compound statements
  at the first level (`if`, `for`, `while`, `try`, `with`, `match`) are
  collapsed: only the first line of the compound statement is shown, followed
  by `...`, prefixed with the statement's stable identifier and line range.
  Simple statements at the first level are shown in full.

- **Compound statements (If, For, While, Try, With, Match) as focus node:**
  The same first-level rendering applies: the statement itself is shown with
  its stable identifier, line range, and first line, followed by its
  first-level body with the same collapse rule.

The stable identifier and line range prefix format is:
`[stable_id] Lstart-end` for multi-line nodes, `[stable_id] Lline` for
single-line nodes.

This structured text is returned in the `text` field of the block summary.
When `text` is present, the caller should use it instead of the generic
`type`, `name`, `attributes`, `child_count` fields for display purposes.

## 16. Python handler full-text threshold

The Python file handler accepts a `full_text_max_lines` parameter as part of
the preview budget. When the target Python file has fewer lines than this
threshold, the handler returns the entire file source as a single text block
instead of the structured rendering described in section 15. This allows
callers to read small files in one step without navigating the tree structure.

The default value of `full_text_max_lines` is 200 lines. The parameter is
optional; when omitted, the default applies. A value of 0 disables the
full-text fallback entirely.

## 17. Post-implementation addenda (G-010, G-011)

<!-- non-binding -->
Sections 17.1 and 17.2 document work performed after the initial implementation
was complete. They do not change any binding requirements in sections 1–16.
They add clarifications about what was actually built and what issues were
found and fixed. Do not propagate these sections into existing G/T/A-step
rewrites — treat them as append-only notes.
<!-- /non-binding -->

### 17.1 G-010 — PythonNodeRenderer implementation

G-010 delivered PythonNodeRenderer (C-022) as a new module `python_visualizer.py`
with two public functions: `render_module(tree, budget)` and `render_node(tree, stable_id)`.
The visualizer was wired into `PythonFileHandler` via `open_root` and `resolve_node_ref`.
An optional `text: str | None` field was added to the `Block` dataclass (C-005).

Known gap left open after G-010: `T-901` (full-text threshold wiring into
`get_schema()` and `validate_params()`) has no atomic steps written (`atomic_steps: []`).
This wiring is required for `full_text_max_lines` to be accepted as a caller parameter.

### 17.2 G-011 — PythonFileHandler refactor findings

G-011 refactored `python_handler.py` after G-010. The following issues were
found during verification of tactical steps (checks t7, t10):

- **T-1001 / t10:** The description defers the decision "verify none are imported
  elsewhere" to the executor. The functions `_cst_statements_to_nodes`,
  `_classify_cst_node`, `_cst_node_to_node`, `_find_by_stable_id` are confirmed
  unused outside `python_handler.py` and are safe to delete.

- **T-1002 / t7:** The description says `open_root` should "return single text Block".
  This is incorrect: `open_root` returns a `Node`, not a `Block`. The Block is
  produced downstream by the BlockHandler. The A-001 prompt correctly implements
  `Node` return — the T-step description contains a terminology error only.

<!-- non-binding -->
## Notes

The XML/HTML deferral is mentioned only to mark scope; it does not produce
any concept. The 1-based/0-based discrepancy explained in section 5 is
documentation, not behaviour beyond what section 5 already binds. The
explicit enumeration of node kinds in section 4 is binding; the example
shapes shown in section 7 are illustrative.
<!-- /non-binding -->