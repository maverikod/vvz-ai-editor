# Marked Tree Unification — Node-ID Cascade Review Package

**Date:** 2026-05-30  
**Plan:** `marked_tree_unification`  
**Repo root:** `/home/vasilyvz/projects/tools/code_analysis`  
**Status:** Planning-only — HRS cascade proposal; no `docs/plans/**` edits in this pass  
**Prior analysis:** agent bf45e1b9 (full UUID in markers + UniversalNodeId layer)  
**User-locked model:** N1–N7 below (final; no alternatives)

## Locked node-id model (N1–N7)

| ID | Rule |
|----|------|
| N1 | Canonical identity = UUID4 in tree-file **metadata** (one per node). Never in marked content; never crosses external API. |
| N2 | In-source/in-tree marker = per-file **integer short_id**, monotonic, never reused after deletion; metadata holds **next_free**. |
| N3 | Tree file = marked content (short_id markers) + metadata section (UUID per node, short_id↔UUID map, next_free). |
| N4 | Dedicated **node-id-map** code block: exactly three operations — (a) build/generate map from tree nodes; (b) validate-and-repair; (c) resolve both directions. Repurposes G-006; absorbs G-007 per-format wiring. No separate "universal" id. |
| N5 | External API (preview, edit, query, grep/indexer): **(file, short_id)** only; UUID never at API; resolve within loaded tree/file. |
| N6 | Rebuild on checksum mismatch (outside session): **preserve next_free** from existing tree when present; brand-new tree starts next_free=1; validate-and-repair keeps UUIDs stable for unchanged nodes. |
| N7 | Invalid/plain-text edit-gate: in-session marked content has **no markers**; metadata (UUIDs, map, next_free) preserved; re-validation rebuilds markers via node-id-map block. |

## Subordinate agents state

| Agent | Status | Scope | Last output |
|-------|--------|-------|-------------|
| researcher_doc | done | Zero-trust HRS/MRS verbatim extraction | dc7a55b1 — all requested labels; {a007} missing |
| doc_writer | done | This review file | a57b9459 — 431 lines on disk |
| planner_auto | idle | — | — |
| coder_auto | idle | — | — |
| tester_auto | idle | — | — |
| tester_ca | idle | — | — |
| researcher_code | idle | — | — |

---

## Section 1 — HRS binding paragraph diffs

For each entry: **CURRENT** (verbatim from `docs/plans/marked_tree_unification/source_spec.md` per researcher_doc) then **PROPOSED** (paste-ready).

### {a001} — Marker / short_id handle

**CURRENT:**

```
{a001} A node-id marker is a short, format-specific string that identifies
exactly one addressable block in a tree file. A marker is the node id: the
marker string is the identifier, not a pointer to an identifier stored
elsewhere.
```

**PROPOSED:**

```
{a001} A node-id marker is a format-specific token that identifies exactly one addressable block in the marked content of a tree file. In every format the in-content marker token is a per-file monotonic integer short_id (decimal digits, no leading-zero requirement beyond uniqueness). The marker is a handle, not the canonical identity: it resolves to exactly one UUID4 stored in the tree file metadata section via the short_id↔UUID map (see {a002}, {n001}). The short_id never appears outside the tree file and never crosses the external API boundary.
```

### {a002} — Tree file structure

**CURRENT:**

```
{a002} Tree files contain source content with node-id markers embedded
natively. Markers appear only in tree files; the real source file is never
modified and remains clean.
```

**PROPOSED:**

```
{a002} A tree file has two parts: (1) marked content — source-equivalent bytes with short_id markers embedded natively per format; (2) a trailing metadata section holding, for every node, its canonical UUID4, the short_id↔UUID map, the next_free counter for short_id allocation, and the source content_checksum used for validity (see {a006}). Markers (short_ids) appear only in the marked content; canonical UUIDs appear only in metadata. The real source file is never modified and remains clean.
```

### {a003} — Marker contract (unchanged ops; short_id markers)

**CURRENT:** (verbatim — keep unmark SHA-256 rule)

```
{a003} The marker contract defines three operations that every per-format
handler must implement: `mark(content) → marked_text`, `parse(marked_text) →
tree`, and `unmark(marked_text) → content`. The `unmark` operation must
reproduce the original source bytes exactly — verified by SHA-256 checksum
comparison of `unmark(mark(source))` against `source`.
```

**PROPOSED:**

