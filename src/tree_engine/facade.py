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
from dataclasses import replace as _replace_dataclass
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
from tree_engine.exceptions import (DocumentVersionConflict, FormatFragmentParseFailed,
    FormatPluginNotFound, NodeNotFound, ShortIdConflict, TreeEngineException, exception_for_code)
from tree_engine.plugins.detachable import DETACHABLE_PLUGIN_SPECS, load_detachable_plugin
from tree_engine.plugins.fallback import PLAIN_TEXT_FORMAT_ID, build_fallback_tree
from tree_engine.plugins.json_format import JSON_FORMAT_PLUGIN
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.plugins.selection import build_extension_table, resolve_format_plugin
from tree_engine.plugins.toml_format import TOML_FORMAT_PLUGIN
from tree_engine.plugins.yaml.plugin import YAML_FORMAT_PLUGIN
from tree_engine.query.engine import query as _query
from tree_engine.query.inspection import SOURCE_FULL, SOURCE_NONE, SOURCE_PREVIEW, drill_down as _drill_down
from tree_engine.query.outline import OutlineResponse
from tree_engine.query.results import QueryMatch
from tree_engine.storage.document_bridge import (DocumentStore, OpenBranch, OpenedTree,
    TreeWriteIntent, WrittenPair)
from tree_engine.storage.history import Checkpoint, CheckpointKind, HistoryPort

__all__ = [
    "TreeDocument", "Address", "load", "save", "reparse", "loads", "dumps", "query", "drill_down",
    "insert", "delete", "replace", "move", "copy_subtree", "apply_subtree", "set_attribute",
    "set_body", "replace_node_id", "resolve_address", "register_format_plugin", "list_formats",
    "open_bytes", "open_file", "write", "SOURCE_NONE", "SOURCE_PREVIEW", "SOURCE_FULL",
    "PLAIN_TEXT_FORMAT_ID", "AddressRemap", "ApplySubtreeResult", "Checkpoint", "CheckpointKind",
    "CopiedDocument", "HistoryPort", "MoveResult", "MutationResult", "NodeAddress", "OpenBranch",
    "OpenedTree", "OutlineResponse", "QueryMatch", "TreeWriteIntent", "WrittenPair"]

#: Every address form {j9rh} accepts, on every address-taking command below.
Address = Union[UUID, int, str, NodeAddress]

#: Result types re-exported off the core modules already imported above, so a caller annotating or
#: isinstance-checking a result never has to reach past this facade for the type.
MoveResult, MutationResult = _move_mod.MoveResult, _ops.MutationResult
ApplySubtreeResult, CopiedDocument = _apply_mod.ApplySubtreeResult, _copy_mod.CopiedDocument

#: The data formats, always present: stdlib-only or one small stable library, and needed by every
#: consumer of the engine. The LANGUAGE formats are not here -- see ``plugins/detachable.py`` for
#: why python and bsl are loaded through an import that is allowed to fail.
_BASE_PLUGINS = (JSON_FORMAT_PLUGIN, TOML_FORMAT_PLUGIN, YAML_FORMAT_PLUGIN,
                 PLAIN_TEXT_FORMAT_PLUGIN)
_REGISTRY = FormatPluginRegistry()
_EXTENSIONS: Dict[str, str] = {}
#: format_id -> the refusal for a format that ships here but whose parser library is not installed.
#: An entry means the format is KNOWN and unavailable, which is a different answer from unknown,
#: and the facade gives it before any resolution so the caller is told what to install ({p023}).
_DETACHED: Dict[str, str] = {}
for _spec in DETACHABLE_PLUGIN_SPECS:
    _plugin_object, _why = load_detachable_plugin(_spec)
    if _plugin_object is None:
        _DETACHED[_spec.format_id] = _why or ""
        _EXTENSIONS.update({extension: _spec.format_id for extension in _spec.file_extensions})
        continue
    _REGISTRY.register_format_plugin(_plugin_object, replace=True)
    _EXTENSIONS.update(build_extension_table([_plugin_object]))
for _builtin in _BASE_PLUGINS:
    _REGISTRY.register_format_plugin(_builtin, replace=True)
_EXTENSIONS.update(build_extension_table(_BASE_PLUGINS))
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

