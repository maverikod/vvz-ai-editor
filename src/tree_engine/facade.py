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
coordinator, a two-document ``move`` taking both locks in document_id order ({p035}). The mutable
working representation the core's splices need, its conversion pair with the immutable
``core.nodes.Node``, and the fields/children and cached-source rules that keep an edit renderable are
owned by ``core.live_tree``; this module only drives them.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
from uuid import UUID

from tree_engine.core import move as _move_mod, operations as _ops, subtree_apply as _apply_mod
from tree_engine.core import subtree_copy as _copy_mod, updates as _updates
from tree_engine.core.address import NodeAddressError, normalize_node_address
from tree_engine.core.identity import AddressRemap, NodeAddress, generate_node_id
from tree_engine.core.live_tree import (LiveNode, TreeDocument, invalidate_cached_source, relink,
    sync_fields, to_frozen, to_live, walk)
from tree_engine.core.locking import DocumentLockCoordinator
from tree_engine.core.nodes import Document
from tree_engine.core.short_id import ShortIdMap
from tree_engine.errors import ErrorCode
from tree_engine.exceptions import (DocumentVersionConflict, FormatFragmentParseFailed, NodeNotFound,
    ShortIdConflict, StorageIOError, TreeEngineException, exception_for_code)
from tree_engine.plugins.bsl.plugin import BSL_FORMAT_PLUGIN
from tree_engine.plugins.fallback import PLAIN_TEXT_FORMAT_ID, build_fallback_tree
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.plugins.selection import build_extension_table, resolve_format_plugin
from tree_engine.plugins.toml_format import TOML_FORMAT_PLUGIN
from tree_engine.plugins.yaml.plugin import YAML_FORMAT_PLUGIN
from tree_engine.query.engine import query as _query
from tree_engine.query.inspection import SOURCE_FULL, SOURCE_NONE, SOURCE_PREVIEW, drill_down as _drill_down
from tree_engine.query.outline import OutlineResponse
from tree_engine.query.results import QueryMatch
from tree_engine.storage.file_txn import FileWrite, publish

__all__ = [
    "TreeDocument", "Address", "load", "save", "reparse", "loads", "dumps", "query", "drill_down",
    "insert", "delete", "replace", "move", "copy_subtree", "apply_subtree", "set_attribute",
    "set_body", "replace_node_id", "resolve_address", "register_format_plugin", "list_formats",
    "SOURCE_NONE", "SOURCE_PREVIEW", "SOURCE_FULL", "PLAIN_TEXT_FORMAT_ID", "AddressRemap",
    "ApplySubtreeResult", "CopiedDocument", "MoveResult", "MutationResult", "NodeAddress",
    "OutlineResponse", "QueryMatch"]

#: Every address form {j9rh} accepts, on every address-taking command below.
Address = Union[UUID, int, str, NodeAddress]

#: Result types re-exported off the core modules already imported above, so a caller annotating or
#: isinstance-checking a result never has to reach past this facade for the type.
MoveResult, MutationResult = _move_mod.MoveResult, _ops.MutationResult
ApplySubtreeResult, CopiedDocument = _apply_mod.ApplySubtreeResult, _copy_mod.CopiedDocument

_BUILTINS = (PYTHON_FORMAT_PLUGIN, BSL_FORMAT_PLUGIN, JSON_FORMAT_PLUGIN, TOML_FORMAT_PLUGIN,
             YAML_FORMAT_PLUGIN, PLAIN_TEXT_FORMAT_PLUGIN)
_REGISTRY = FormatPluginRegistry()
for _builtin in _BUILTINS:
    _REGISTRY.register_format_plugin(_builtin, replace=True)
_EXTENSIONS: Dict[str, str] = dict(build_extension_table(_BUILTINS))
_LOCKS = DocumentLockCoordinator()

# -- typed-error boundary ---------------------------------------------------

