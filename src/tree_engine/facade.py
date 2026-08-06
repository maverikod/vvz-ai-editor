"""The single public entry point of the tree engine (concept C-021).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Everything a caller needs is here -- :class:`TreeDocument`, the file/content entry points, the read and
mutating operations, and their result types ({p037}) -- so nothing needs an import from
``tree_engine.core.*``/``tree_engine.plugins.*``, and every error raised is a ``tree_engine.exceptions``
class carrying an ``ErrorCode`` of ``tree_engine.errors``. File calls route to the storage layer, format
selection/parsing/rendering to the plugin layer (including the authorized plain-text fallback after
``FORMAT_CONTENT_PARSE_FAILED`` and nothing else) and document operations to the core ({p025}); every
address-taking command resolves through ``normalize_node_address`` first ({j9rh}) and every mutating one
checks ``expected_version`` against the monotonic ``document_version`` ({p024}) under the shared lock
coordinator ({p035}). ``core.nodes.Node`` being immutable, :class:`_LiveNode` mirrors its schema mutably
for the core's splices, converted back for every render.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union
from uuid import UUID, uuid4
from tree_engine.core import move as _move_mod, operations as _ops, subtree_apply as _apply_mod
from tree_engine.core import subtree_copy as _copy_mod, updates as _updates
from tree_engine.core.address import NodeAddressError, normalize_node_address
from tree_engine.core.identity import AddressRemap, NodeAddress, generate_node_id
from tree_engine.core.locking import DocumentLockCoordinator
from tree_engine.core.nodes import Document, Node, NodeKind, NodeSchemaError
from tree_engine.core.short_id import ShortIdMap
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (DocumentVersionConflict, FormatFragmentParseFailed, InvalidParentType,
    NodeNotFound, ShortIdConflict, StorageIOError, TreeEngineException, exception_for_code)
from tree_engine.plugins.bsl.plugin import BSL_FORMAT_PLUGIN
from tree_engine.plugins.fallback import PLAIN_TEXT_FORMAT_ID, build_fallback_tree
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.plugins.selection import build_extension_table, resolve_format_plugin
from tree_engine.plugins.toml_format import TOML_FORMAT_PLUGIN
from tree_engine.query.engine import query as _query
from tree_engine.query.inspection import SOURCE_FULL, SOURCE_NONE, SOURCE_PREVIEW, drill_down as _drill_down
from tree_engine.query.outline import OutlineResponse
from tree_engine.query.results import QueryMatch
from tree_engine.storage.file_txn import FileWrite, publish

__all__ = ["TreeDocument", "Address", "load", "save", "reparse", "loads", "dumps", "query", "drill_down",
    "insert", "delete", "replace", "move", "copy_subtree", "apply_subtree", "set_attribute", "set_body",
    "replace_node_id", "resolve_address", "SOURCE_NONE", "SOURCE_PREVIEW", "SOURCE_FULL",
    "PLAIN_TEXT_FORMAT_ID", "AddressRemap", "ApplySubtreeResult", "CopiedDocument", "MoveResult",
    "MutationResult", "NodeAddress", "OutlineResponse", "QueryMatch"]

Address = Union[UUID, int, str, NodeAddress]
_CACHED_SOURCE = ("raw", "content")  # plugin-cached source slices, stale on every ancestor of an edit
_BUILTINS = (PYTHON_FORMAT_PLUGIN, BSL_FORMAT_PLUGIN, JSON_FORMAT_PLUGIN, TOML_FORMAT_PLUGIN, PLAIN_TEXT_FORMAT_PLUGIN)
_REGISTRY = FormatPluginRegistry()
for _builtin in _BUILTINS:
    _REGISTRY.register_format_plugin(_builtin, replace=True)
_EXTENSIONS: Dict[str, str] = dict(build_extension_table(_BUILTINS))
_LOCKS, MoveResult, MutationResult = DocumentLockCoordinator(), _move_mod.MoveResult, _ops.MutationResult
ApplySubtreeResult, CopiedDocument = _apply_mod.ApplySubtreeResult, _copy_mod.CopiedDocument

# -- typed-error boundary ---------------------------------------------------
def _code_of(exc: BaseException) -> Optional[ErrorCode]:
    """``.code``, then the older ``.error_code`` the plugin errors carry, then ``.errors[0].code``."""
    for name in ("code", "error_code"):
        if isinstance(getattr(exc, name, None), ErrorCode):
            return getattr(exc, name)
    for entry in getattr(exc, "errors", None) or ():
        if isinstance(getattr(entry, "code", None), ErrorCode): return entry.code
    return None
@contextmanager
def _typed(default: ErrorCode) -> Iterator[None]:
    """Type every escaping error: one already in the hierarchy passes through, any other is re-raised
    (chained) as the class owning its ``ErrorCode``, else ``default``."""
    try:
        yield
    except TreeEngineException: raise
    except Exception as exc:
        code = _code_of(exc) or (ErrorCode.STORAGE_IO_ERROR if isinstance(exc, OSError) else default)
        raise exception_for_code(code)(str(exc) or type(exc).__name__) from exc

@dataclass(eq=False)
class _LiveNode:
    """Mutable mirror of ``core.nodes.Node``: same schema, plus the settable ``parent``/list ``children``
    the core's mutating operations need. Never leaves this module."""
    kind: str
    fields: Dict[str, Any]
    children: List["_LiveNode"]
    node_id: UUID
    short_id: Optional[int] = None
    extended_type: Optional[str] = None
    buffer_range: Optional[Tuple[int, int]] = None
    references: Tuple[Any, ...] = ()
    parent: Optional["_LiveNode"] = field(default=None, repr=False)

    def get_attribute(self, name: str, default: Any = None) -> Any:
        return self.fields.get(name, default)

    def set_attribute(self, name: str, value: Any) -> None:
        """Set field ``name``; a non-primitive raises the ``NodeSchemaError`` ``core.updates`` types."""
        if not (value is None or isinstance(value, (str, int, float, bool, bytes))):
            raise NodeSchemaError(ErrorCode.INVALID_PARENT_TYPE,
                                  f"attribute {name!r} must be primitive, got {type(value).__name__}")
        self.fields = {**self.fields, name: value}