```
{a003} The marker contract defines three operations that every per-format handler must implement: `mark(content) → marked_text`, `parse(marked_text) → tree`, and `unmark(marked_text) → content`. Markers embedded by `mark` use integer short_id tokens per {a001}, not UUIDs. The `unmark` operation strips all marker tokens and metadata-bound marker forms and must reproduce the original source bytes exactly — verified by SHA-256 checksum comparison of `unmark(mark(source))` against `source`.
```

### {a006} — Checksum sync (add rebuild / next_free pointer)

**CURRENT:** (verbatim)

```
{a006} Synchronization between a tree file and the corresponding source file
is done by SHA-256 checksum of source content. If the checksum stored in the
tree file matches the current checksum of the source file, the tree is valid.
If the checksums differ outside an active session, the tree is invalid and
must be rebuilt from the source file.
```

**PROPOSED:**

```
{a006} Synchronization between a tree file and the corresponding source file is done by SHA-256 checksum of source content recorded in the tree file metadata section. If the stored checksum matches the current checksum of the source file, the tree is valid. If the checksums differ outside an active edit session, the tree is invalid and must be rebuilt from the clean source file via TreeBuilder, applying short_id allocation rules in {a007}: preserve next_free from the existing tree file when one exists; when no prior tree exists, initialize next_free to 1. Rebuild assigns fresh short_ids to nodes but validate-and-repair (see {n002}) preserves UUID4 for nodes whose underlying content identity is unchanged.
```

### {a007} — NEW (short_id allocation / rebuild)

**CURRENT:** *(label absent in source_spec.md)*

**PROPOSED:**

```
{a007} Short_id allocation is per tree file. Metadata holds next_free, the lowest integer not yet issued. Each new addressable node receives short_id = next_free, then next_free increments by 1. A short_id is never reused after its node is deleted — retired ids remain absent from the map. On rebuild from source when a prior tree file exists, next_free is copied from that file's metadata so new ids continue above all previously issued ids (including retired ones). On first-time tree creation, next_free starts at 1. The node-id-map block validate-and-repair operation enforces map consistency with marked content and keeps UUID4 stable for nodes whose content identity is unchanged across repair.
```

### {b000} — Handler contract

**CURRENT:** (verbatim — long paragraph from researcher)

```
{b000} Every format has a dedicated handler that implements a common
four-operation contract: `parse_content(file_path, content) → list[TreeNode]`
builds the node tree from source content; `mark(content) → marked_text`
embeds node-id markers natively into the content using the format's own
syntax; `unmark(marked_text) → content` strips all markers and reproduces
the original source bytes exactly; `sidecar_path(source_abs) → Path` returns
the sibling tree-file path for the given source file. All handlers are
registered in a central registry keyed by file-extension and live under
`core/tree_handlers/`. No handler may use another format's marker syntax.
The common contract is the only coupling between handlers; each handler's
internal implementation is entirely format-specific. Every addressable node
in every format receives a marker without exception: where the format provides
a metadata field or equivalent structured slot, the node id lives in that
metadata; where no such slot exists, the marker appears as a format-native
comment at the END of the block (never mid-lexeme, per `{a004}`).
```

**PROPOSED:** Replace closing "node id" phrasing with:

- Every addressable node receives a **short_id marker** in marked content per format rules in {b001}–{b005}.
- Canonical UUID4 for each node is written only in tree metadata, not by handlers inventing API-facing ids.
- Handlers use the node-id-map block ({n001}–{n003}) to resolve short_id↔UUID when building or parsing trees; they do not embed UUIDs in markers.

(Keep the rest of {b000} CURRENT text for parse_content, mark, unmark, sidecar_path, registry, no cross-format syntax — only adjust node-id sentences as above.)

```
{b000} Every format has a dedicated handler that implements a common
four-operation contract: `parse_content(file_path, content) → list[TreeNode]`
builds the node tree from source content; `mark(content) → marked_text`
embeds node-id markers natively into the content using the format's own
syntax; `unmark(marked_text) → content` strips all markers and reproduces
the original source bytes exactly; `sidecar_path(source_abs) → Path` returns
the sibling tree-file path for the given source file. All handlers are
registered in a central registry keyed by file-extension and live under
`core/tree_handlers/`. No handler may use another format's marker syntax.
The common contract is the only coupling between handlers; each handler's
internal implementation is entirely format-specific. Every addressable node
receives a short_id marker in marked content per format rules in {b001}–{b005}.
Canonical UUID4 for each node is written only in tree metadata, not by handlers
inventing API-facing ids. Handlers use the node-id-map block ({n001}–{n003})
to resolve short_id↔UUID when building or parsing trees; they do not embed
UUIDs in markers.
```

### {b001} — Text