def _code_of(exc: BaseException) -> Optional[ErrorCode]:
    """The stable ``ErrorCode`` an internal exception already declares, if any: ``.code``, then the
    older ``.error_code`` the plugin contract/registry errors still carry, then the first entry of a
    ``.errors`` validation list. ``None`` when it declares none."""
    for name in ("code", "error_code"):
        if isinstance(getattr(exc, name, None), ErrorCode):
            return getattr(exc, name)
    for entry in getattr(exc, "errors", None) or ():
        if isinstance(getattr(entry, "code", None), ErrorCode):
            return entry.code
    return None

@contextmanager
def _typed(default: ErrorCode) -> Iterator[None]:
    """Guarantee every escaping error is a typed ``tree_engine.exceptions``: one already in the public
    hierarchy passes through untouched, any other is re-raised (chained) as the class owning its
    declared ``ErrorCode``, or ``default`` when it declares none -- so no bare ``KeyError``,
    ``ValueError`` or ``AttributeError`` from an internal layer ever reaches a caller."""
    try:
        yield
    except TreeEngineException:
        raise
    except Exception as exc:
        code = _code_of(exc) or (ErrorCode.STORAGE_IO_ERROR if isinstance(exc, OSError) else default)
        raise exception_for_code(code)(str(exc) or type(exc).__name__) from exc

# -- plugin resolution, content and file entry points ({p037}) --------------

def _plugin(format_id: Optional[str] = None, file_path: Optional[str] = None) -> Any:
    """Resolve exactly one format plugin, explicit ``format_id`` first ({p061})."""
    return resolve_format_plugin(format_id=format_id, file_path=file_path, registry=_REGISTRY,
                                 extension_table=_EXTENSIONS)

def register_format_plugin(plugin: Any, *, replace: bool = False) -> None:
    """Register a format plugin with this facade: it joins both the registry and the extension table,
    so an explicit ``format_id`` and each of its declared file extensions resolve to it from here on."""
    with _typed(ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR):
        _REGISTRY.register_format_plugin(plugin, replace=replace)
        _EXTENSIONS.update(build_extension_table([plugin]))

def list_formats() -> Tuple[str, ...]:
    """The ``format_id`` of every format plugin currently registered with this facade."""
    return tuple(metadata.format_id for metadata in _REGISTRY.list_format_plugins())

def loads(content: Union[str, bytes], *, format_id: Optional[str] = None,
          file_path: Optional[str] = None, allow_plain_text_fallback: bool = True) -> TreeDocument:
    """Parse in-memory content into a :class:`TreeDocument` ({p037}): the format is ``format_id`` when
    given, else ``file_path``'s extension, and neither resolving raises ``FormatUnknownExtension``. Only
    a ``FORMAT_CONTENT_PARSE_FAILED`` from the resolved plugin may open the authorized plain-text
    fallback ({p058}, {p063}); every other failure reaches the caller unmasked."""
    with _typed(ErrorCode.FORMAT_CONTENT_PARSE_FAILED):
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        plugin = _plugin(format_id, file_path)
        source_id, path = plugin.metadata.format_id, Path(file_path) if file_path else None
        try:
            parsed = plugin.parse_document(text)
        except Exception as exc:
            if not (allow_plain_text_fallback
                    and _code_of(exc) is ErrorCode.FORMAT_CONTENT_PARSE_FAILED):
                raise
            back = build_fallback_tree(text, exc, source_format_id=source_id)
            return TreeDocument(to_live(back.document.root), source_id, PLAIN_TEXT_FORMAT_ID,
                                text.encode("utf-8"), path=path,
                                fallback_diagnostic=back.metadata.diagnostic)
        return TreeDocument(to_live(parsed.root), source_id, parsed.representation_format_id,
                            text.encode("utf-8"), path=path)

def dumps(document: TreeDocument) -> bytes:
    """Render ``document`` back to source bytes through its own format plugin."""
    with _typed(ErrorCode.UNSUPPORTED_TRANSLATION):
        common = Document(root=to_frozen(document.root), source_format_id=document.source_format_id,
                          representation_format_id=document.format_id)
        output = _plugin(document.format_id).generate_output(common, {})
        return output if isinstance(output, bytes) else str(output).encode("utf-8")

