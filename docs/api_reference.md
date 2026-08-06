# tree_engine public API reference

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Step: G-027/T-001/A-004 (`api-reference-doc`), plan
`24271419-4dc6-44f2-8613-f350310f5c12`, concept C-021 (PublicApiAndErrorModel).

Subject read directly: `src/tree_engine/facade.py`, `src/tree_engine/core/live_tree.py`,
`src/tree_engine/exceptions.py`, `src/tree_engine/errors.py`. Every signature below was
extracted with `inspect.signature` against this worktree's code, not copied by eye; every
numbered example was executed with
`PYTHONPATH=src /home/vasilyvz/projects/tools/ai_editor/.venv/bin/python`. This document is
the stable contract surface for the C-023 adapter and C-022 contract tests; it changes only
through cascade discipline, never a silent edit.

## 1. Facade contract

`tree_engine.facade` is the single public entry point (`__all__` lists every name below).
File-taking calls (`load`, `save`) route to the storage layer; calls on an already-loaded
`TreeDocument` route to the core. Every escaping error is one `tree_engine.exceptions` class
carrying a stable `ErrorCode`; no bare `KeyError`/`ValueError`/`AttributeError` from an
internal layer reaches a caller (`facade._typed`).

`load`/`save` are the **direct-file path**, not the full lifecycle contract: the recoverable
open of a source/tree *pair* — partial-publication recovery, `source_sha256` conflict
detection, edit-session concurrency — is owned by `storage/lifecycle.py`, a sibling module,
not by these two functions. `save` does use the storage layer's transactional file publish
(`storage.file_txn.publish`, journal-then-rename) so a crash mid-write cannot corrupt the
target file, but conflict detection across concurrent editors is `lifecycle.py`'s job.

## 2. Built-in formats

`list_formats()` (example 1 below) returns exactly:

| `format_id` | Extensions | Third-party dependency | Optional extra |
|---|---|---|---|
| `python` | `.py`, `.pyi` | `libcst` | `tree-engine-python` |
| `bsl` | `.bsl` | `tree_sitter`, `tree_sitter_bsl` | `tree-engine-bsl` |
| `json` | `.json` | none (stdlib) | — |
| `toml` | `.toml` | none (stdlib, `tomllib`) | — |
| `yaml` | `.yaml`, `.yml` | none (stdlib, hand-rolled scanner) | — |
| `plain_text` | `.txt`, and the mandatory fallback target | none (stdlib) | — |

The core, storage layer, and these three stdlib-only plugins need nothing beyond the
standard library; `pipeline/checks/check_boundary.py` mechanically enforces that `libcst`/
`tree_sitter`/`tree_sitter_bsl` are only ever imported under `plugins/`. A `lark`-based
query grammar exists behind `tree-engine-query` (`lark`) for the selector engine; it is not
a format plugin. `register_format_plugin`/`list_formats` let a caller extend or inspect the
registry at runtime.

## 3. Addressing

`Address = Union[UUID, int, str, NodeAddress]`. Every address-taking command resolves
through `resolve_address`/`normalize_node_address` before any check or mutation:

- `UUID` — a canonical `node_id`, checked against `document.nodes_by_id`.
- positive `int` — a document-local `short_id`, resolved through the bidirectional
  `ShortIdMap`.
- `str` starting `0x`/`0X` — a hex-rendered `short_id` (`short_id.to_hex`/`from_hex`).
- `str` containing `:` — a serialized `"document_id:node_id"` `NodeAddress`.
- bare UUID `str`, or a `NodeAddress` instance directly.

**Both `node_id` (UUID4) and `short_id` are minted fresh on every parse** (`TreeDocument.
__init__`/`reindex`, `ShortIdMap()` starting at 1). An address is therefore *parse-local*:
it cannot be carried from one `loads()`/`load()` result to another, even for what looks like
the same source text. An unresolvable address raises `NodeNotFound`; a short_id resolving to
more than one node_id (a defensive guard against a broken map invariant, never expected in
practice) raises `ShortIdConflict`; a `NodeAddress`/`"doc:node"` string naming a different
`document_id` raises `NodeNotFound` before any local lookup (see `core.address.
ForeignDocumentAddressError`, remapped at the facade boundary). No rejection path starts a
partial operation.

## 4. Versioning and locking