def _remap(fields: Mapping[str, Any], old: Sequence[Any], new: Sequence[Any]) -> Dict[str, Any]:
    """``fields`` with each node value swapped for its counterpart by object identity; a live node no
    longer among ``old`` -- a field-held child some splice detached -- is frozen on the spot instead."""
    swap = {id(o): n for o, n in zip(old, new)}
    def one(value: Any) -> Any:
        if isinstance(value, tuple):
            return tuple(one(item) for item in value)
        return swap.get(id(value)) or (_to_frozen(value) if isinstance(value, _LiveNode) else value)
    return {key: one(value) for key, value in fields.items()}
def _to_live(node: Node, parent: Optional[_LiveNode] = None) -> _LiveNode:
    live = _LiveNode(kind=str(node.kind), fields=dict(node.fields), children=[], parent=parent,
                     node_id=node.node_id if node.node_id is not None else generate_node_id(),
                     short_id=node.short_id, extended_type=node.extended_type,
                     buffer_range=node.buffer_range, references=tuple(node.references or ()))
    live.children = [_to_live(child, live) for child in node.children]
    live.fields = _remap(node.fields, node.children, live.children)
    return live
def _to_frozen(live: _LiveNode) -> Node:
    children = [_to_frozen(child) for child in live.children]
    return Node(kind=NodeKind(live.kind), fields=_remap(live.fields, live.children, children),
                children=tuple(children), node_id=live.node_id, short_id=live.short_id,
                extended_type=live.extended_type, buffer_range=live.buffer_range, references=live.references)
def _walk(node: _LiveNode) -> Iterator[_LiveNode]:
    yield node
    for child in node.children: yield from _walk(child)
def _relink(node: _LiveNode, parent: Optional[_LiveNode]) -> None:
    node.parent = parent
    for child in node.children: _relink(child, node)
