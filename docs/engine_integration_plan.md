# Staged plan: wiring `tree_engine` into the editor

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Status: plan only. No production file is changed by this document. Every module, class and
function named below was read in this worktree; measured facts are marked **[M]**. Where I could
not establish something, §9 says so.

Governing rulings folded in: the external MCP surface is **frozen** (internals only); the engine
ships as the PyPI distribution **`ai-editor-tree-engine`** (import package stays `tree_engine`,
MIT, version locked to the server); a genuine capability gap is closed **in the engine**, never
routed around in `ai_editor/`.

## 0. Measured baseline

- **[M]** `grep -rln tree_engine ai_editor/` → 0 files. Only `adapter/`, `pipeline/`,
  `benchmarks/` and `tests/` import it. The editor runs entirely on its own machinery.
- **[M]** `python -m pipeline.cli list` warns *"failed to import check module
  'pipeline.checks.check_contract': No module named 'tree_engine'"* — the engine is **not
  installed** in the local venv; `src/` reaches `sys.path` only inside the container
  (`docker/Dockerfile:31,41`: `COPY src/ src/`, then `pip install -e ".[tree-engine]"`).
- **[M]** Live compat matrix (`adapter.compat_matrix`): 67 rows — 50 supported, 4 partial,
  13 not-implemented. Not 70/10 (§8).
- **[M]** `pyproject.toml` `version = "1.0.93"`; `client/ai_editor_client/version.txt` = `1.0.83`.
  Ten versions of drift, nothing pinning them.

## 1. The seam

The boundary falls **between the editor's `EditSession` and the editor's tree machinery** — not
at the MCP command layer and not at the storage layer.

**Editor keeps (unchanged):** the MCP command classes (`ai_editor/commands/universal_file_*`),
CA session/lock handling (`ai_editor/core/upstream/session_guard.py`, `SessionGuard`), the
workspace layout and git-backed draft history (`ai_editor/core/edit_session/edit_session_impl.py`
`EditSession`, `session_repo.py` `SessionRepo`, `session_history.py`, `workspace_layout.py`), the
command facade registry (`ai_editor/commands/universal_file_edit/session.py`
`EditSession`/`get_session`/`create_session`), project scoping, error codes and response shapes.

**Engine takes over:** parse, tree, node identity, addressing, mutation, render. Concretely it
replaces `ai_editor/core/tree_lifecycle/` (`builder.TreeBuilder`, `node_id_map.NodeIdMap`),
`ai_editor/core/json_tree/` (`tree_builder`, `tree_modifier`, `json_saver`),
`ai_editor/core/tree_temp/` parsers/serializers, `ai_editor/tree/handler_registry.HandlerRegistry`
+ `FormatHandler.mark/unmark`, and the address resolvers
`ai_editor/core/edit_session/edit_operations_adapter.resolve_node_ref_to_short_id`,
`ai_editor/commands/universal_file_edit/tree_temp_edit_nodes._resolve_target_node`,
`ai_editor/commands/universal_file_edit/text_node_ref`.

**What crosses the seam.** One new editor-side module — call it
`ai_editor/core/engine_bridge/` — holding exactly: *in*, a source path plus draft bytes, an
integer/string `node_ref` from the frozen API, and an operation dict from `universal_file_edit`;
*out*, a `tree_engine.facade.TreeDocument`, rendered bytes for the draft, and per-node
`(short_id, node_id)` pairs for preview/search responses.

The exact engine entry points, all read and confirmed present in
`src/tree_engine/facade.py`: `loads`, `dumps`, `load`, `save`, `reparse`, `resolve_address`,
`query`, `drill_down`, `insert`, `delete`, `replace`, `move`, `set_attribute`, `set_body`,
`copy_subtree`, `apply_subtree`, `replace_node_id`, `list_formats`. Identity state lives on
`tree_engine.core.live_tree.TreeDocument` (`short_id_map`, `short_id_index`, `nodes_by_id`,
`resolve_short_id`, `reindex`) and `tree_engine.core.short_id.ShortIdMap`.