def load(path: Union[str, Path], *, format_id: Optional[str] = None,
         allow_plain_text_fallback: bool = True) -> TreeDocument:
    """Read ``path`` and parse it into a :class:`TreeDocument`. This is the direct-file path over the
    merged storage siblings: the recoverable open of a source/tree *pair* -- partial-publication
    recovery, source_sha256 conflict detection, edit-session concurrency -- belongs to
    ``storage/lifecycle.py``, not merged yet; this call routes there once it lands."""
    with _typed(ErrorCode.STORAGE_IO_ERROR):
        content = Path(path).read_bytes()
    return loads(content, format_id=format_id, file_path=str(path),
                 allow_plain_text_fallback=allow_plain_text_fallback)

def save(document: TreeDocument, path: Optional[Union[str, Path]] = None) -> Path:
    """Render ``document`` and publish it as one recoverable file transaction ({p090}). The
    lifecycle-owned tree-file companion, its checksums, and conflict policy wait on
    ``storage/lifecycle.py``, exactly as :func:`load` documents."""
    content = dumps(document)
    with _typed(ErrorCode.STORAGE_IO_ERROR):
        target = Path(path) if path is not None else document.path
        if target is None:
            raise StorageIOError("save() needs a path: this document came from loads(), not a file")
        publish([FileWrite(target_path=target, content=content)],
                target.with_suffix(target.suffix + ".journal"))
        document.path, document.source_bytes = target, content
        return target

def reparse(document: TreeDocument) -> TreeDocument:
    """Rebuild ``document`` from its own rendered source, in place ({p037}): render, parse again with
    the source format's plugin, and swap the result in with fresh indexes and a bumped version. Never
    an implicit side effect of any other call."""
    content = dumps(document)
    rebuilt = loads(content, format_id=document.source_format_id, allow_plain_text_fallback=False)
    with _operation(document, None):
        document.root, document.source_bytes = rebuilt.root, content
        document.format_id, document.fallback_diagnostic = rebuilt.format_id, None
        document.short_id_map, document.short_id_index = ShortIdMap(), {}
        document.reindex()
        document.document_version += 1
    return document

# -- addressing, versioning, locking ----------------------------------------

def resolve_address(document: TreeDocument, address: Address) -> UUID:
    """Resolve any accepted address form -- a UUID4, a positive-int or ``0x``-hex short_id, or a
    ``"document_id:node_id"`` string -- to its canonical UUID4 ({j9rh}). An unknown or
    foreign-document address raises ``NodeNotFound`` and an ambiguous short_id ``ShortIdConflict``,
    both before any operation starts."""
    try:
        return normalize_node_address(document, address, current_document_id=document.document_id,
                                      resolve_short_id=document.resolve_short_id)
    except NodeAddressError as exc:
        failure = ShortIdConflict if type(exc).__name__ == "AmbiguousAddressError" else NodeNotFound
        raise failure(f"unresolvable node address {address!r}", address=str(address)) from exc

def _nodes(document: TreeDocument, targets: Any) -> List[LiveNode]:
    """One address, or an ordered sequence of them, all resolved before any work begins."""
    return [document.nodes_by_id[resolve_address(document, a)]
            for a in (targets if isinstance(targets, (list, tuple)) else [targets])]

def _check_version(document: TreeDocument, expected: Optional[int]) -> None:
    """Reject a stale operation before any mutation starts ({p024})."""
    if expected is not None and expected != document.document_version:
        raise DocumentVersionConflict(f"expected_version {expected!r} does not match "
                                      f"document_version {document.document_version!r}",
                                      expected_version=expected,
                                      current_version=document.document_version)

@contextmanager
def _operation(document: TreeDocument, expected: Optional[int],
               default: ErrorCode = ErrorCode.INVALID_POSITION) -> Iterator[None]:
    """One mutating command: check ``expected_version`` ({p024}), hold this document's lock for the
    whole operation ({p035}), and type every escaping error."""
    _check_version(document, expected)
    with _LOCKS.acquire_locks([document.document_id]), _typed(default):
        yield