def _sync_fields(parent: Optional[_LiveNode]) -> None:
    """Mirror ``parent.children`` into the node-holding ``fields`` Python and BSL render from (JSON/TOML
    render from ``children`` and hold none). One node-sequence field is unambiguous and is rewritten;
    several, or only single-valued ones, cannot express a sequence edit and are refused, not ignored."""
    if parent is None:
        return
    sequences = [name for name, value in parent.fields.items()
                 if isinstance(value, tuple) and value and all(isinstance(v, _LiveNode) for v in value)]
    if len(sequences) == 1:
        parent.fields = {**parent.fields, sequences[0]: tuple(parent.children)}
    elif sequences or any(isinstance(value, _LiveNode) for value in parent.fields.values()):
        raise InvalidParentType(f"node kind {parent.kind!r} does not hold its children in one sequence "
                                "field; splice into the sequence-holding descendant instead")

class TreeDocument:
    """One loaded document. ``document_version`` is the monotonic counter every mutating command checks and
    bumps ({p024}); ``source_format_id`` and ``format_id`` differ only under the authorized plain-text
    fallback, which also fills ``fallback_diagnostic`` ({p050}, {7a9b}); ``nodes_by_id``, ``short_id_index``,
    ``short_id_map`` and ``parent_index`` are the document-local addressing state ({p097})."""

    def __init__(self, root: _LiveNode, source_format_id: str, format_id: str, source_bytes: bytes, *,
                 path: Optional[Path] = None, fallback_diagnostic: Optional[Mapping[str, Any]] = None) -> None:
        self.document_id, self.document_version = uuid4(), 1
        self.root, self.source_bytes, self.path = root, source_bytes, path
        self.source_format_id, self.format_id = source_format_id, format_id
        self.fallback_diagnostic = dict(fallback_diagnostic) if fallback_diagnostic else None
        self.short_id_map, self.nodes_by_id, self.short_id_index = ShortIdMap(), {}, {}
        self.reindex()

    def reindex(self) -> None:
        """Rebuild the node, short_id and parent indexes: a node keeps its short_id, one without gets the
        next monotonic value, a gone node's is released and never reused ({p097})."""
        live: Dict[UUID, _LiveNode] = {node.node_id: node for node in _walk(self.root)}
        for node_id in self.short_id_index.values():
            if node_id not in live:
                self.short_id_map.release(node_id)
        self.nodes_by_id, self.short_id_index = live, {}
        self.parent_index = {i: (n.parent.node_id if n.parent is not None else None) for i, n in live.items()}
        for node_id, node in live.items():
            existing = self.short_id_map.get_short_id(node_id)
            node.short_id = existing if existing is not None else self.short_id_map.allocate(node_id)
            self.short_id_index[node.short_id] = node_id

    def resolve_short_id(self, short_id: int) -> Sequence[UUID]:
        """The ``normalize_node_address`` accessor: short_id -> node_id."""
        node_id = self.short_id_map.get_node_id(short_id)
        return () if node_id is None else (node_id,)

    def source_for(self, node: _LiveNode) -> Optional[str]:
        """The node's own text from the loaded source, for ``drill_down`` previews."""
        span = node.buffer_range
        return None if span is None else self.source_bytes[span[0]:span[1]].decode("utf-8", "replace")

# -- plugin resolution, content and file entry points ({p037}) --------------
def _plugin(format_id: Optional[str] = None, file_path: Optional[str] = None) -> Any:
    return resolve_format_plugin(format_id=format_id, file_path=file_path, registry=_REGISTRY,
                                 extension_table=_EXTENSIONS)
def loads(content: Union[str, bytes], *, format_id: Optional[str] = None, file_path: Optional[str] = None,
          allow_plain_text_fallback: bool = True) -> TreeDocument:
    """Parse content ({p037}): the format is ``format_id``, else ``file_path``'s extension, and neither
    resolving raises ``FormatUnknownExtension``; only ``FORMAT_CONTENT_PARSE_FAILED`` opens the fallback."""
    with _typed(ErrorCode.FORMAT_CONTENT_PARSE_FAILED):
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        plugin = _plugin(format_id, file_path)
        source_id, path = plugin.metadata.format_id, Path(file_path) if file_path else None
        try:
            parsed = plugin.parse_document(text)
        except Exception as exc:
            if not (allow_plain_text_fallback and _code_of(exc) is ErrorCode.FORMAT_CONTENT_PARSE_FAILED):
                raise
            back = build_fallback_tree(text, exc, source_format_id=source_id)
            return TreeDocument(_to_live(back.document.root), source_id, PLAIN_TEXT_FORMAT_ID,
                                text.encode("utf-8"), path=path, fallback_diagnostic=back.metadata.diagnostic)
        return TreeDocument(_to_live(parsed.root), source_id, parsed.representation_format_id,
                            text.encode("utf-8"), path=path)
