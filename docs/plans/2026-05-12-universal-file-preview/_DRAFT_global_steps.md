# Global Step Decomposition (draft for review)

This is a draft of level-3 global steps for the `universal_file_preview` plan.
Each step lists the concepts it covers, the relations it implements, and the
binding source_spec line ranges it occupies. Each step passes the conceptual
test (no files, modules, classes, or functions named here).

The plan has 9 global steps. This is above the typical_range of [3, 7] but
below the indicator_threshold of 10. The decomposition uses one step per
handler (G-004..G-008) so future handlers (XML, TOML, binary formats, ...)
can be added as new G-NNN steps without touching the existing ones.


## G-001 — Public command contract

**Concepts covered:** C-001 (PreviewCommand), C-012 (ResponseEnvelope),
C-014 (ErrorClassification), C-021 (ScopeBoundary).

**Relations implemented:**
- C-001 produces C-012
- C-001 produces C-014
- C-001 implements C-021

**Source ranges:** 5–8, 13–21, 168–184, 200–213, 215–226.

**Conceptual scope:** the system exposes one MCP command with a fixed input
schema, a uniform response envelope (one shape for all NodeKind values), a
deterministic error classification, and explicit negative scope. This step
fixes WHAT the command is to callers, not HOW it is built.


## G-002 — Uniform node model and navigation step

**Concepts covered:** C-002 (HandlerDispatcher), C-003 (Handler),
C-004 (NodeKind), C-005 (Sliceability), C-006 (ChildPreviewRule),
C-007 (NavigationStep), C-008 (Slice), C-013 (PreviewBudget).

**Relations implemented:**
- C-001 owns C-002
- C-002 uses C-003
- C-001 owns C-007
- C-007 consumes C-005
- C-007 consumes C-008
- C-007 uses C-006
- C-007 produces C-012
- C-005 depends_on C-004
- C-006 depends_on C-004
- C-001 consumes C-008
- C-001 consumes C-013
- C-007 consumes C-013
- C-003 produces C-014
- C-007 produces C-014

**Source ranges:** 25–34, 36–45, 47–70, 75–92, 95–106, 108–122,
186–198, 200–213.

**Conceptual scope:** the dispatcher chooses a handler; the handler produces
the uniform in-memory node representation (NodeKind plus child set); the one
navigation step asks Sliceability of the focus, applies Slice when it can,
and renders each child via the ChildPreviewRule appropriate to that child's
own NodeKind. This is the spine of the command. There are no per-type
engines and no per-type response shapes — only one procedure parameterised
by the node it works on.


## G-003 — Stable identifiers and tree sessions

**Concepts covered:** C-009 (StableIdentifier), C-010 (NodeReference),
C-011 (TreeSession).

**Relations implemented:**
- C-010 depends_on C-009
- C-007 consumes C-010
- C-001 consumes C-010
- C-007 uses C-011
- C-001 uses C-011

**Source ranges:** 124–145, 147–149, 151–166.

**Conceptual scope:** the command reuses identifiers from existing project
tree infrastructure (cst_load_file for Python, list_json_blocks for JSON,
project YAML infra or JSON-pointer-style paths for YAML, zero-based line
index for lines roots). It accepts an optional NodeReference to focus the
preview, and an optional caller-owned TreeSession or opens one transiently.
It never closes or invalidates sessions it did not create.


## G-004 — Python handler

**Concepts covered:** C-016 (PythonHandler).

**Relations implemented:**
- C-016 extends C-003
- C-016 produces C-004
- C-016 depends_on C-009

**Source ranges:** 130–134.

**Conceptual scope:** the handler for .py, .pyi, .pyw. It opens a Python
file and produces a tree_node root (Module). Interior nodes follow the
CST: FunctionDef and ClassDef are tree_node, their bodies are sequences of
further tree_node statements, leaf values are scalar. The handler resolves
node_ref values that are stable_id UUIDs produced by cst_load_file. It
does not implement navigation.


## G-005 — Text handler

**Concepts covered:** C-017 (TextHandler).

**Relations implemented:**
- C-017 extends C-003
- C-017 produces C-004

**Source ranges:** 141–144.

**Conceptual scope:** the handler for .md, .txt, .rst, .adoc. It opens a
text file and produces a lines root whose children are scalar text lines.
node_ref values for child lines are zero-based line indices. There is no
secondary parse: scalar lines have no children of their own.