**A seam that does not exist yet, inside the engine.** `facade.load`/`facade.save` do **not** use
`storage/lifecycle.py`. The docstrings say so verbatim: *"the recoverable open of a source/tree
pair … belongs to `storage/lifecycle.py`, not merged yet; this call routes there once it lands"*
(`facade.py:158-160`, repeated at `:168-169`). Worse, `StorageLifecycle.open/save` operate on the
**immutable** `core.nodes.Document`, while every mutating facade call operates on the **mutable**
`TreeDocument`/`LiveNode`; there is no converter between an `OpenedDocument` and a `TreeDocument`.
The editor needs both halves, so **closing this is engine work and it is Stage 1**.

## 2. Capability gap — what the editor actually needs

**[M]** The real gaps, from `adapter.compat_matrix.gaps()`:

| capability | formats affected | does the editor need it? |
|---|---|---|
| `context_sensitive_role_resolution` | bsl, plain_text, json, toml, yaml | **No** — a `role_for` hook for semantic-role mapping; nothing in `ai_editor/commands/` consumes a semantic role for these formats. Plan no work. |
| `import_export_tree_bridge` | bsl, plain_text, json, toml, yaml | **No** — exposes a raw native parse object; the matrix's own `_LEGACY_REFERENCE` records *"ai_editor never exposed a raw LibCST object across its MCP boundary."* Plan no work. |
| `cst_query_selector` | plain_text/json/toml/yaml **partial**; bsl not-impl. | **Yes** — the `selector` parameter of `universal_file_search`/`universal_file_preview`. Close the four partial rows in `src/tree_engine/query/engine.py` + per-plugin node-kind tables. The bsl row is `ModuleNotFoundError: tree_sitter_bsl`, an environment fact. |
| `format_plugin_module` (python), `registry_extension_conflict_rejected` (`*`) | — | No — probe artifacts, see §8. |

**Two real gaps the matrix does not report, both found by reading and probing:**

1. **`facade.resolve_address` rejects a decimal-string short_id.** `core/address.py:303-326`:
   a `str` is tried as `0x…` hex, then as `document_id:node_id`, then as a bare UUID — a plain
   `"3"` falls through to `UnknownAddressError`. The frozen API's preview hands out
   `node_ref=str(short_id)` (`marked_tree_navigation.py:220,239`), i.e. decimal strings.
   **Engine work:** accept a decimal-digit string as a short_id in `normalize_node_address`,
   before the UUID attempt. Proof: `tests/core/test_address.py` asserting
   `normalize_node_address(doc, "3", …) == normalize_node_address(doc, 3, …)`.
2. **`facade.insert` on `plain_text` produces an unrenderable tree.** **[M]** local probe:
   `insert(doc, "zulu\n", position="before", sibling=<first paragraph>)` splices the fragment's
   `plain_text:root` node in as a sibling, and the next `dumps(doc)` raises
   `UnsupportedTranslation: format 'plain_text' cannot translate node type 'plain_text:root'`.
   Cause: `facade._fragment` (`facade.py:240-253`) inserts whatever `parse_fragment` returns, and
   `plain_text.parse_fragment` returns a root container. **Engine work:** either `parse_fragment`
   returns the paragraph nodes, or `_fragment` unwraps a format-root. Proof: a facade test that
   inserts into a plain-text document and asserts the rendered bytes.

## 3. Staging

Each stage is independently shippable, read paths before mutation paths, and each names the live
check that gates it. Live-check names are **[M]** from `python -m pipeline.cli list` — note the
inconsistent spelling: `live-edit` and `live-write` have no `check-` prefix, the rest do.