def dumps(document: TreeDocument) -> bytes:
    """Render ``document`` back to source bytes through its format plugin."""
    with _typed(ErrorCode.UNSUPPORTED_TRANSLATION):
        common = Document(root=_to_frozen(document.root), source_format_id=document.source_format_id,
                          representation_format_id=document.format_id)
        output = _plugin(document.format_id).generate_output(common, {})
        return output if isinstance(output, bytes) else str(output).encode("utf-8")
def load(path: Union[str, Path], *, format_id: Optional[str] = None,
         allow_plain_text_fallback: bool = True) -> TreeDocument:
    """Read ``path`` and parse it -- the direct-file path over the merged storage siblings. The recoverable
    open of a source/tree *pair* (partial-publication recovery, source_sha256 conflict detection,
    edit-session concurrency) belongs to ``storage/lifecycle.py``, not merged yet."""
    with _typed(ErrorCode.STORAGE_IO_ERROR):
        content = Path(path).read_bytes()
    return loads(content, format_id=format_id, file_path=str(path),
                 allow_plain_text_fallback=allow_plain_text_fallback)
def save(document: TreeDocument, path: Optional[Union[str, Path]] = None) -> Path:
    """Publish the rendered ``document`` as one recoverable file transaction ({p090}); the tree-file
    companion, checksums, and conflict policy wait on the lifecycle module."""
    content = dumps(document)
    with _typed(ErrorCode.STORAGE_IO_ERROR):
        target = Path(path) if path is not None else document.path
        if target is None:
            raise StorageIOError("save() needs a path: this document came from loads(), not a file")
        publish([FileWrite(target_path=target, content=content)], target.with_suffix(target.suffix + ".journal"))
        document.path, document.source_bytes = target, content
        return target
def reparse(document: TreeDocument) -> TreeDocument:
    """Rebuild ``document`` from its own rendered source, in place ({p037}); never implicit."""
    content = dumps(document)
    rebuilt = loads(content, format_id=document.source_format_id, allow_plain_text_fallback=False)
    with _operation(document, None):
        document.root, document.source_bytes = rebuilt.root, content
        document.format_id, document.fallback_diagnostic = rebuilt.format_id, None
        document.short_id_map, document.short_id_index = ShortIdMap(), {}
        document.reindex()
        document.document_version += 1
    return document

def resolve_address(document: TreeDocument, address: Address) -> UUID:
    """Resolve any address form to its canonical UUID4 ({j9rh}): unknown or foreign-document raises
    ``NodeNotFound`` and an ambiguous short_id ``ShortIdConflict``, before any work."""
    try:
        return normalize_node_address(document, address, current_document_id=document.document_id,
                                      resolve_short_id=document.resolve_short_id)
    except NodeAddressError as exc:
        failure = ShortIdConflict if type(exc).__name__ == "AmbiguousAddressError" else NodeNotFound
        raise failure(f"unresolvable node address {address!r}", address=str(address)) from exc
def _nodes(document: TreeDocument, targets: Any) -> List[_LiveNode]:
    return [document.nodes_by_id[resolve_address(document, a)]
            for a in (targets if isinstance(targets, (list, tuple)) else [targets])]
def _check_version(document: TreeDocument, expected: Optional[int]) -> None:
    if expected is not None and expected != document.document_version:
        raise DocumentVersionConflict(f"expected_version {expected!r} != {document.document_version!r}",
                                      expected_version=expected, current_version=document.document_version)