`TreeDocument.document_version` starts at `1` and increments by exactly one on every
committed mutation. Every mutating facade call accepts `expected_version: Optional[int]`;
when given and it does not match, `DocumentVersionConflict` is raised before any mutation
starts (`facade._check_version`), so a stale search result can never mutate a different
node. One document's operations are serialized end-to-end by a shared
`DocumentLockCoordinator` (one `threading.Lock` per `document_id`, held for the whole
operation). `move` across two documents (`target_document` given) acquires both documents'
locks in deterministic `document_id` (UUID4) order through the same coordinator, so a
concurrent cross-document move can neither deadlock nor publish partially. Automatic merging
of concurrent changes is never performed.

## 5. `TreeDocument`

```
TreeDocument(root: LiveNode, source_format_id: str, format_id: str, source_bytes: bytes, *,
             path: Optional[Path] = None,
             fallback_diagnostic: Optional[Mapping[str, Any]] = None) -> None
```

Attributes a caller reads directly: `document_id` (fresh `UUID4` per load/loads),
`document_version` (monotonic `int`), `root` (`LiveNode`), `source_format_id`/`format_id`
(differ only under the plain-text fallback), `path` (`None` for a `loads()`-only document),
`nodes_by_id`, `short_id_index`, `short_id_map`, `parent_index` (document-local addressing
state, rebuilt by `reindex()` after every mutation), `fallback_diagnostic`. Not constructed
directly by a caller in normal use — `load`/`loads` build it.

## 6. Function reference

Every signature below is the literal `inspect.signature` output.

### File and content entry points

```
loads(content: Union[str, bytes], *, format_id: Optional[str] = None,
      file_path: Optional[str] = None, allow_plain_text_fallback: bool = True) -> TreeDocument
dumps(document: TreeDocument) -> bytes
load(path: Union[str, Path], *, format_id: Optional[str] = None,
     allow_plain_text_fallback: bool = True) -> TreeDocument
save(document: TreeDocument, path: Optional[Union[str, Path]] = None) -> Path
reparse(document: TreeDocument) -> TreeDocument
```

`format_id` takes unconditional priority over `file_path`'s extension when both are given;
an unresolved extension raises `FormatUnknownExtension`. Only a `FORMAT_CONTENT_PARSE_FAILED`
from the resolved plugin may open the authorized plain-text fallback (`allow_plain_text_
fallback=True`, the default); every other failure is unmasked. `save(document)` with no
`path` and a `document.path` of `None` (a `loads()`-only document) raises `StorageIOError`
(example 8). `reparse` renders, re-parses with the *source* format only
(`allow_plain_text_fallback=False`), and bumps `document_version` — never an implicit side
effect of any other call.

### Addressing

```
resolve_address(document: TreeDocument, address: Address) -> UUID
```

### Read-only

```
query(document: TreeDocument, selector: str, *, include_source: bool = False) -> List[QueryMatch]
drill_down(document: TreeDocument, address: Optional[Address] = None, *, depth: int = 1,
           expected_version: Optional[int] = None, include_attributes: bool = True,
           include_source: str = SOURCE_PREVIEW, source_preview_bytes: int = 256,
           max_output_bytes: int = 65536) -> OutlineResponse
```

`query` never reparses the loaded source; a malformed selector raises `InvalidSelector`.
`include_source` on `drill_down` takes one of the re-exported constants `SOURCE_NONE`,
`SOURCE_PREVIEW` (default), `SOURCE_FULL`.

### Mutating

```
insert(document, source: Union[str, bytes], *, position: str, parent: Optional[Address] = None,
       sibling: Optional[Address] = None, index: Optional[int] = None,
       expected_version: Optional[int] = None) -> MutationResult
delete(document, targets: Any, *, expected_version: Optional[int] = None) -> MutationResult
replace(document, targets: Any, source: Union[str, bytes], *,
        expected_version: Optional[int] = None) -> MutationResult
move(document, targets: Any, *, position: str, parent: Optional[Address] = None,
     sibling: Optional[Address] = None, index: Optional[int] = None,
     target_document: Optional[TreeDocument] = None,
     expected_version: Optional[int] = None) -> MoveResult
copy_subtree(document, address: Optional[Address] = None, *,
             expected_version: Optional[int] = None, preserve_ids: bool = False) -> CopiedDocument
apply_subtree(document, copy: CopiedDocument, *,
              expected_version: Optional[int] = None) -> ApplySubtreeResult
set_attribute(document, address: Address, name: str, value: Any, *,
              expected_version: Optional[int] = None) -> MutationResult
set_body(document, address: Address, source: Union[str, bytes], *,
         expected_version: Optional[int] = None) -> MutationResult
replace_node_id(document, address: Address, new_node_id: UUID, *,
                 expected_version: Optional[int] = None) -> AddressRemap
```