**CURRENT:** (verbatim from researcher — line-prefixed node id)

```
{b001} Text files (`.txt`, `.rst`) use line-level markers. Each line in the
tree file is prefixed with a node id and a fixed separator character before
the original line content. The node id for the first line of each paragraph
encodes a paragraph flag that distinguishes it from continuation lines.
Paragraph boundaries are the only structural delimiter: two or more
consecutive newlines (`\n\n`) mark a paragraph break; single newlines are
continuation. The handler produces exactly two node levels — paragraph and
line — and no deeper nesting. Blank lines that serve as paragraph separators
carry no marker and are reproduced verbatim by `unmark`.
```

**PROPOSED:**

```
{b001} Text files (`.txt`, `.rst`) use line-level markers. Each marked line is prefixed with `P:<short_id>:` or `L:<short_id>:` (paragraph vs continuation line) followed by the original line content, where short_id is a decimal integer. Paragraph boundaries: two or more consecutive newlines (`\n\n`); single newlines are continuation. Exactly two node levels — paragraph and line. Blank separator lines carry no marker and reproduce verbatim on unmark. Prefix width for preview alignment is sized for integer short_id magnitude, not UUID width (see {i007}).
```

### {b002} — Markdown

**CURRENT:**

```
<!-- id:<uuid> -->
```

**PROPOSED:**

```
{b002} Markdown files use HTML comments as markers: `<!-- id:<short_id> -->` on its own line immediately before each addressable block, where short_id is a decimal integer. (Keep markdown-it-py 4.0.0, block types, inline non-addressable, unmark removes comment lines without altering whitespace — same as CURRENT.)
```

### {b003} — YAML

**CURRENT:**

```
___id___: <uuid>`, wrap `{___id___: <uuid>, v: <scalar>}
```

**PROPOSED:**

```
{b003} YAML files use `___id___` as the first key of each addressable mapping; its value is integer short_id. Scalar sequence elements wrap as `{___id___: <short_id>, v: <scalar>}`. Marked file remains valid YAML. Unmark removes all `___id___` keys and `v`-unwrap; byte-exact reproduction unchanged.
```

### {b004} — JSON

**CURRENT:**

```
"___id___": "<uuid>"
```

**PROPOSED:**

```
{b004} JSON uses recursive wrapper `{"___id___": <short_id>, "v": <original_value>}` at every level, where short_id is a JSON number (integer). Unmark extracts `v` recursively; byte-exact structure unchanged; no alternative wrapper shapes.
```

### {b005} — Python

**CURRENT:**