### Stage 0 — Make the engine installable and depended-upon (no behaviour change)
Changes: new `src/pyproject.toml` (`name = "ai-editor-tree-engine"`, MIT, `packages.find` over
`src` with `namespaces = true` — load-bearing, `src/tree_engine/` has **no `__init__.py`
anywhere**), root `pyproject.toml` gains the dependency and drops `tree_engine*` from its
`packages.find.include`, `docker/Dockerfile` installs the distribution instead of `COPY src/`.
Engine supplies: nothing new. Proves it: `check-boundary-check`, `check-contract`,
`check-recovery`, `check-roundtrip` pass with `tree_engine` imported **out of tree** (today
`check-contract`/`check-recovery` cannot even import — see §0). Plus a fresh-venv
`pip install ai-editor && python -c "import tree_engine.facade"`.
Blocker to note, not to design around: the PyPI name `ai-editor-tree-engine` is **unverified**;
check it before the first publish. Publishing needs credentials I do not have.

### Stage 1 — Engine: join `StorageLifecycle` to `TreeDocument`
Pure engine work; the editor does not change. Add to `src/tree_engine/storage/lifecycle.py` (or a
sibling) the conversion `OpenedDocument -> TreeDocument` and back, using the existing
`core.live_tree.to_live`/`to_frozen`, and seeding `TreeDocument.short_id_map` from
`OpenedDocument.short_id_map` rather than letting `reindex()` mint a fresh one. Then route
`facade.load`/`facade.save` through it, as their own docstrings promise.
Proves it: `check-recovery`, `check-contract`, and a new engine test — load a file, mutate, save,
reload, assert every surviving node kept its `short_id` **and** its `node_id`.
Without this stage nothing else works: identity that is not persisted is not identity.

### Stage 2 — Engine: close the two real gaps of §2
Decimal-string short_id in `core/address.py`; plain-text fragment insertion in `facade.py` /
`plugins/plain_text.py`. Proves it: unit tests named in §2 plus `check-roundtrip`.

### Stage 3 — Read path, tree-temp formats (json/yaml/toml/ini)
Editor modules changed: `ai_editor/commands/universal_file_preview/marked_tree_navigation.py`,
`tree_temp_preview_focus.py`, `handlers/json_handler.py`, `handlers/yaml_handler.py`,
`handlers/tree_temp_handler.py`; `ai_editor/commands/universal_file_edit/search_command.py`.
Engine supplies: `facade.loads`, `drill_down`, `query`, and per-node
`(short_id, node_id)` via `core/address.build_node_address_view`.
Response shape is unchanged: `node_ref` stays a string, and it stays the **same integer** the
caller sees today, because the engine's short_id is also a 1-based monotonic integer.
Proves it: `check-live-preview`, `check-live-search`, `check-live-node-at-line`.