def _committed(document: TreeDocument, *parents: Optional[LiveNode]) -> None:
    """Close a successful mutation: mirror each affected parent's new children back into its
    node-holding fields, invalidate the cached source slice every ancestor of the edit now holds
    stale, then reindex and bump the version."""
    for parent in parents:
        sync_fields(parent)
        invalidate_cached_source(parent)
    document.reindex()
    document.document_version += 1

def _fragment(document: TreeDocument, source: Union[str, bytes]) -> List[LiveNode]:
    """Parse caller-supplied source into fresh live nodes through the document's own plugin, giving a
    node whose id would collide with a live one a fresh UUID4 and leaving short_id allocation to the
    core preflight."""
    parsed = _plugin(document.format_id).parse_fragment(source)
    if isinstance(parsed, str):
        raise FormatFragmentParseFailed(
            f"{document.format_id} found no structure in the given fragment")
    roots = [to_live(n) for n in (parsed if isinstance(parsed, (list, tuple)) else [parsed])]
    for node in (n for root in roots for n in walk(root)):
        if node.node_id in document.nodes_by_id:
            node.node_id = generate_node_id()
        node.short_id = None
    return roots

def _next_short_id(document: TreeDocument) -> int:
    """The document's own monotonic allocator, injected into the core preflight ({p097})."""
    return document.short_id_map.allocate(generate_node_id())

# -- document operations ({p037}) -------------------------------------------

def query(document: TreeDocument, selector: str, *,
          include_source: bool = False) -> List[QueryMatch]:
    """Run a selector over the loaded tree, never reparsing its source; a malformed selector raises
    ``InvalidSelector``."""
    with _typed(ErrorCode.INVALID_SELECTOR):
        return _query(document, _plugin(document.format_id), selector,
                      include_source=include_source)

def drill_down(document: TreeDocument, address: Optional[Address] = None, *, depth: int = 1,
               expected_version: Optional[int] = None, include_attributes: bool = True,
               include_source: str = SOURCE_PREVIEW, source_preview_bytes: int = 256,
               max_output_bytes: int = 65536) -> OutlineResponse:
    """Read-only compact outline around ``address`` (the document root by default)."""
    _check_version(document, expected_version)
    if address is not None:
        resolve_address(document, address)
    with _typed(ErrorCode.INVALID_SELECTOR):
        return _drill_down(document, address, depth=depth, include_attributes=include_attributes,
                           include_source=include_source, source_preview_bytes=source_preview_bytes,
                           max_output_bytes=max_output_bytes)

def insert(document: TreeDocument, source: Union[str, bytes], *, position: str,
           parent: Optional[Address] = None, sibling: Optional[Address] = None,
           index: Optional[int] = None, expected_version: Optional[int] = None) -> MutationResult:
    """Parse ``source`` and insert it at one {p107} positional address: ``first_child``,
    ``last_child``, ``child_index`` (with ``index``), ``before``, or ``after``."""
    with _operation(document, expected_version):
        parent_node = _nodes(document, parent)[0] if parent is not None else None
        sibling_node = _nodes(document, sibling)[0] if sibling is not None else None
        incoming = _fragment(document, source)[0]
        result = _ops.insert(document, incoming, position=position, parent=parent_node,
                             sibling=sibling_node, index=index,
                             next_short_id=lambda: _next_short_id(document))
        _committed(document, incoming.parent)
        return result

def delete(document: TreeDocument, targets: Any, *,
           expected_version: Optional[int] = None) -> MutationResult:
    """Delete a node, a contiguous sibling range, or a subtree ({p010})."""
    with _operation(document, expected_version):
        resolved = _nodes(document, targets)
        parent_node = resolved[0].parent
        result = _ops.delete(document, resolved)
        _committed(document, parent_node)
        return result

def replace(document: TreeDocument, targets: Any, source: Union[str, bytes], *,
            expected_version: Optional[int] = None) -> MutationResult:
    """Atomically replace a contiguous sibling range with parsed ``source`` ({p108}): no intermediate
    range-missing state is ever observable."""
    with _operation(document, expected_version):
        resolved = _nodes(document, targets)
        incoming, parent_node = _fragment(document, source), resolved[0].parent
        result = _ops.replace_range(document, resolved, incoming,
                                    next_short_id=lambda: _next_short_id(document))
        _committed(document, parent_node)
        return result