def _detached(format_id: Optional[str] = None, file_path: Optional[str] = None) -> Optional[str]:
    """The refusal for a format that ships with the engine but whose parser is not installed, or
    ``None``. Resolution order mirrors :func:`_plugin`'s: an explicit ``format_id`` decides alone
    ({p061}), otherwise the path's extension does, through the same table."""
    if format_id is not None:
        return _DETACHED.get(format_id)
    if file_path:
        extension = Path(file_path).suffix.lstrip(".").lower()
        return _DETACHED.get(_EXTENSIONS.get(extension, ""))
    return None

def _plugin(format_id: Optional[str] = None, file_path: Optional[str] = None) -> Any:
    """Resolve exactly one format plugin, explicit ``format_id`` first ({p061}).

    A format whose plugin is shipped but detached is refused here, by name, before resolution: the
    alternative answers are all worse than a refusal -- ``FORMAT_UNKNOWN_EXTENSION`` would claim
    the engine has never heard of ``.py``, a bare ``FORMAT_PLUGIN_NOT_FOUND`` would not say what to
    install, and the plain-text fallback would quietly hand back a Python file parsed as text."""
    refusal = _detached(format_id, file_path)
    if refusal is not None:
        raise FormatPluginNotFound(refusal)
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

#: The storage half of this facade: the source/tree pair, the checksum open decision, and the write
#: that persists node identity. Built over the same registry and extension table every other call
#: resolves through, and driven through this module's own ``loads``/``dumps`` so the rebuild branch
#: keeps one plugin resolution and one authorized plain-text fallback rather than a second copy.
_STORE = DocumentStore(_REGISTRY, parse_source=loads, render_source=dumps,
                       extension_table=_EXTENSIONS)

def open_bytes(source: Union[str, bytes], *, tree: Optional[bytes] = None,
               format_id: Optional[str] = None, file_path: Optional[str] = None,
               allow_plain_text_fallback: bool = True,
               active_session_holds_file: bool = False,
               history: Optional[HistoryPort] = None) -> OpenedTree:
    """Take the open decision from BYTES: the source bytes, and the stored tree file's bytes when
    the caller has them ({p087}). For a caller that already holds the content -- one that fetched
    both files from somewhere that is not this filesystem, or that must not create files where
    they live -- this is the whole of open, and it touches no filesystem at all.

    The recorded ``source_sha256`` decides. Matching, the stored tree IS the document and every
    node keeps its ``node_id`` and its ``short_id``; absent or unusable, the source is parsed with
    fresh identity. A mismatch is decided by ``active_session_holds_file``, which only the caller
    knows: with no session the file on disk is the truth and the tree is rebuilt, with a session
    holding it the tree is the truth and is kept. :class:`OpenedTree` reports which of the four
    branches was taken, whether identity survived, the tree file bytes the decision calls for, and
    what would have to happen to the tree file for it to agree -- which this call leaves to the
    caller, having written nothing."""
    return _STORE.open_bytes(source, tree=tree, format_id=format_id, file_path=file_path,
                             allow_plain_text_fallback=allow_plain_text_fallback,
                             active_session_holds_file=active_session_holds_file, history=history)

def open_file(path: Union[str, Path], *, format_id: Optional[str] = None,
              allow_plain_text_fallback: bool = True,
              active_session_holds_file: bool = False,
              history: Optional[HistoryPort] = None) -> OpenedTree:
    """:func:`open_bytes` over a real pair on disk, acting on the intent it computes.

    The SOURCE file is read and never written: it takes no part in the file transaction this
    performs, so its bytes and its mtime are unchanged whatever the decision was. The derived TREE
    file is created when there is none and refreshed when the source has superseded it -- that is
    not a violation of a read-only open, it is what gives the next open identity to hand out.
    ``written_paths`` on the result is exactly what was written, which is the tree file or nothing.
    Use :func:`open_bytes` where even the derived artefact must not be created."""
    return _STORE.open_file(path, format_id=format_id,
                            allow_plain_text_fallback=allow_plain_text_fallback,
                            active_session_holds_file=active_session_holds_file, history=history)

def load(path: Union[str, Path], *, format_id: Optional[str] = None,
         allow_plain_text_fallback: bool = True,
         active_session_holds_file: bool = False,
         history: Optional[HistoryPort] = None) -> TreeDocument:
    """Read ``path`` and open it into a :class:`TreeDocument`, through the storage layer ({p085}).
    The document of :func:`open_file` and nothing else: a valid tree file beside ``path`` is
    accepted and identity survives the reload, a stale or absent one is rebuilt from the source and
    the tree file brought up to date. Use :func:`open_file` instead when the branch, the refusal
    reason, the write intent or the paths written matter."""
    return open_file(path, format_id=format_id,
                     allow_plain_text_fallback=allow_plain_text_fallback,
                     active_session_holds_file=active_session_holds_file,
                     history=history).document