### Stage 4 — Mutation path, tree-temp
Editor modules changed: `tree_temp_edit_nodes.py`, `tree_temp_edit_batch.py`,
`tree_temp_write_commit.py`, `tree_temp_legacy_apply.py`,
`edit_operations_adapter.resolve_node_ref_to_short_id`. The `_resolve_target_node` rejection
(`tree_temp_edit_nodes.py:366-369`, *"tree-temp operation requires target_stable_id, uuid-like
target_node_id/node_id, or json_pointer"*) disappears because the integer now resolves through the
engine map; `json_pointer` and `target_stable_id` keep working, so the frozen surface loses
nothing. Engine supplies `resolve_address`, `insert`/`delete`/`replace`/`move`/`set_attribute`/
`set_body`, and `dumps` for the draft bytes.
Proves it: `live-edit` (the check carrying the one remaining failure), `live-write`,
`check-live-close`.

### Stage 5 — Text and jsonl
Editor modules changed: `text_node_ref.py`, `text_fallback_tree.py`, `text_op_guards.py`,
`text_draft_apply.py`, `text_move_support.py`, `handlers/text_handler.py`,
`handlers/jsonl_handler.py`. This is the stage that changes what an integer *means* for text:
today `text_handler.py:80` emits `node_ref=str(i)` with `i` a **zero-based line index** and
`text_node_ref._resolve_flat_line_index` reads it back as a position; afterwards it is a short_id
from `plugins/plain_text.py`. **The integers stay integers and stay dense on a freshly opened
file**, so a caller that reads a preview and passes the number back is unaffected; what changes is
that the number survives an insert above it.
Proves it: `live-edit`, `check-live-preview`, `check-live-node-at-line`.

### Stage 6 — Python / sidecar, last
Editor modules changed: `ai_editor/core/tree_lifecycle/builder.py`,
`universal_file_edit/sidecar_cst_apply.py`, `edit_session/edit_operations_adapter.py`,
`edit_session_mutations.py`, `marker_cycle.py`. Python goes last because it is the one group that
already works (§6) and therefore has the most to lose. Engine supplies
`plugins/python/plugin.py` (LibCST).
Proves it: `live-edit`, `check-live-search`, `check-live-open`, `check-live-close`,
`check-roundtrip`.

**Coverage gap to close before Stage 4.** `universal_file_move_nodes`, `universal_file_save`,
`universal_file_replace` and the six `session_git_*`/`session_undo`/`session_redo`/`session_write`
commands have **no live check** — measured against the registered command names in
`ai_editor/commands/`. Under a frozen-API migration, an unchecked command is an unguarded one.
Add named checks to the `pipeline` CLI first.

## 4. The safety net — and what it cannot do today

`adapter/feature_flag.py` is sound and usable as-is: three modes (`legacy`/`adapter`/`comparison`),
`AI_EDITOR_FEATURE_FLAG` inline JSON as the rollback lever, `AI_EDITOR_FEATURE_FLAG_FILE` second,
`DEFAULT_MODE = LEGACY` when neither is set, and `overrides` keyed by bare command name **or**
`"<command>:<format_id>"`. That per-format granularity maps exactly onto the staging above:
Stage 3 flips `universal_file_preview:json`, not `universal_file_preview`.

**`adapter/comparison.py` cannot serve this migration in its current shape, and pretending
otherwise would wreck the plan.** Measured from the source:

- `MCPAdapter` implements **five** commands (`COMMAND_SPECS`): open, preview, search, write,
  capabilities. `universal_file_edit`, `universal_file_close`, `universal_file_node_at_line`,
  `universal_file_move_nodes` are absent.
- Its signatures **drop `project_id`/`session_id` for a `file_path`** (`mcp_adapter.py:17-18`) —
  not a drop-in for the real, session-based commands.
- `_LEGACY_SUFFIXES = (".py", ".pyi", ".pyw")`: the legacy side understands only Python, so
  json/yaml/toml/text comparison is impossible. And `universal_file_preview` is listed in
  `NOT_COMPARABLE_COMMANDS` outright, because legacy preview needs a live session.

**Therefore:** use `comparison` where it is honest (Stage 6, Python, `universal_file_search` and
`universal_file_open`), and for Stages 3–5 make the **live pipeline the comparison instrument**:
run the gating live checks against one deployment with the flag `legacy`, then the same checks
with the flag flipped, and require identical declared responses. That is a real two-engine
comparison over the frozen surface — precisely what the frozen-API ruling makes possible.

**Evidence that justifies flipping one command:** (1) its gating live check green in both flag
positions on the real deployed server; (2) the §6 acceptance invariant green for that format;
(3) `check-roundtrip` green for that format; (4) at least one full working day of `comparison`
traffic with zero `DIVERGENCE` records in `DivergenceLog` **where comparison is possible at all**,
plus an explicit written note where it is not — never a silent pass. Rollback is one environment
variable and a process restart; it never requires a redeploy.

## 5. What will break

**Tree-file format — coexistence, then migration.** The editor's on-disk tree file is a
three-section text file (`node_id_map.py`: `---CHECKSUMS---` / `---MAP---` / `---TREE---`, YAML
bodies, `MapEntry{short_id, uuid, content_fingerprint, kind, attributes}`). The engine's is a
single JSON object (`storage/schema.py`: `TreeFile{envelope, payload, checksums}`,
`schema_version "1.0"`, `payload.short_id_map` = `ShortIdMap.to_dict()`), written beside the
source as `<source>.tree.json` (`lifecycle.DEFAULT_TREE_SUFFIX`). They **coexist**: the engine
writes its own sibling and never reads or writes the editor's, and per stage the old writer is
retired together with its readers, so no migrator is needed. Do not build a converter —
`content_fingerprint` has no counterpart in the engine schema, and inventing one would encode the
very identity model being replaced.

**Existing sessions break across the deploy.** An `EditSession` holds `session_tree_path` pointing
at a `---MAP---` file; after a flip, resolution goes through the engine. Sessions are already
process-local (`_active_sessions`, `_session_bundles` are module dicts) and already do not survive
a restart. Say so in the release note; do not build session migration.

**`node_ref` vocabulary — preserved; this is the constraint that shapes the design.** Accepted
forms today and how each keeps working: `int`/decimal-string short_id
(`edit_operations_adapter.py:217-227`) — resolved through the engine map instead; UUID4 stable-id
(`tree_temp_edit_nodes._extract_stable_target`) — *becomes* the engine's `node_id`; JSON Pointer
(`looks_like_json_pointer_node_ref`) — kept as a *lookup* returning a short_id, exactly as
`resolve_session_pointer_node_ref` already does (`marked_tree_navigation.py:100-125`, it rewrites
`params["node_ref"] = str(short_id)`); markdown slug — kept, markdown is out of scope above. The
engine additionally accepts `0x…` hex and `document_id:node_id`: new capability, not a change.

**Silently changed meaning, and it must be called out in the release note:** for `.txt`/`.rst`
and `.jsonl`, an integer that today *is* a line position stops being one (Stage 5). A caller that
computed `node_ref` arithmetically from a line number — rather than reading it out of a preview
response — will break. That is the intended correction, but it is a behaviour change under a
frozen schema and deserves a named live check asserting the new semantics.

## 6. The acceptance invariant

> Insert a line at the top of a file; the identifier of a node below must NOT change, while its
> line number does.

**[M] The engine already satisfies the identity half.** Probe on the project venv,
`plain_text` document `"alpha\nbravo\ncharlie\n"`:

```
BEFORE: (1,root) (2,'d1df30ab',alpha) (3,'af2f2a9e',bravo) (4,'9c6ab87b',charlie)
AFTER : (1,root) (7,root-frag) (8,'f62724f1',zulu) (2,'d1df30ab',alpha) (3,'af2f2a9e',bravo) (4,'9c6ab87b',charlie)
```

short_ids 2/3/4 kept both their integer **and** their UUID4 across an insert above them; the new
nodes took 7 and 8 from the monotonic allocator. The mechanism is `TreeDocument.reindex()`
(`core/live_tree.py:318-332`): an existing node keeps the short_id the `ShortIdMap` already holds,
only a node without one gets a fresh value. That is the owner's model, working. (The same probe
exposed the plain-text insert defect of §2: identity is right, the fragment shape is not.)