def move(document: TreeDocument, targets: Any, *, position: str, parent: Optional[Address] = None,
         sibling: Optional[Address] = None, index: Optional[int] = None,
         target_document: Optional[TreeDocument] = None,
         expected_version: Optional[int] = None) -> MoveResult:
    """Move a subtree or sibling range, within one document or across two: both locks are taken in
    deterministic document_id order by the shared coordinator, so a concurrent move can neither
    deadlock nor publish partly ({p035})."""
    _check_version(document, expected_version)
    target = target_document if target_document is not None else document
    resolved = _nodes(document, targets)
    source_parent = resolved[0].parent
    parent_node = _nodes(target, parent)[0] if parent is not None else None
    sibling_node = _nodes(target, sibling)[0] if sibling is not None else None
    with _typed(ErrorCode.INVALID_POSITION):
        result = _move_mod.move(document, resolved, position=position, target_document=target,
                                parent=parent_node, sibling=sibling_node, index=index,
                                lock_coordinator=_LOCKS.acquire_locks)
        _committed(document, source_parent)
        if target is not document:
            _committed(target, resolved[0].parent)
        return result

def copy_subtree(document: TreeDocument, address: Optional[Address] = None, *,
                 expected_version: Optional[int] = None,
                 preserve_ids: bool = False) -> CopiedDocument:
    """An independent, read-only copy of the subtree at ``address`` ({p072}), for
    :func:`apply_subtree`. ``preserve_ids`` keeps the original UUID4s ({p074}) instead of minting
    fresh ones ({p073})."""
    _check_version(document, expected_version)
    node_id = resolve_address(document, address) if address is not None else None
    with _typed(ErrorCode.NODE_NOT_FOUND):
        copy = _copy_mod.copy_subtree(document, node_id, expected_version, preserve_ids)
        relink(copy.root, None)
        return copy

def apply_subtree(document: TreeDocument, copy: CopiedDocument, *,
                  expected_version: Optional[int] = None) -> ApplySubtreeResult:
    """Return ``copy`` into ``document``, replacing the subtree it was taken from ({p076})."""
    with _operation(document, expected_version, ErrorCode.NODE_ID_CONFLICT):
        result = _apply_mod.apply_subtree(document, copy, expected_version=expected_version)
        relink(document.root, None)
        applied = document.nodes_by_id.get(result.node_id)
        _committed(document, applied.parent if applied is not None else None)
        return result

def set_attribute(document: TreeDocument, address: Address, name: str, value: Any, *,
                  expected_version: Optional[int] = None) -> MutationResult:
    """Set one primitive field on the addressed node ({p011}); admissibility is decided by the node
    itself and a rejection mutates nothing."""
    with _operation(document, expected_version, ErrorCode.INVALID_PARENT_TYPE):
        node = _nodes(document, address)[0]
        result = _updates.set_attribute(document, node, name, value)
        # The edited node and its ancestors may still hold a parse-time source
        # slice; without invalidating it the new value is written into fields
        # and silently absent from rendered output ({p022}).
        invalidate_cached_source(node)
        document.document_version += 1
        return result

def set_body(document: TreeDocument, address: Address, source: Union[str, bytes], *,
             expected_version: Optional[int] = None) -> MutationResult:
    """Replace the addressed node's children with ``source``, parsed ({p038}): every incoming root
    clears the shared preflight before any existing child is removed, so a rejection leaves the node
    untouched."""
    with _operation(document, expected_version, ErrorCode.INVALID_PARENT_TYPE):
        node = _nodes(document, address)[0]
        outcome = _updates.set_body(document, node, _fragment(document, source),
                                    admits_nested_structure=lambda _n: True,
                                    parse_fragment=lambda text, **_kw: _fragment(document, text)[0],
                                    source_format_id=document.format_id,
                                    next_short_id=lambda: _next_short_id(document))
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