def write(document: TreeDocument, path: Optional[Union[str, Path]] = None, *,
          history: Optional[HistoryPort] = None) -> WrittenPair:
    """Render ``document`` and publish the source/tree pair as one recoverable transaction ({p090}),
    reporting every path written. This is where identity is persisted through an edit: the tree
    file carries each node's ``node_id``/``short_id`` and the live ``short_id_map`` with its
    monotonic counter, so the next open of these bytes takes the SHA_MATCH branch with identity
    intact.

    ``written_paths`` is the whole of the change -- nothing else is created and no journal survives
    a successful publication -- so a caller that owns atomicity elsewhere can stage exactly those
    files. A checkpoint is recorded through ``history`` once the publication is verified on disk."""
    with _typed(ErrorCode.STORAGE_IO_ERROR):
        return _STORE.write(document, path, history=history)

def save(document: TreeDocument, path: Optional[Union[str, Path]] = None, *,
         history: Optional[HistoryPort] = None) -> Path:
    """The source path :func:`write` published, for a caller that needs nothing else from it."""
    return write(document, path, history=history).source_path

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
    core preflight.

    A fragment parser is free to wrap its result in a CONTAINER of its own -- ``plain_text``'s does,
    documenting that ``parse_fragment`` "always yields a root container Node" -- and splicing that
    container in as a sibling builds a tree the same format then cannot render: ``dumps()`` fails
    with ``UNSUPPORTED_TRANSLATION`` on a ``plain_text:root`` found where a paragraph belongs. A
    plugin says so by declaring ``fragment_container_kinds``, and such a node is unwrapped to its
    children, which are the content the caller meant. The declaration is what keeps this narrow:
    for JSON an object returned by ``parse_fragment`` is a genuine value and must NOT be unwrapped,
    even though it carries the document root's own kind. An empty container carries no content at
    all, so it raises like every other structureless fragment instead of splicing nothing."""
    plugin = _plugin(document.format_id)
    parsed = plugin.parse_fragment(source)
    if isinstance(parsed, str):
        raise FormatFragmentParseFailed(
            f"{document.format_id} found no structure in the given fragment")
    roots = [to_live(n) for n in (parsed if isinstance(parsed, (list, tuple)) else [parsed])]
    containers = tuple(getattr(plugin, "fragment_container_kinds", ()) or ())
    if len(roots) == 1 and roots[0].kind in containers:
        roots = roots[0].children
        for node in roots:
            node.parent = None
        if not roots:
            raise FormatFragmentParseFailed(
                f"{document.format_id} found no structure in the given fragment")
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
    ``last_child``, ``child_index`` (with ``index``), ``before``, or ``after``.

    A fragment that parses into SEVERAL nodes is inserted whole, in order, rather than having
    everything after the first silently dropped. The core splice takes one node at a time against a
    fixed anchor, so the order of the calls is what fixes the final order: ``first_child`` and
    ``after`` are spliced back to front, ``before``/``last_child``/``child_index`` front to back.
    The returned :class:`MutationResult` describes the FIRST fragment node -- its ``node_id``,
    ``short_id`` and final ``position`` -- and carries the ``inserted`` addresses and short_id
    ``remap`` of every one of them, in fragment order."""
    reverse = position in ("first_child", "after")
    with _operation(document, expected_version):
        parent_node = _nodes(document, parent)[0] if parent is not None else None
        sibling_node = _nodes(document, sibling)[0] if sibling is not None else None
        incoming = _fragment(document, source)
        results = [
            _ops.insert(document, node, position=position, parent=parent_node,
                        sibling=sibling_node, index=index if index is None else index + offset,
                        next_short_id=lambda: _next_short_id(document))
            for offset, node in enumerate(reversed(incoming) if reverse else incoming)]
        ordered = list(reversed(results)) if reverse else results
        result = _replace_dataclass(
            ordered[0], remap=tuple(entry for step in ordered for entry in step.remap),
            inserted=tuple(address for step in ordered for address in step.inserted))
        _committed(document, incoming[0].parent)
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