**Where each format stands, and which stage moves it:**

- **Python / sidecar — passes, but not for the reason the brief gives.**
  `NodeIdMap._entry_identity_key` (`node_id_map.py:120-130`) preserves a UUID by
  `internal:{internal_node_id}` when that attribute is present, else by
  `short:{short_id}:fp:{fingerprint}`. **[M]** `internal_node_id` is written only by
  `ai_editor/tree/handlers/python_handler.py`. Python is stable because LibCST supplies a stable
  id; **every other format falls back to the fingerprint+short_id key, which cannot survive a
  shift.** Stage 6.
- **tree-temp (json/yaml/toml/ini) — fails today, fixed by Stages 3–4.** `core/tree_temp/
  tree_node.TreeNode.stable_id` is a UUID4 minted at parse time and never persisted;
  `_regenerate_stable_ids` mints fresh ones outright. `core/json_tree/models.py` derives `node_id`
  as `uuid5(namespace, json_pointer)` — a pointer hash, which changes when the pointer changes.
- **text / jsonl — fails today, fixed by Stage 5.** `text_node_ref._resolve_flat_line_index`
  treats the integer as a position by definition; `_resolve_paragraph_line_block` re-parses the
  source and matches by parse-order short_id, which shifts.

**Make it a live check, not a doc claim.** Add `check-live-node-identity` to the `pipeline` CLI
before Stage 3: open a file, preview it, record `(node_ref, focus stable id)` for the last node,
insert a line at the top via `universal_file_edit`, preview again, assert the identifier is
unchanged and the reported line number increased by one; run it per format. It must be RED for
tree-temp and text the moment it is added — that is the reproduction, per the bug-fix cycle — and
it turns green format-by-format as Stages 3–6 land.