## G-006 — JSON handler

**Concepts covered:** C-018 (JsonHandler).

**Relations implemented:**
- C-018 extends C-003
- C-018 produces C-004
- C-018 depends_on C-009

**Source ranges:** 136–139.

**Conceptual scope:** the handler for .json. It opens a JSON file and
produces a root whose NodeKind depends on the document type: mapping for
objects, sequence for arrays, scalar for bare scalars. Interior nodes
follow the JSON shape. The handler resolves node_ref values as node_id
from list_json_blocks or as JSON pointers (`/foo/bar`); the two are accepted
interchangeably because the same project infrastructure produces them.


## G-007 — JSON Lines handler

**Concepts covered:** C-019 (JsonLinesHandler).

**Relations implemented:**
- C-019 extends C-003
- C-019 produces C-004

**Source ranges:** 137–137, 141–144.

**Conceptual scope:** the handler for .jsonl, .ndjson. It opens a JSONL
file and produces a lines root whose children are scalar text lines, so
a slice at the root selects line indices without parsing any JSON. When
the caller drills into a specific line by passing its index, the follow-up
request parses that line as its own root (using the JSON-handler logic
from G-006). This step does not duplicate JSON parsing; it composes the
lines root and delegates per-line parsing.


## G-008 — YAML handler

**Concepts covered:** C-020 (YamlHandler).

**Relations implemented:**
- C-020 extends C-003
- C-020 produces C-004
- C-020 depends_on C-009

**Source ranges:** 138–139.

**Conceptual scope:** the handler for .yaml, .yml. It opens a YAML file
and produces a root whose NodeKind depends on the document root: mapping
for YAML mappings, sequence for YAML sequences, scalar for bare scalars.
A multi-document YAML file (separated by `---`) produces a sequence root
whose elements are the document roots. The handler resolves node_ref
values using the project YAML tree infrastructure when present, otherwise
as JSON-pointer-style paths derived from the loaded document.


## G-009 — Read-only batch integration

**Concepts covered:** C-015 (ReadOnlyBatchIntegration).

**Relations implemented:**
- C-015 depends_on C-001

**Source ranges:** 20–21, 228–238.

**Conceptual scope:** after G-001 through G-008 are stable, the command
name is added to the read-only batch whitelist. This is a separate step
because the whitelist edit is a contract change for a different command
and must not happen before the command and its handlers are green.


## I1 Coverage check (informal, to be verified before freeze)

Concepts: C-001..C-021 — 21 concepts in spec.yaml. All 21 are assigned to
exactly one global step. No concept appears in two steps.

Relations: 36 relations in spec.yaml. All 36 are implemented by exactly
one global step. No relation is unassigned, no relation appears in two
steps. Verified locally with a coverage script before this draft was
written.

Source ranges: 5..238 (binding lines only). Every binding section of
source_spec is referenced by at least one global step.

Step count: 9. Above typical_range upper bound of 7, below
indicator_threshold of 10. The excess is intentional: one handler per
step allows new handlers to be added as new G-NNN steps without revising
any existing step.


## Dependency order

- G-001 has no plan-internal dependencies.
- G-002 depends_on G-001 (navigation step produces the envelope defined
  by G-001).
- G-003 depends_on G-002 (NodeReference and TreeSession flow into the
  navigation step).
- G-004 depends_on G-002 and G-003 (Python handler produces nodes that
  G-002 navigates, using identifier source from G-003).
- G-005 depends_on G-002 (text handler produces lines nodes; no
  identifier source needed beyond zero-based index).
- G-006 depends_on G-002 and G-003 (JSON handler, identifier source from
  G-003).
- G-007 depends_on G-005 and G-006 (JSONL composes a lines root from
  G-005 and reuses JSON parsing from G-006 for per-line drill-down).
- G-008 depends_on G-002 and G-003 (YAML handler, identifier source from
  G-003).
- G-009 depends_on G-001 through G-008 (do not whitelist before all
  handlers work).

## Adding a new handler in the future

Adding support for a new file type creates one new G-NNN step (the
handler) and one cascade update to source_spec/spec.yaml to introduce its
concept. Existing handlers and the navigation step are not touched.
