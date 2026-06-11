# Marked Tree Unification — HRS Review Package

> **HISTORICAL NOTE:** This document captured the decision-review package for the predecessor plan iteration. The canonical green plan at `docs/plans/marked_tree_unification/` and `docs/ai_reports/marked_tree_unification_dovodka_audit.yaml` supersede this package. Retained for audit trail only.

**Date:** 2026-05-30  
**Plan:** `marked_tree_unification`  
**HRS path:** `docs/plans/marked_tree_unification/source_spec.md` (repo-relative)

---

## Purpose & status

This document is a **human review package** for proposed edits to the Human-Readable Specification (HRS) of plan `marked_tree_unification`. **HRS edits are AUTHORIZED**; cascade to `source_spec.md` and downstream plan artifacts is **in progress**.

**Locked decisions encoded in this package:**

| ID | Decision |
|----|----------|
| **A1** | **Lifecycle = TARGET model to implement.** Keep existing HRS Block 4 (`{d001}`–`{d006}`) and Block 5 (`{e001}`–`{e006}`). Discard prior "code-truth" rewrites of `{d001}`–`{d005}`. Current `universal_file_*` diverges from the HRS; that divergence is implementation work, not a reason to rewrite the HRS. Augment the target where user nuances (a)–(f) are missing. |
| **A2** | **Preview = 1:1 with existing code**, except thresholds are **per-format** (Python, JSON, YAML, Markdown, plain text each have their own `full_text_max_lines`). Otherwise: node-id markers at the start of each physical line; special comments stripped before render; `IndentedBlock` transparent; compound headers remain. See **FINAL-1** for threshold unit and JSON normalization. |
| **FINAL-1** | Preview thresholds: **source lines** for every format; JSON normalized to printable form before line counting; default 200 lines per format; threshold 0 disables full inline rendering; bytes **not** used for inline-vs-drilldown. |
| **FINAL-2** | Open `content`: accepted **only** when target file is non-existent or source/tree is broken/corrupted; **ERROR** if file exists and is valid; when accepted: write content to session file first, then standard build/tree/checksum/git protocol. |

All paths in this document are **repo-relative** to the workspace root.

---

## Section L — Lifecycle (TARGET, keep + augment)

Block 4 (`{d001}`–`{d006}`) and Block 5 (`{e001}`–`{e006}`) describe the **target** edit-session lifecycle. `{d002}`, `{d003}`, and `{d005}` require augmentation; all other lifecycle paragraphs in Block 4 are kept verbatim.

### `{d001}` — Session directory

**KEEP**

> {d001} An edit session is represented by a session directory placed next to the source file. The directory name is `<FileName>-<UUID4>` where `FileName` is the source file's base name and `UUID4` is a randomly generated UUID.

---

### `{d002}` — Open session

**AUGMENT (FINAL-2)** — append content-supply rule to open semantics:

> {d002} Opening a session performs four steps in order: create the session directory; copy the source file into the session directory; validate the co-located tree file by checksum — if valid, copy it into the session directory, if missing or invalid, build a new tree from the source content inside the session directory; initialize a git repository (dulwich 1.2.4, already installed) inside the session directory and create the initial commit containing the source copy and the tree file. When the caller supplies `content` for open: that content is accepted ONLY when the target file is NON-EXISTENT or its source/tree is BROKEN/CORRUPTED (invalid checksum, unreadable tree, or missing co-located tree where required). If the target file exists and is valid, supplying `content` is an ERROR. When content is supplied for a missing or broken file: FIRST write the provided source into the session code file, THEN follow the standard open protocol — build the tree, write the tree, and record checksums (КС) — and create the normal session git initial commit.

---

### `{d003}` — In-session editing invariant

**AUGMENT** — replaces current text to add hide/unhide cycle (nuance **b**), per-mutation stripped source export and checksum recording (nuance **c**), and TEMP mirror semantics; resolves conflict with "in-session source copy is not touched by tree edits."

**Current verbatim HRS:**

> {d003} During an open session, all editing operates on the tree file inside the session directory. The tree is the source of truth. The in-session source copy is not touched by tree edits; only the tree changes during editing. Every tree modification without exception must be followed immediately by writing the tree to disk and creating a git commit. One tree modification equals one git commit. This invariant has no exceptions.