@contextmanager
def _operation(document: TreeDocument, expected: Optional[int], default: ErrorCode = ErrorCode.INVALID_POSITION) -> Iterator[None]:
    _check_version(document, expected)
    with _LOCKS.acquire_locks([document.document_id]), _typed(default):
        yield
def _committed(document: TreeDocument, *parents: Optional[_LiveNode]) -> None:
    """Close a mutation: re-sync fields, drop each ancestor's now-stale cached source slice, reindex, bump."""
    for parent in parents:
        _sync_fields(parent)
        node: Optional[_LiveNode] = parent
        while node is not None:
            node.fields, node = {k: v for k, v in node.fields.items() if k not in _CACHED_SOURCE}, node.parent
    document.reindex()
    document.document_version += 1
def _fragment(document: TreeDocument, source: Union[str, bytes]) -> List[_LiveNode]:
    parsed = _plugin(document.format_id).parse_fragment(source)
    if isinstance(parsed, str):
        raise FormatFragmentParseFailed(f"{document.format_id} found no structure in the given fragment")
    roots = [_to_live(n) for n in (parsed if isinstance(parsed, (list, tuple)) else [parsed])]
    for node in (n for root in roots for n in _walk(root)):
        if node.node_id in document.nodes_by_id:
            node.node_id = generate_node_id()
        node.short_id = None
    return roots

def query(document: TreeDocument, selector: str, *, include_source: bool = False) -> List[QueryMatch]:
    """Run a selector over the loaded tree, never reparsing it; a malformed one raises ``InvalidSelector``."""
    with _typed(ErrorCode.INVALID_SELECTOR):
        return _query(document, _plugin(document.format_id), selector, include_source=include_source)
def drill_down(document: TreeDocument, address: Optional[Address] = None, *, depth: int = 1,
               expected_version: Optional[int] = None, include_attributes: bool = True, include_source: str = SOURCE_PREVIEW,
               source_preview_bytes: int = 256, max_output_bytes: int = 65536) -> OutlineResponse:
    """Read-only compact outline around ``address`` (the root by default)."""
    _check_version(document, expected_version)
    if address is not None:
        resolve_address(document, address)
    with _typed(ErrorCode.INVALID_SELECTOR):
        return _drill_down(document, address, depth=depth, include_attributes=include_attributes,
                           include_source=include_source, source_preview_bytes=source_preview_bytes,
                           max_output_bytes=max_output_bytes)
def insert(document: TreeDocument, source: Union[str, bytes], *, position: str, parent: Optional[Address] = None,
           sibling: Optional[Address] = None, index: Optional[int] = None,
           expected_version: Optional[int] = None) -> MutationResult:
    """Insert parsed ``source`` at a {p107} address: first_child, last_child, child_index, before, after."""
    with _operation(document, expected_version):
        parent_node = _nodes(document, parent)[0] if parent is not None else None
        sibling_node = _nodes(document, sibling)[0] if sibling is not None else None
        incoming = _fragment(document, source)[0]
        result = _ops.insert(document, incoming, position=position, parent=parent_node, sibling=sibling_node,
                             index=index, next_short_id=lambda: document.short_id_map.allocate(generate_node_id()))
        _committed(document, incoming.parent)
        return result
def delete(document: TreeDocument, targets: Any, *, expected_version: Optional[int] = None) -> MutationResult:
    """Delete a node, a contiguous sibling range, or a subtree ({p010})."""
    with _operation(document, expected_version):
        resolved = _nodes(document, targets)
        parent_node = resolved[0].parent
        result = _ops.delete(document, resolved)
        _committed(document, parent_node)
        return result
def replace(document: TreeDocument, targets: Any, source: Union[str, bytes], *,
            expected_version: Optional[int] = None) -> MutationResult:
    """Replace a contiguous sibling range with parsed ``source``, with no range-missing state ({p108})."""
    with _operation(document, expected_version):
        resolved = _nodes(document, targets)
        incoming, parent_node = _fragment(document, source), resolved[0].parent
        result = _ops.replace_range(document, resolved, incoming,
                                    next_short_id=lambda: document.short_id_map.allocate(generate_node_id()))
        _committed(document, parent_node)
        return result