## 7. Version identity across three distributions

**Recommendation: one source of truth plus a runtime declaration — not three declarations and a
test.** A single root `VERSION` file, read by all three `pyproject.toml` files via
`[tool.setuptools.dynamic] version = { file = "VERSION" }` — the mechanism
`client/pyproject.toml` already uses for `ai_editor_client/version.txt`. Three declarations plus a
pinning test protect only the repository; they cannot protect an operator who installs a
mismatched wheel, which is **[M]** exactly the situation on disk today. One file makes drift
unrepresentable at build time; the runtime check below makes it detectable at install time. Keep
a pinning test too — modelled on
`tests/unit/test_config_templates_package.py::test_pyproject_version_matches_template`, which
genuinely fires — so a hand-edit to any `pyproject.toml` goes red immediately.

**Extend the existing declaration mechanism, do not invent one.**
`ai_editor/core/dependency_compat.py` already produces `versions` / `minimum_required` /
`compatibility` from `importlib.metadata.version(...)`, is surfaced by
`ai_editor/commands/health_command.py:101` as `queue_dependencies`, and is enforced at startup by
`assert_queue_dependencies_compatible`, called from `ai_editor/main.py:85`.

1. **Engine.** Add `REQUIRED_TREE_ENGINE_VERSION` (read from the same `VERSION`) to
   `dependency_compat.py`, report `versions.ai_editor_tree_engine` and
   `compatibility.tree_engine_ok`, and make the requirement **equality**, not a minimum, since the
   two are version-locked. Enforcement: **hard refusal at startup**, beside
   `assert_queue_dependencies_compatible`, before `create_app_with_events`. Justification: the
   engine owns node identity and the on-disk tree file; a mismatched engine can write a tree file
   the server cannot read back — on-disk corruption, not a degraded feature. A server that
   corrupts files is worse than one that will not start.
2. **Client.** The check belongs in `client/ai_editor_client/client.py` on
   `CodeAnalysisAsyncClient`, run **once per connection** (first call, cached), not per call:
   call `health`, read `versions.ai_editor_server`, compare against `__version__`
   (`client/ai_editor_client/__init__.py:180`). On mismatch raise a new typed
   `ServerVersionMismatch(ClientValidationError)` in `client/ai_editor_client/exceptions.py`
   naming **both** numbers and the fix. **Fail the connection, not the call** — a session
   half-created against an incompatible server is worse than one never started.
3. **Diagnosability, which the strictness makes mandatory.** `health` and `info` must stay
   reachable across a mismatch — they are how the operator sees the two numbers — so the client's
   gate must **exempt** them and refuse only the rest; otherwise the check hides its own evidence.
   The error must name the installed client version, the reported server version, and the single
   remedy (`pip install ai-editor-client==<server>`). Upgrade order becomes load-bearing; that is
   intended, and is a release-note item.

**Plan step:** bring `client/ai_editor_client/version.txt` from 1.0.83 to the current server
version in the same commit that introduces the single `VERSION` file, so the rule is established
by a state that already satisfies it.

**Packaging scope, per the owner:** the engine is internal interface, not a product — correct
metadata, the four existing extras (`tree-engine-python`, `tree-engine-bsl`, `tree-engine-query`,
aggregate `tree-engine`) carried over verbatim, a working out-of-tree import, and the version
discipline. No README polish, no docs site.