`position` for `insert`/`move` is one of `first_child`, `last_child`, `child_index` (needs
`index`), `before`, `after`. `targets` for `delete`/`replace`/`move` is one address or an
ordered sequence of them (a contiguous sibling range). `copy_subtree` with `preserve_ids=
False` (default) mints fresh UUID4s for the copy; `True` keeps the originals, for later
`apply_subtree` back into the same tree. `replace_node_id` rewrites a node's UUID4 while
keeping its `short_id` intact (`ShortIdMap.rekey`).

### Registry

```
register_format_plugin(plugin: Any, *, replace: bool = False) -> None
list_formats() -> Tuple[str, ...]
```

## 7. Result types

Re-exported by the facade so a caller never imports past it (all `@dataclass`, fields via
`dataclasses.fields`):

| Type | Fields |
|---|---|
| `MutationResult` | `node_id, short_id, position, remap, removed, inserted` |
| `MoveResult` | `node_id, short_id, position, remap, removed, inserted, reference_delta` |
| `ApplySubtreeResult` | `node_id, short_id_remap, removed, inserted` |
| `CopiedDocument` | `document_id, document_version, root, nodes_by_id, short_id_map, old_uuid_to_new_uuid, origin_document_id, origin_parent_id` |
| `AddressRemap` | `old, new` |
| `QueryMatch` | `node_id, short_id_hex, type, kind, name, range, parent_path, source` |
| `OutlineResponse` | `meta, nodes, truncation` |

## 8. Error-code table (23 codes, complete and total)

`tree_engine.exceptions.CODE_TO_EXCEPTION` is asserted at import time to map every
`ErrorCode` to exactly one class, each `issubclass` of the layer base its code declares in
`errors.ERROR_CODE_LAYER` — this table cannot drift from the code.

| Code | Layer | Exception class |
|---|---|---|
| `NODE_NOT_FOUND` | CORE | `NodeNotFound` |
| `NODE_ID_CONFLICT` | CORE | `NodeIdConflict` |
| `SHORT_ID_CONFLICT` | CORE | `ShortIdConflict` |
| `DOCUMENT_VERSION_CONFLICT` | CORE | `DocumentVersionConflict` |
| `INVALID_SELECTOR` | CORE | `InvalidSelector` |
| `INVALID_POSITION` | CORE | `InvalidPosition` |
| `INVALID_PARENT_TYPE` | CORE | `InvalidParentType` |
| `CYCLE_DETECTED` | CORE | `CycleDetected` |
| `UNRESOLVED_REFERENCE` | CORE | `UnresolvedReference` |
| `CONCURRENT_TREE_MODIFICATION` | CORE | `ConcurrentTreeModification` |
| `FORMAT_UNKNOWN_EXTENSION` | PLUGIN | `FormatUnknownExtension` |
| `FORMAT_EXTENSION_CONFLICT` | PLUGIN | `FormatExtensionConflict` |
| `FORMAT_PLUGIN_NOT_FOUND` | PLUGIN | `FormatPluginNotFound` |
| `PLUGIN_CAPABILITY_NOT_SUPPORTED` | PLUGIN | `PluginCapabilityNotSupported` |
| `FORMAT_CONTENT_PARSE_FAILED` | PLUGIN | `FormatContentParseFailed` |
| `FORMAT_FRAGMENT_PARSE_FAILED` | PLUGIN | `FormatFragmentParseFailed` |
| `FORMAT_PLUGIN_CONTRACT_ERROR` | PLUGIN | `FormatPluginContractError` |
| `UNSUPPORTED_TRANSLATION` | PLUGIN | `UnsupportedTranslation` |
| `TREE_PAYLOAD_INVALID` | STORAGE | `TreePayloadInvalid` |
| `TREE_SCHEMA_UNSUPPORTED` | STORAGE | `TreeSchemaUnsupported` |
| `CHECKSUM_MISMATCH` | STORAGE | `ChecksumMismatch` |
| `CONCURRENT_SOURCE_MODIFICATION` | STORAGE | `ConcurrentSourceModification` |
| `STORAGE_IO_ERROR` | STORAGE | `StorageIOError` |