**Proposed (AUGMENT):**

> {d003} During an open session, all editing operates on the tree file inside the session directory; the tree is the source of truth. Before each mutation, any node metadata that carries markers is hidden into the tree content as format-native comments (or equivalent inline marker form); the mutation is applied to that temporarily denuded representation; after the mutation, markers and metadata are fully restored to their canonical positions — the node id lives in metadata where the format provides a metadata slot, and as a format-native comment at the END of the block where it does not. Every tree modification without exception must be followed immediately by: writing the updated tree file to disk inside the session directory; exporting the in-session source copy by stripping all special marker comments from the tree via `unmark` and writing that clean source into the session directory (the session TEMP artefacts mirror the original project's source and tree layout, not the live project files); recording SHA-256 content checksums for both the tree file and the exported source copy; and creating a git commit in the session repository that captures both artefacts. One tree modification equals one git commit. This invariant has no exceptions.

---

### `{d004}` — Write (commit) command

**KEEP** — nuance **(e)** (atomic copy-out to live project files) is already present.

> {d004} The write (commit) command makes a file edit permanent in two stages. First, inside the session: it writes the current tree, regenerates the in-session source file from that tree via `unmark`, and commits both. Second, immediately after the in-session commit: it copies both artifacts out to their external locations — the regenerated source over the live project file, and the tree onto its co-located sibling position next to that source — replacing the previous external copies. The copy-out of the two artifacts is atomic: either both are written externally or neither is.

---

### `{d005}` — Close session

**AUGMENT** — adds explicit "without any checks" for nuance **(f)**.

**Current verbatim HRS:**

> {d005} Closing a session deletes the session directory entirely, including its git repository. Only the final co-located tree file survives. The git history of the session is ephemeral and does not persist after close.

**Proposed (AUGMENT):**

> {d005} Closing a session deletes the session directory entirely, including its git repository, without performing any validation, checksum, or consistency checks. Only the final co-located tree file survives (if previously written out via the write command). The git history of the session is ephemeral and does not persist after close.

---

### `{d006}` — Dulwich dependency declaration

**KEEP**

> {d006} The dependency on `dulwich` must be declared in the project's dependency manifest (requirements file or pyproject.toml). It is currently installed in the venv but not declared.

---

### Block 5 — Session Git API (`{e001}`–`{e006}`)

All Block 5 paragraphs are **KEEP**. They fully support the session git MCP API target model.

#### `{e001}`

**KEEP**

> {e001} The session git repository is exposed through MCP as a set of session-scoped commands. Every command in this set requires a `session_id` parameter. A command called without an active session returns an error; it does not attempt to access the file system without a valid session context.

#### `{e002}`

**KEEP**

> {e002} `session_git_log(session_id)` returns the commit history of the session repository: commit hash, message, and timestamp for each commit. Implementation reads history via `repo.get_walker()` (dulwich); `porcelain.log` is not used because it writes to stdout and returns None.

#### `{e003}`

**KEEP**

> {e003} `session_git_diff(session_id, *, mode, rev_a, rev_b=None)` returns a diff in one of two modes. Mode `tree` diffs two tree-file versions (two commits) and shows what changed at the marker/node level between them. Mode `source` diffs a tree-file version (rev_a) against the source file held inside the session directory, showing divergence between the marked tree and that in-session source. The in-session source is the copy made at open, rewritten only by the write command via `unmark`; the live project file on disk is not an input to this diff.

#### `{e004}`

**KEEP**

> {e004} `session_git_show(session_id, rev)` returns the full content of the tree file at the given commit.

#### `{e005}`

**KEEP**

> {e005} `session_git_status(session_id)` returns uncommitted changes relative to HEAD. Under the invariant that every tree modification immediately produces a commit, this should always be empty; the command exists as a consistency check.

#### `{e006}`

**KEEP**

> {e006} `session_git_revert(session_id, rev)` rolls the session tree back to the state at `rev` by creating a new revert commit. The git history is preserved; no commit is deleted. Because one tree modification equals one commit, revert rolls back by individual node edits.

---

### Marker contract cross-ref (nuance a)

Universal marker placement belongs in the marker contract (Block 2), not Block 4. `{b005}` is kept verbatim (Python-specific detail). Augment `{b000}` with the universal ALL-nodes rule.

#### `{b000}` — Format handler contract

**KEEP** + **AUGMENT** (append universal rule)

**Current verbatim HRS:**

> {b000} Every format has a dedicated handler that implements a common four-operation contract: `parse_content(file_path, content) → list[TreeNode]` builds the node tree from source content; `mark(content) → marked_text` embeds node-id markers natively into the content using the format's own syntax; `unmark(marked_text) → content` strips all markers and reproduces the original source bytes exactly; `sidecar_path(source_abs) → Path` returns the sibling tree-file path for the given source file. All handlers are registered in a central registry keyed by file-extension and live under `core/tree_handlers/`. No handler may use another format's marker syntax. The common contract is the only coupling between handlers; each handler's internal implementation is entirely format-specific.

**Proposed (AUGMENT)** — append to end of existing `{b000}` paragraph:

> Every addressable node in every format receives a marker without exception: where the format provides a metadata field or equivalent structured slot, the node id lives in that metadata; where no such slot exists, the marker appears as a format-native comment at the END of the block (never mid-lexeme, per `{a004}`).

#### `{b005}` — Python hybrid scheme (cross-reference only)

**KEEP** — no change proposed in this package.

> {b005} Python files use a hybrid scheme determined by CST node type. Where a CST node carries a metadata dict (function definitions, class definitions, decorated statements, and similar named constructs that already store metadata in the existing codebase), the node id is written into that metadata dict under a reserved key. Where a CST node has no metadata dict (simple statements, expressions, import lines, assignment targets), a trailing comment `# ___id___:<uuid>` is appended at the end of the last physical line of the logical block. The minimally-addressable block is the complete logical statement or expression as parsed by the CST, never an individual physical line within it. A multiline docstring is one block; its marker appears on the line containing the closing `"""`, after the quotes. Line continuations (`\`) and bracket-continuation expressions (open paren/bracket across lines) are one block; the marker appears on the last physical line of the continuation. A shebang line (`#!/...`) is not addressable and carries no marker. The `unmark` operation removes metadata-dict entries and trailing comments without altering any other whitespace, and must reproduce the original source byte-for-byte.

---

### Lifecycle nuances coverage table

| Nuance | Description | Status in current HRS | Resolution | Label(s) |
|--------|-------------|----------------------|------------|----------|
| **(a)** | Every addressable node receives a marker (metadata slot or end-of-block comment) | Partially in `{b005}` (Python only); `{b000}` lacks universal rule | **Newly added** via `{b000}` augmentation | `{b000}`, `{b005}` (KEEP) |
| **(b)** | Hide metadata into format-native comments before each mutation; restore after | **Not in HRS** | **Newly added** via `{d003}` augmentation | `{d003}` |
| **(c)** | Per-mutation: write tree, export stripped source to session TEMP, record checksums, git commit | Partially implied by `{d003}` git commit; export/checksum detail missing | **Newly added** via `{d003}` augmentation | `{d003}` |
| **(d)** | Per-mutation git commit in session repository (one edit = one commit) | **Already in HRS** `{d003}` (pre-augmentation core invariant retained) | **KEEP** in augmented `{d003}` | `{d003}` |
| **(e)** | WRITE atomically copies session artefacts to live project source + co-located tree | **Already in HRS** | **KEEP** `{d004}` verbatim | `{d004}` |
| **(f)** | CLOSE deletes session directory without validation or consistency checks | Implied but not explicit ("without any checks" absent) | **Newly added** via `{d005}` augmentation | `{d005}` |
| **(g)** | Open `content` param: only when target non-existent or source/tree broken; ERROR if valid file exists; write-then-standard-protocol when accepted | **Not in HRS** | **Newly added** via `{d002}` augmentation (**FINAL-2**) | `{d002}` |

---

### Implementation-scope note (not HRS text)

Current `universal_file_*` commands use an **in-memory `EditSession`** (`commands/universal_file_edit/session.py`) with `.draft` lockfiles — not the session-directory model described in Block 4. That divergence is **implementation work** to build toward the HRS target; it is **not** grounds to rewrite `{d001}`–`{d005}` to match today's code.

---

## Section P — Preview (1:1, per-format thresholds)

Preview paragraphs encode **1:1 alignment with existing preview code**, with `{i005}` revised per **FINAL-1** to use **per-format** line thresholds (source lines; JSON normalized before line count) instead of a single global threshold.

### `{i003}` — Session-scoped preview navigation

**MODIFY**

**Current verbatim HRS:**

> {i003} When a `session_id` is supplied in the preview request, the navigation operates on the in-session tree draft (the tree file inside the session directory) rather than the disk tree file. This is the mechanism for previewing unsaved edits before committing them. A `session_id` referencing a closed or non-existent session returns an error.

**Proposed (MODIFY):**

> {i003} When a `session_id` is supplied in the preview request, navigation operates on the in-session tree or draft held by the active `EditSession` (in-memory CST for Python, `{file}.draft` and in-memory roots for JSON/YAML, `{file}.draft` for text) rather than only the last committed on-disk artefacts. This is the mechanism for previewing unsaved edits before write. A `session_id` referencing a closed or non-existent session returns an error.

---

### `{i005}` — Selector and inline-vs-drilldown threshold

**MODIFY (FINAL-1)** *(per-format thresholds — replaces prior single global threshold)*

**Current verbatim HRS:**

> {i005} A selector expression applied in phase 2 may be a slice string of the form `start:end` (zero-based, exclusive end) to cap the returned block count, or a list of specific node ids to cherry-pick blocks. The preview budget (maximum lines and maximum value preview length) limits render output independently of the selector; blocks that exceed the budget are truncated with an explicit truncation marker.

**Proposed (MODIFY):**

> {i005} A selector expression applied in phase 2 may be a slice string of the form `start:end` (zero-based, exclusive end) to cap the returned block count, or a list of specific node ids to cherry-pick blocks. Full inline rendering of a node's source text (annotated mode with node-id prefixes at the start of each physical line) is used when the node's line span is strictly less than that format's `full_text_max_lines` threshold; when the span equals or exceeds the format's threshold, or when that format's threshold is zero, preview falls back to collapsed structural drilldown. Each supported format — Python (`.py`), JSON (`.json`), YAML (`.yaml`/`.yml`), Markdown (`.md`), and plain text (`.txt`/`.rst`) — has its own independent `full_text_max_lines` value; the default is 200 source lines for every format unless configured otherwise. Setting a format's threshold to zero disables full inline rendering for that format (drilldown only). Thresholds are measured in source lines for every format, not bytes. For JSON specifically: content must be normalized to a printable (pretty-printed) form BEFORE line counting and inline rendering, so the line-based threshold is meaningful on the JSON preview/handler path. A separate `max_chars` budget may paginate the serialized preview envelope but does not control the inline-versus-drilldown decision.

---

### `{i006}` — Python CST preview blocks

**MODIFY**

**Current verbatim HRS:**

> {i006} Preview for Python files produces CST-node blocks with type labels (e.g. `FunctionDef`, `ClassDef`, `ImportFrom`), a source line range (`L<start>-<end>` or `L<n>` for single-line), and attribute summaries (function name, decorator list, base classes, etc.). Nested drill-down follows CST parent-child relationships: drilling into a `ClassDef` exposes its method `FunctionDef` children; drilling into a `FunctionDef` exposes its body statements. A `tree_id` from a prior `cst_load_file` call can be passed instead of `file_path` to reuse an already-loaded CST.

**Proposed (MODIFY):**

> {i006} Preview for Python files produces CST-node blocks with type labels (e.g. `FunctionDef`, `ClassDef`, `ImportFrom`), source line ranges (`L<start>-<end>`), and attribute summaries. In block enumeration and collapsed text rendering, `IndentedBlock` wrapper nodes are not emitted as separate blocks; their direct statement children appear in place of the block container. When rendering inside compound statements (`If`, `For`, `While`, `Try`, `With`, `Match`, function/class bodies), the compound statement header line may still appear as a summary row with an ellipsis when nested compound statements are present; drilldown follows CST parent-child relationships via stable ids in sidecar metadata. A `tree_id` from a prior `cst_load_file` call may be passed instead of `file_path` to reuse an already-loaded CST.

---

### `{i007}` — Node-id prefix at line start

**ADD**

**Proposed (ADD):**

> {i007} In preview annotated and full-text rendering modes, every node-id marker prefix is placed at the start of the physical source line: the form `[<node_id>] ` followed by the original line content with no trailing or inline marker placement. Lines without an associated node id use blank padding of fixed width so column alignment of source text is preserved across the rendered block.

---

### `{i008}` — Strip legacy identity comments before render

**ADD**

**Proposed (ADD):**

> {i008} Before preview renders Python source text, legacy identity comments are removed from the logical source used for display: the trailing `# cst-node-ids: begin` … `# cst-node-ids: end` block and whole-line `# @node-id: <uuid>` comments. Stripping occurs on both committed on-disk source and in-session draft lines used for diff preview. Preview output never shows these special comments; node ids in preview come from sidecar metadata prefixes, not from preserved inline comment markers.

---

## Section C — `{c005}` unified build

**MODIFY** — keep prior package proposed text (TreeBuilder.build via HandlerRegistry, checksum in tree file AND returned reference, legacy parity oracle until G-000).

**Current verbatim HRS:**

> {c005} A dedicated tree-creation module (`core/tree_lifecycle/builder.py` or equivalent) exposes `recreate_tree_from_content(*, kind, content, source_path, tree_path, content_checksum)`. It dispatches to the appropriate per-format handler based on `kind`, writes the resulting tree file to `tree_path` as a sibling of the source file, and records `content_checksum` in the tree file so that subsequent validity checks can compare it against the current source checksum. This module is the single place that writes tree files; no other module writes tree files directly.

**Proposed (MODIFY):**

> {c005} A dedicated tree-creation module (`core/tree_lifecycle/builder.py` or equivalent) exposes `TreeBuilder.build(*, content, source_abs, file_path, content_checksum)`. It resolves the appropriate FormatHandler via `HandlerRegistry.default_registry().resolve(source_abs)`, produces natively-marked tree content via `FormatHandler.mark(content)`, writes the tree file to `FormatHandler.sidecar_path(source_abs)` as a sibling of the source file, and records `content_checksum` in the tree file AND exposes it in the returned tree reference so that subsequent validity checks can compare it against the current source checksum. This module is the single place that writes tree files on the canonical unified path; no other module writes tree files directly. The legacy `recreate_tree_from_content(*, kind, ...)` dispatch remains in the codebase as an untouched parity oracle until G-000 cutover.

---

## Implementation scope implied (not HRS text)

The following must be **built** because the target lifecycle in Block 4 diverges from current `universal_file_*` behavior. These items become plan steps **after HRS approval**; they are not HRS paragraph text.

- **Session directory model** (`{d001}`) vs current in-memory `EditSession` + lockfile
- **Per-mutation session git commits** (`{d003}`) vs git only on optional project write
- **Hide/unhide metadata cycle** before and after each mutation (`{d003}` augment)
- **Per-mutation tree write + stripped source export + checksum recording** in session TEMP (`{d003}` augment)
- **Markers on all addressable nodes** — metadata slot or end-of-block comment (`{b000}` / `{b005}`)
- **Open-from-content rules** (`{d002}` **FINAL-2**) vs unrestricted or ambiguous `content` on open
- **Per-format preview thresholds** (`{i005}` **FINAL-1**) vs current single global `full_text_max_lines`
- **`session_git_*` MCP commands** wired to session-directory git repo (`{e001}`–`{e006}`)
- **WRITE** copies session artefacts atomically to live project files (`{d004}`)
- **CLOSE** blind session-directory delete without validation (`{d005}` augment)

---

## Remaining tiny open items

**RESOLVED** — all items closed by user decisions FINAL-1 and FINAL-2 (2026-05-30):

| Item | Resolution |
|------|------------|
| Preview threshold unit (lines vs bytes) | **FINAL-1:** source LINES for every format; JSON normalized to printable form before line counting; default 200 lines per format; 0 disables; bytes NOT used |
| Open-from-content param | **FINAL-2:** `content` accepted ONLY when target file non-existent or source/tree broken/corrupted; ERROR if file exists and valid; when accepted: write content to session file first, then standard build/tree/checksum/git protocol |