## 8. Where the brief's description of the current state is wrong

1. **"70 SUPPORTED and 10 NOT_IMPLEMENTED".** **[M]** 67 rows: 50 supported, **4 partial**, 13
   not-implemented. The partial rows (`cst_query_selector` for plain_text/json/toml/yaml) are the
   ones that matter to the editor, and are invisible in a supported/not-implemented framing.
2. **The gaps are not only those two capabilities.** Three further not-implemented rows:
   `python | format_plugin_module` (probe artifact — the plugin itself loads fine),
   `bsl | cst_query_selector` (`ModuleNotFoundError: tree_sitter_bsl`, an environment fact), and
   `* | registry_extension_conflict_rejected` (registry behaviour, not a format).
3. **"sidecar (.py) — correct".** Correct in effect, wrong in mechanism, and the difference
   matters: the UUID survives via `internal_node_id` **only when the handler supplies one**, and
   **[M]** only `python_handler.py` ever does (lines 1028, 1067, 1124). The generic path is
   `short:{short_id}:fp:{fingerprint}` — position-plus-content. `NodeIdMap` is therefore not a
   general-purpose stable-identity map; a plan assuming it is would be building on sand.
4. **"tree-temp — no map at all".** No short_id↔UUID map, agreed. But there *is* a per-node UUID4
   `stable_id` on `core/tree_temp/tree_node.TreeNode`, handed out as `node_ref` by
   `tree_temp_handler.py:98` and `tree_temp_preview_focus.py:260`. A UUID-shaped `node_ref` is
   already part of the frozen tree-temp surface and must keep resolving.
5. **"Preview … hands out `node_ref=str(short_id)` and edit refuses it".** True on one of *two*
   paths. `navigation.py:111-117` routes to the tree-temp path (UUID `node_ref`) when
   `params["tree_temp_roots"] is not None`, and to marked-tree navigation (integer `node_ref`)
   otherwise. The failure is real but path-dependent; a fix must cover both routes.
6. **"`plugins/plain_text.py` builds a paragraph/line tree".** **[M]** It builds `plain_text:root`
   + one `plain_text:paragraph` per **line** (`_split_paragraphs` uses `splitlines(keepends=True)`).
   There is no two-level structure. If the editor's Paragraph+Line model
   (`text_node_ref.text_uses_paragraph_line_tree`) must survive on the frozen surface, that is
   **engine work** in `plugins/plain_text.py` — see §9, I could not settle whether it must.
7. **"packaged and physically present inside the deployed image".** Present, yes
   (`docker/Dockerfile:31,41`). *Packaged* only as an entry in the root `pyproject.toml`'s
   `packages.find`; it is not a distribution, and **[M]** not importable in the local checkout.
8. **`facade.load`/`save` bypass `storage/lifecycle.py` entirely** (§1). The storage layer is
   complete as modules but **not wired to the mutation layer**. "Complete" overstates it.

## 9. What I could not establish

- **Whether the frozen response shape requires the two-level Paragraph+Line text tree.** The
  editor holds two different text models: `str(i)` zero-based line index in
  `handlers/text_handler.py:80`, and a parse-order short_id over a Paragraph+Line tree in
  `text_node_ref._resolve_paragraph_line_block`. Which one a caller sees depends on the dispatch
  path, and I could not settle it from source. **Resolve before Stage 5** by running
  `check-live-preview` against a real `.txt` file and reading the payload.
- **Whether `tests/` contains a pin between client and server versions.** My grep for
  `1.0.83`/`version.txt` under `tests/` returned nothing — evidence of absence, not proof; a
  differently-worded assertion could exist.
- **Whether `content_fingerprint` is load-bearing beyond UUID preservation.** I traced its
  producers and its use in `_entry_identity_key`, but not every consumer.
- **Live behaviour of anything.** Every claim here is source reading plus two local probes.
  Nothing has been checked against the deployed 1.0.93 server — which is why the staging above
  puts the live checks first.