```
metadata dict + `# ___id___:<uuid>`
```

**PROPOSED:**

```
{b005} Python hybrid scheme: metadata dict carries canonical UUID4 under a reserved metadata key; in-content marker is integer short_id only — metadata dict short_id field where the format uses metadata for markers, else trailing comment `# ___id___:<short_id>` on the last physical line of the block. (Keep CST block boundaries, shebang, unmark byte-exact — same as CURRENT except uuid→short_id in comment and metadata marker role split per N1.)
```

Clarify in PROPOSED: **metadata dict holds UUID4**; **comment/metadata marker slot holds short_id** for addressing within tree file.

### Block 12–13 replacement — retire {l001}–{l003}, {m001}–{m002}

**CURRENT {l001}:**

```
{l001} The universal node id is a dedicated, standalone code block consisting of exactly two pure functions: `generate() -> str` produces a new universal identifier in a single uniform short form that is identical across every format, and `validate(value) -> bool` returns whether a value is a well-formed universal identifier in that same form. This block is the only source of universal identifiers; no format handler generates them on its own. The block depends on nothing else in the system and is built in isolation.
```

**CURRENT {l002}:**

```
{l002} The universal node id does not replace the format-specific node id of {a001}. Each format keeps its own native identifier mechanism unchanged — CST UUID, sidecar stable id, marker comment id, and the `___id___` key all remain exactly as defined in Blocks 1 and 2. The uniform universal form is distinct from, and additional to, the native identifier.
```

**CURRENT {l003}:**

```
{l003} Every format handler uses `generate()` and `validate()` to build a native-to-universal identity map for its tree file. The handler is responsible for producing universal identifiers only through this block and for validating them only through this block; it never invents its own universal-id scheme.
```

**CURRENT {m001}:**

```
{m001} For every format, the handler maintains a native-to-universal identity map appended at the end of the tree file, in a clearly delimited trailing section after the format's own content. Each entry pairs one native identifier with one universal identifier produced by the universal node id block of {l001}. The native identifier mechanism is unchanged and the map is purely additive; the handler keeps the map in sync as nodes are added or removed.
```

**CURRENT {m002}:**

```
{m002} The identity map is wired into every preview and every edit operation: each preview exposes universal identifiers and accepts a universal identifier as the node reference, and each edit operation accepts a universal identifier as its target, translating between native and universal identifiers through the per-format map at the boundary. The underlying preview, navigation, and edit logic is not rewritten; only the translation is added. An unrecognised or invalid universal identifier is an input error, never a silent ignore. This integration (G-007) is strictly the final plan step: it runs after G-000 sidecar layout cutover and G-006 universal node id are complete, when every other block has been built and verified end to end.
```

**RETIRED labels:** {l001}, {l002}, {l003}, {m001}, {m002} — remove from binding set after cascade; remap MRS source_labels to new block.

**NEW Block — Node identity & map (proposed labels {n001}–{n003})**

**PROPOSED {n001}:**

```
{n001} Canonical node identity is UUID4. Each addressable node has exactly one UUID4 stored in the tree file metadata section. UUID4 is never embedded in marked content, never returned by preview/edit/query/grep MCP commands, and never accepted as an external node reference. UUID4 is assigned at node creation and kept stable across validate-and-repair for nodes whose underlying content identity is unchanged.
```

**PROPOSED {n002}:**

```
{n002} The node-id-map block is a dedicated module exposing exactly three operations: (1) build — scan the tree's marked content and metadata to generate or refresh the short_id↔UUID map and per-node UUID entries; (2) validate_and_repair — detect inconsistencies between markers, map, UUID entries, and next_free, then fix them while preserving UUID4 for unchanged nodes per {a007}; (3) resolve — bidirectional lookup short_id→UUID and UUID→short_id within one tree file context. No other public entry points perform map mutation. This block replaces the former universal-node-id generate/validate pair and centralizes map logic previously split across format handlers.
```

**PROPOSED {n003}:**

```
{n003} External consumers (preview navigation, edit operations, tree query, grep/indexer block assembly) address nodes by (project-relative file path, short_id) only. short_id is the integer marker token from the tree file for that file. Resolution to UUID4 happens only inside the server when operating on a loaded tree, via the node-id-map block. An unrecognised short_id for that file is an input error, never silent ignore. File path disambiguates short_id — the same integer may exist in different files' trees independently.
```

### {i002} — node_ref

**CURRENT:** (verbatim — format-specific UUID/stable id)

```
{i002} A `node_ref` in a preview request is always a node id (marker) from
the tree file — never a line number. The format of the node id is
format-specific: for Python files it is a stable UUID from the CST node
metadata; for JSON/YAML files it is the stable id from the sidecar tree; for
text and markdown files it is the node id embedded in the marker comment. An
unrecognised `node_ref` returns an input error; it is never silently ignored.
```

**PROPOSED:**

```
{i002} A node_ref in a preview request is always a short_id (integer) valid for the requested file's tree — never a line number and never a UUID4. The server resolves short_id to internal UUID4 via the tree file metadata map in the loaded tree context. An unrecognised short_id returns an input error; it is never silently ignored.
```

### {i007} — Annotated prefix width

**CURRENT:**

```
{i007} In preview annotated and full-text rendering modes, every node-id
marker prefix is placed at the start of the physical source line: the form
`[<node_id>] ` followed by the original line content with no trailing or
inline marker placement. Lines without an associated node id use blank padding
of fixed width so column alignment of source text is preserved across the
rendered block.
```

**PROPOSED:**

```
{i007} In preview annotated and full-text rendering modes, every line that has an associated short_id is prefixed at the start of the physical source line with `[<short_id>] ` (decimal integer) followed by the original line content. Lines without an associated short_id use blank padding of fixed width so column alignment is preserved; the fixed width is sized for the maximum short_id string length expected for the tree (integer digit count), not for UUID width.
```

### Collateral HRS edits (not full CURRENT/PROPOSED blocks — list for cascade)

| Label | Change summary |
|-------|----------------|
| {f002} | Preview returns **short_id** handles, not UUID |
| {h001}–{h007} | Edit targets use **short_id** in VALID tree mode |
| {h008}/{h009} | INVALID mode: no markers in content; metadata preserved; re-validation uses node-id-map **build** to restore markers |
| {i004} | Remove sidecar UUID node_ref walk-up; JSON/YAML use **short_id** only |
| {i008} | Python preview prefixes show short_id; strip legacy `# @node-id` comments; UUID only in metadata |
| {j001} | Query returns **short_id** list |
| {d003} | Align hide/unhide with short_id markers + metadata UUID preservation (N7) |