def move(document: TreeDocument, targets: Any, *, position: str, parent: Optional[Address] = None,
         sibling: Optional[Address] = None, index: Optional[int] = None,
         target_document: Optional[TreeDocument] = None, expected_version: Optional[int] = None) -> MoveResult:
    """Move a subtree or sibling range within one document or across two, both locks in id order ({p035})."""
    _check_version(document, expected_version)
    target = target_document if target_document is not None else document
    resolved = _nodes(document, targets)
    source_parent = resolved[0].parent
    parent_node = _nodes(target, parent)[0] if parent is not None else None
    sibling_node = _nodes(target, sibling)[0] if sibling is not None else None
    with _typed(ErrorCode.INVALID_POSITION):
        result = _move_mod.move(document, resolved, position=position, target_document=target, parent=parent_node,
                                sibling=sibling_node, index=index, lock_coordinator=_LOCKS.acquire_locks)
        _committed(document, source_parent)
        if target is not document:
            _committed(target, resolved[0].parent)
        return result
def copy_subtree(document: TreeDocument, address: Optional[Address] = None, *, expected_version: Optional[int] = None,
                 preserve_ids: bool = False) -> CopiedDocument:
    """A read-only copy of the subtree at ``address`` ({p072}) for :func:`apply_subtree`; ``preserve_ids``
    keeps the original UUID4s ({p074}) instead of minting fresh ones ({p073})."""
    _check_version(document, expected_version)
    node_id = resolve_address(document, address) if address is not None else None
    with _typed(ErrorCode.NODE_NOT_FOUND):
        copy = _copy_mod.copy_subtree(document, node_id, expected_version, preserve_ids)
        _relink(copy.root, None)
        return copy
def apply_subtree(document: TreeDocument, copy: CopiedDocument, *,
                  expected_version: Optional[int] = None) -> ApplySubtreeResult:
    """Return ``copy`` into ``document``, replacing the subtree it came from ({p076})."""
    with _operation(document, expected_version, ErrorCode.NODE_ID_CONFLICT):
        result = _apply_mod.apply_subtree(document, copy, expected_version=expected_version)
        _relink(document.root, None)
        applied = document.nodes_by_id.get(result.node_id)
        _committed(document, applied.parent if applied is not None else None)
        return result
def set_attribute(document: TreeDocument, address: Address, name: str, value: Any, *,
                  expected_version: Optional[int] = None) -> MutationResult:
    """Set one primitive field on the addressed node ({p011}); the node itself decides admissibility."""
    with _operation(document, expected_version, ErrorCode.INVALID_PARENT_TYPE):
        result = _updates.set_attribute(document, _nodes(document, address)[0], name, value)
        document.document_version += 1
        return result
def set_body(document: TreeDocument, address: Address, source: Union[str, bytes], *,
             expected_version: Optional[int] = None) -> MutationResult:
    """Replace the addressed node's children with parsed ``source`` ({p038}); every root clears the shared
    preflight first, so a rejection changes nothing."""
    with _operation(document, expected_version, ErrorCode.INVALID_PARENT_TYPE):
        node = _nodes(document, address)[0]
        outcome = _updates.set_body(document, node, _fragment(document, source),
                                    admits_nested_structure=lambda _n: True,
                                    parse_fragment=lambda text, **_kw: _fragment(document, text)[0],
                                    source_format_id=document.format_id,
                                    next_short_id=lambda: document.short_id_map.allocate(generate_node_id()))
        _committed(document, node)
        return outcome.mutation
def replace_node_id(document: TreeDocument, address: Address, new_node_id: UUID, *,
                    expected_version: Optional[int] = None) -> AddressRemap:
    """Atomically rewrite the addressed node's UUID4, keeping its short_id ({p109})."""
    with _operation(document, expected_version, ErrorCode.NODE_ID_CONFLICT):
        old_node_id = resolve_address(document, address)
        remap = _updates.replace_node_id(document, old_node_id, new_node_id)
        document.short_id_map.rekey(old_node_id, new_node_id)
        document.reindex()
        document.document_version += 1
        return remap