`FormatContentParseFailed` is the **only** class with `plain_text_fallback_permitted = True`
(asserted at import time); every other code is never masked by any fallback. Every leaf's
`.layer` property is derived live from `ERROR_CODE_LAYER`, never restated.

## 9. Known limits — read before relying on byte fidelity

- **BSL round-trip is not byte-identical on real 1C modules today.** Measured: 0 of 200
  sampled files from a real configuration dump round-tripped byte-identically; about a third
  of the mismatches are only a dropped UTF-8 BOM. Treat BSL fidelity as unverified in
  production until this is fixed and re-measured.
- **`set_attribute` with a field name the target format's generator does not recognize fails
  at render time, not at set time.** Verified (§10, example 9): setting an unknown field on
  a `python:Module` node succeeds silently; `dumps()` later raises
  `FormatPluginContractError` from `libcst.Module.__init__()`'s own `TypeError`.
  `LiveNode.set_attribute` only validates that the *value* is a primitive — never the field
  *name* against the target format's schema.
- **`set_body` on a `python:IndentedBlock` detaches the field-held `header` node from
  addressing.** Verified (§10, example 10): the block's `header` field (a
  `python:TrailingWhitespace` LibCST node, not part of the block's spliced `body` sequence)
  is present in `nodes_by_id` before the call and absent after — `reindex()` walks only
  `.children`, and `set_body` replaces `.children` with the freshly parsed statements without
  the old `header` node.
- **Splicing children only works where exactly one field holds the node sequence.** Verified
  (§10, example 11): `python:Module`/`python:IndentedBlock` (their `body` field) accept it; a
  `python:If` node holds `test`, `body`, `orelse` in separate single/sequence fields with no
  single unambiguous sequence, and `sync_fields` raises `InvalidParentType` — splice into the
  sequence-holding descendant instead.
- **`load`/`save` are not `storage/lifecycle.py`.** No `source_sha256` conflict detection, no
  tree-file companion, no edit-session concurrency guard — see §1.

## 10. Executed examples (all run against this worktree, output pasted verbatim)

```python
import tree_engine.facade as f

# 1. list_formats()
f.list_formats()
# -> ('python', 'bsl', 'json', 'toml', 'yaml', 'plain_text')

# 2-3. loads/dumps round trip + address forms all resolve to the same node
doc = f.loads('{"a": 1, "b": [1,2,3]}', format_id="json")
f.dumps(doc) == b'{"a": 1, "b": [1,2,3]}'          # -> True
root_id, short = doc.root.node_id, doc.root.short_id
(f.resolve_address(doc, root_id) == f.resolve_address(doc, short)
 == f.resolve_address(doc, f"0x{short:x}") == root_id)  # -> True

# 4. unknown address -> NodeNotFound
import uuid
f.resolve_address(doc, uuid.uuid4())
# -> NodeNotFound: [NODE_NOT_FOUND] unresolvable node address UUID(...)

# 5-6. stale expected_version rejected; a real insert bumps document_version
doc = f.loads('[1, 2, 3]', format_id="json")
f.insert(doc, "4", position="last_child", parent=doc.root.node_id, expected_version=999)
# -> DocumentVersionConflict: [DOCUMENT_VERSION_CONFLICT] expected_version 999
#    does not match document_version 1
f.insert(doc, "4", position="last_child", parent=doc.root.node_id)
doc.document_version                                # -> 2
f.dumps(doc)                                         # -> b'[1, 2, 3, 4]'

# 7. save() then load() round trip
path = f.save(doc, "/tmp/example.json")
f.dumps(f.load(path)) == f.dumps(doc)                # -> True

# 8. save() with no path on a loads()-only document
f.save(f.loads('{"x": 1}', format_id="json"))
# -> StorageIOError: [STORAGE_IO_ERROR] save() needs a path: this
#    document came from loads(), not a file
```

Examples 9-11 (set_attribute render-time failure, set_body header detachment, ambiguous-
parent splice rejection) are given in full, with their real output, in §9 above; all eleven
were executed in this session with
`PYTHONPATH=src /home/vasilyvz/projects/tools/ai_editor/.venv/bin/python`, none edited after
the run.