---

## Section 2 — MRS cascade outline (no edits)

### C-002 NodeId — redefine

- **Was:** marker string is the identifier; format-specific UUID in marker.
- **Proposed:** NodeId = integer **short_id** — in-marker handle and sole external API reference (with file path). Properties: monotonic per file, never reused, resolves via map; unrecognised → input error.
- **source_labels:** {a001}, {a007}, {n003}, {i002}, {f002}, {j001}; drop UUID-in-marker refs.

### New / repurposed concepts

| Proposed id | Name | Role |
|-------------|------|------|
| C-024 → split/rename | **NodeCanonicalId** or keep C-024 as **TreeNodeUuid** | UUID4 in metadata only (N1) |
| C-025 (new) | **NodeIdMap** | Three operations build / validate_and_repair / resolve (N4) |
| C-003 TreeFile | Extend properties | marked content + delimited metadata section (map, next_free, checksum, per-node UUID) — **conflicts with current "natively-marked content only"** → needs user ruling |

### Retire / remove relations

- C-007 → C-024 (universal id generation)
- C-015 → C-024
- C-016 → C-024
- Remove "universal id", "native-to-universal", "generate/validate" properties from C-024

### Add relations

- C-003 **owns** NodeIdMap (or C-025)
- C-007 **uses** NodeIdMap (handlers call resolve at parse/mark boundaries)
- C-002 **depends_on** NodeIdMap for resolution to UUID internally
- C-015, C-016 **use** C-002 only (short_id at API) — drop C-024 from external surface

### source_labels remap

- Retired: {l001}–{l003}, {m001}, {m002}
- Added: {n001}, {n002}, {n003}, {a007}

---

## Section 3 — GS / TS / AS impact (plan-only inventory)

**Cascade invalidates:** entire plan → `needs_review` per cascade rules; code not yet executed per assignment.

| GS | Impact | Rough AS touch count |
|----|--------|---------------------|
| **G-001** | All format handlers {b001}–{b005}; marker contract A-001/A-002; TreeNode; registry — UUID out of markers, short_id in | ~12 AS |
| **G-002** | TreeBuilder writes metadata section; TreeLifecycle checksum + rebuild preserves next_free | ~7 AS |
| **G-003** | Session mutation hide/unhide (N7); metadata preserved without markers in INVALID mode | ~14 AS |
| **G-004** | Preview {i002}/{i007}; edit ops; tree query — short_id only; **prefix width → integer** (plan prompt constant ~6–12 chars, not 40/UUID) | ~11 AS |
| **G-005** | Grep/indexer return short_id | ~11 AS |
| **G-006** | **Repurpose:** 1 AS → node-id-map module (build, validate_and_repair, resolve); drop generate/validate universal | 1 AS rewrite |
| **G-007** | **Fold into G-001 + G-006:** retire 7 AS identity-remap layer; per-format map wiring absorbed by handlers + central map | 7 AS obsolete / merge |
| **G-000** | Sidecar read/write must parse/write metadata section | ~16 AS |

**Execution order after cascade:** likely G-001 + G-006 (map block) early → G-002 → G-003 → G-004 → G-005 → G-000; **G-007 removed as separate GS**.

**Total AS affected:** ~79 (full plan regen expected).

---

## Section 4 — Open edge cases (one-line user rulings)

1. **Metadata section format (C-003):** Delimiter and serialization for trailing metadata (JSON tail? YAML front-matter inverse?) — HRS currently says on-disk tree is "natively-marked content" only; N3 requires a second section.
2. **Text handler `P:`/`L:` namespace:** Confirm `P:<short_id>:` / `L:<short_id>:` vs bare integer prefix — affects parse and preview width.
3. **JSON/YAML `___id___` type:** Integer in JSON number and YAML unquoted int — confirm schema validators and edit ops accept numeric not string.
4. **Python dual key:** Reserved metadata key name for UUID4 vs short_id in CST metadata — single dict or split keys?
5. **G-004 prefix constant:** Replace UUID-oriented width (36+ brackets ≈39–40) with `SHORT_ID_PREFIX_WIDTH` derived from max(short_id) or fixed cap (e.g. 10 digits)?

---

## Section 5 — Cascade procedure reminder

1. Human authorizes HRS edits (paste Section 1 PROPOSED blocks).
2. Re-project `spec.yaml` (machine_spec only via cascade).
3. Reassess all G-steps; merge G-007 into G-001/G-006; regen TS/AS.
4. cycle_1 + cycle_2 + tactical + atomic green before code execution restart.

---

End of file.
