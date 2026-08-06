"""Attribute, body, source-fragment, and identifier updates (concept C-006,
{p011}, {p038}, {p109}).

Runs on top of the sibling files already merged for this concept:
``validation.py`` (``validate_mutation``), ``operations.py`` (``insert``,
``delete``, ``MutationResult``, ``MutationError``), ``reparse.py``
(``reparse_edited_node``, the post-text-change auto-reparse stage this file
is the sole caller-facing counterpart of), and ``identity.py``
(``replace_node_id``, the low-level ``nodes_by_id`` id swap this file's own
``replace_node_id`` builds on). Same duck-typed ``document``/``node``
contract as those files: ``document.nodes_by_id``, an optional
``document.short_id_index`` (``short_id -> node_id``), and a node exposing
``node_id``, ``short_id``, ``parent``, ``children``. A node may additionally
expose ``get_attribute``/``set_attribute`` (the already-merged
``node_types.py`` wrapper contract) and a ``references`` tuple of
``NodeAddress``-like values (the reserved slot documented on ``nodes.py``'s
``Node``).

``set_attribute`` never classifies which attributes are export fields, or
implements any other field-admissibility policy, itself: it resolves the
target node and calls the node's own already-merged ``set_attribute``
method, which is where ``node_types.py``'s ``ExportFieldMixin`` already
decides -- before mutating anything -- whether a given field (``export`` in
particular) is admissible for that node's concrete type. A rejection
(``NodeSchemaError``, e.g. ``ExportNotApplicableError``) is caught and
re-raised as this concept's own ``MutationError`` carrying the same
``ErrorCode``; nothing is mutated on that path, since the node's own method
already validates before it writes.

``set_body`` accepts plain text, a single node, or a non-empty/empty
sequence of nodes. Text (and ``set_source_fragment``, always textual)
preserves the edited node's own existing leading indentation when the new
text does not already carry it, touches no sibling, and -- once the text is
written -- hands off exactly once to ``reparse.reparse_edited_node``,
surfacing whatever :class:`~tree_engine.core.reparse.ReparseOutcome` it
returns; a raised ``ReparseError`` restores the node's prior text before
propagating, so the whole update rolls back under the reparse stage's own
error code. A node or sequence body never goes through reparse (it is
already structured, not new text): every incoming root is preflighted with
``validate_mutation`` against the target as parent (``position=
"last_child"``, mirroring how ``reparse.py`` attaches new children) before
anything is touched; only after every root clears preflight are the node's
current children removed via the sibling ``operations.delete`` and the new
roots attached via ``operations.insert``, one call per root -- the same
reuse ``reparse.py`` already makes of those two functions.

``replace_node_id`` builds on ``identity.replace_node_id`` (validates and
swaps ``nodes_by_id`` atomically, raising before any mutation on a
malformed or colliding id) and additionally rekeys ``document
.short_id_index`` (the short_id itself is untouched, per {p097}; only the
node_id it currently points at moves) and rewrites the matching
``references`` entries of every node in ``document`` and in each
``loaded_documents`` entry the caller actually supplied -- never any other
document. Duplicates none of ``identity.py``'s validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from tree_engine.core.identity import AddressRemap, NodeAddress
from tree_engine.core.identity import replace_node_id as _identity_replace_node_id
from tree_engine.core.nodes import NodeSchemaError
from tree_engine.core.operations import MutationError, MutationResult, delete, insert
from tree_engine.core.reparse import ReparseError, ReparseOutcome, reparse_edited_node
from tree_engine.core.validation import ValidationError, validate_mutation
from tree_engine.errors import ErrorCode

__all__ = [
    "UpdateOutcome",
    "set_attribute",
    "set_body",
    "set_source_fragment",
    "replace_node_id",
]


@dataclass(frozen=True)
class UpdateOutcome:
    """Result of ``set_body``/``set_source_fragment``: the structural
    ``mutation`` (affected node's identity, unchanged position), plus
    ``reparse`` -- the :class:`~tree_engine.core.reparse.ReparseOutcome`
    when a text change was routed through the reparse stage, or ``None``
    for a node/sequence body (never reparsed, see module docstring)."""

    mutation: MutationResult
    reparse: Optional[ReparseOutcome] = None


# -- internal helpers, duplicated in miniature from the sibling files since
# they are private there (mirrors reparse.py's own precedent) ---------------


def _resolve(document: Any, ref: Any) -> Optional[Any]:
    if ref is None:
        return None
    nodes_by_id = getattr(document, "nodes_by_id", None) or {}
    candidate_id = getattr(ref, "node_id", None)
    if candidate_id is not None and nodes_by_id.get(candidate_id) is ref:
        return ref
    if isinstance(ref, UUID) and ref in nodes_by_id:
        return nodes_by_id[ref]
    short_index = getattr(document, "short_id_index", None)
    if isinstance(short_index, dict) and ref in short_index:
        return nodes_by_id.get(short_index[ref])
    for candidate in nodes_by_id.values():
        if getattr(candidate, "short_id", None) == ref:
            return candidate
    return None


def _fragment_nodes(root: Any) -> List[Any]:
    ordered: List[Any] = []
    stack = [root]
    while stack:
        node = stack.pop(0)
        ordered.append(node)
        stack = list(getattr(node, "children", None) or ()) + stack
    return ordered


def _get_content(node: Any) -> str:
    getter = getattr(node, "get_attribute", None)
    if callable(getter):
        return getter("content", "") or ""
    return getattr(node, "content", "") or ""


def _set_content(node: Any, text: str) -> None:
    setter = getattr(node, "set_attribute", None)
    if callable(setter):
        setter("content", text)
        return
    node.content = text


def _preserve_indentation(old_text: str, new_text: str) -> str:
    """Keep ``old_text``'s own leading indentation when ``new_text`` does
    not already carry it, so a caller passing bare re-indented content does
    not strip the node's place in its surrounding layout. Never touches any
    sibling: only ``old_text``/``new_text`` of this one node are read."""
    stripped_old = old_text.lstrip(" \t")
    indent = old_text[: len(old_text) - len(stripped_old)]
    if indent and not new_text.startswith(indent):
        return indent + new_text.lstrip(" \t")
    return new_text


def _retarget(address: Any, old_id: UUID, new_id: UUID, scanned_doc_id: Any, target_doc_id: Any) -> Any:
    """Retarget one reference iff it names the renamed node ``old_id`` *in
    the document being renamed* (``target_doc_id``): either an implicit
    local address (``document_id is None``) found while scanning that same
    document, or an explicit address naming ``target_doc_id`` outright. A
    local address found in any other scanned document names a node local to
    that other document instead, never the renamed one, and is left alone."""
    if getattr(address, "node_id", None) != old_id:
        return address
    addr_doc_id = getattr(address, "document_id", None)
    if addr_doc_id is None:
        if scanned_doc_id != target_doc_id:
            return address
    elif addr_doc_id != target_doc_id:
        return address
    return NodeAddress(document_id=addr_doc_id, node_id=new_id)


def _apply_text_and_reparse(
    document: Any,
    target: Any,
    new_text: str,
    *,
    source_format_id: str,
    admits_nested_structure: Callable[[Any], bool],
    parse_fragment: Callable[..., Any],
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]],
    references: Optional[Iterable[Any]],
    loaded_documents: Optional[Dict[Any, Any]],
    used_short_ids: Optional[Sequence[Any]],
    next_short_id: Optional[Callable[[], Any]],
    generate_node_id: Optional[Callable[[], Any]],
) -> UpdateOutcome:
    if is_type_compatible is not None and not is_type_compatible(target, "body", new_text):
        raise MutationError([
            ValidationError(
                code=ErrorCode.INVALID_PARENT_TYPE,
                message="text body is not admissible for this node's type",
                node_id=getattr(target, "node_id", None),
            )
        ])
    old_text = _get_content(target)
    final_text = _preserve_indentation(old_text, new_text)
    _set_content(target, final_text)
    kwargs: Dict[str, Any] = dict(
        is_type_compatible=is_type_compatible, references=references,
        loaded_documents=loaded_documents, used_short_ids=used_short_ids,
        next_short_id=next_short_id,
    )
    if generate_node_id is not None:
        kwargs["generate_node_id"] = generate_node_id
    try:
        outcome = reparse_edited_node(
            document, target, final_text, source_format_id=source_format_id,
            admits_nested_structure=admits_nested_structure, parse_fragment=parse_fragment,
            **kwargs,
        )
    except ReparseError:
        _set_content(target, old_text)
        raise
    mutation = MutationResult(
        node_id=getattr(target, "node_id", None), short_id=getattr(target, "short_id", None), position=None,
    )
    return UpdateOutcome(mutation=mutation, reparse=outcome)


def _replace_children(
    document: Any,
    parent_node: Any,
    roots: Sequence[Any],
    *,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]],
    references: Optional[Iterable[Any]],
    loaded_documents: Optional[Dict[Any, Any]],
    used_short_ids: Optional[Sequence[Any]],
    next_short_id: Optional[Callable[[], Any]],
) -> MutationResult:
    old_children = list(getattr(parent_node, "children", None) or ())
    all_fragment_nodes: List[Any] = []
    for root in roots:
        all_fragment_nodes.extend(_fragment_nodes(root))
    seen: set = set()
    for fnode in all_fragment_nodes:
        rid = getattr(fnode, "node_id", None)
        if rid is not None and rid in seen:
            raise MutationError([ValidationError(code=ErrorCode.NODE_ID_CONFLICT, message=f"node_id repeated in incoming body: {rid!r}")])
        seen.add(rid)
    dry_errors: List[ValidationError] = []
    for root in roots:
        result = validate_mutation(
            document, root, parent=parent_node, position="last_child",
            is_type_compatible=is_type_compatible, references=references,
            loaded_documents=loaded_documents, used_short_ids=used_short_ids, next_short_id=None,
        )
        dry_errors.extend(result.errors)
    if dry_errors:
        raise MutationError(dry_errors)

    # Preflight cleared for every root -- nothing has been touched yet.
    removed: Tuple[NodeAddress, ...] = ()
    if old_children:
        removed = delete(document, old_children).removed
    remap: List[Any] = []
    inserted: List[NodeAddress] = []
    for root in roots:
        result = insert(
            document, root, position="last_child", parent=parent_node,
            is_type_compatible=is_type_compatible, references=references,
            loaded_documents=loaded_documents, used_short_ids=used_short_ids, next_short_id=next_short_id,
        )
        remap.extend(result.remap)
        inserted.extend(result.inserted)
    return MutationResult(
        node_id=getattr(parent_node, "node_id", None), short_id=getattr(parent_node, "short_id", None),
        position=0, remap=tuple(remap), removed=removed, inserted=tuple(inserted),
    )


# -- public operations --------------------------------------------------


def set_attribute(document: Any, node: Any, name: str, value: Any) -> MutationResult:
    """Set field ``name`` on ``node`` ({p011}). Admissibility -- including
    whether ``name`` is an export field for this node's concrete type -- is
    decided entirely by the node's own already-merged ``set_attribute``
    method (see module docstring); this function adds no classification of
    its own and mutates nothing when that call raises."""
    target = _resolve(document, node)
    if target is None:
        raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"node could not be resolved: {node!r}")])
    setter = getattr(target, "set_attribute", None)
    if not callable(setter):
        raise MutationError([ValidationError(code=ErrorCode.INVALID_SELECTOR, message=f"node exposes no set_attribute: {type(target).__name__}")])
    try:
        setter(name, value)
    except NodeSchemaError as exc:
        raise MutationError([ValidationError(code=exc.code, message=str(exc), node_id=getattr(target, "node_id", None))]) from exc
    return MutationResult(node_id=getattr(target, "node_id", None), short_id=getattr(target, "short_id", None), position=None)


def set_body(
    document: Any,
    node: Any,
    body: Any,
    *,
    admits_nested_structure: Callable[[Any], bool],
    parse_fragment: Callable[..., Any],
    source_format_id: str = "",
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None,
    loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None,
    next_short_id: Optional[Callable[[], Any]] = None,
    generate_node_id: Optional[Callable[[], Any]] = None,
) -> UpdateOutcome:
    """Set ``node``'s body ({p038}): ``body`` is plain text, a single node,
    or a sequence of nodes. Text preserves the node's own indentation (see
    ``_preserve_indentation``) and, once written, routes exactly once
    through ``reparse.reparse_edited_node`` (rolled back on
    ``ReparseError``). A node/sequence body is preflighted whole against
    ``node`` as parent via the injected ``is_type_compatible`` -- the same
    compatibility rules ``validate_mutation`` already uses -- before any of
    the node's current children are removed or the new ones attached; a
    rejection leaves the node's existing children completely untouched."""
    target = _resolve(document, node)
    if target is None:
        raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"node could not be resolved: {node!r}")])
    if isinstance(body, str):
        return _apply_text_and_reparse(
            document, target, body, source_format_id=source_format_id,
            admits_nested_structure=admits_nested_structure, parse_fragment=parse_fragment,
            is_type_compatible=is_type_compatible, references=references, loaded_documents=loaded_documents,
            used_short_ids=used_short_ids, next_short_id=next_short_id, generate_node_id=generate_node_id,
        )
    roots = list(body) if isinstance(body, (list, tuple)) else [body]
    mutation = _replace_children(
        document, target, roots, is_type_compatible=is_type_compatible, references=references,
        loaded_documents=loaded_documents, used_short_ids=used_short_ids, next_short_id=next_short_id,
    )
    return UpdateOutcome(mutation=mutation, reparse=None)


def set_source_fragment(
    document: Any,
    node: Any,
    fragment_text: str,
    *,
    admits_nested_structure: Callable[[Any], bool],
    parse_fragment: Callable[..., Any],
    source_format_id: str = "",
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]] = None,
    references: Optional[Iterable[Any]] = None,
    loaded_documents: Optional[Dict[Any, Any]] = None,
    used_short_ids: Optional[Sequence[Any]] = None,
    next_short_id: Optional[Callable[[], Any]] = None,
    generate_node_id: Optional[Callable[[], Any]] = None,
) -> UpdateOutcome:
    """Overwrite ``node``'s raw source text ({p011}). Always textual --
    unlike ``set_body`` there is no node/sequence form -- so this always
    preserves indentation and routes exactly once through
    ``reparse.reparse_edited_node``, exactly like ``set_body``'s text path
    (see :func:`_apply_text_and_reparse`)."""
    target = _resolve(document, node)
    if target is None:
        raise MutationError([ValidationError(code=ErrorCode.NODE_NOT_FOUND, message=f"node could not be resolved: {node!r}")])
    return _apply_text_and_reparse(
        document, target, fragment_text, source_format_id=source_format_id,
        admits_nested_structure=admits_nested_structure, parse_fragment=parse_fragment,
        is_type_compatible=is_type_compatible, references=references, loaded_documents=loaded_documents,
        used_short_ids=used_short_ids, next_short_id=next_short_id, generate_node_id=generate_node_id,
    )


def replace_node_id(
    document: Any, old_node_id: UUID, new_node_id: UUID, *, loaded_documents: Optional[Dict[Any, Any]] = None,
) -> AddressRemap:
    """Atomically rewrite a node's UUID4 ({p109}). Delegates the id-format
    validation and the ``nodes_by_id`` swap itself to
    ``identity.replace_node_id`` -- raising before any mutation on a
    malformed or colliding new id, exactly as that function already
    guarantees -- then rekeys ``document.short_id_index`` (only the
    node_id a short_id points at moves; the short_id itself never changes,
    per {p097}) and rewrites the ``references`` of every node in
    ``document`` and in each ``loaded_documents`` entry supplied, and only
    those; a document the caller did not pass here is left untouched by
    design."""
    remap = _identity_replace_node_id(document, old_node_id, new_node_id)
    short_index = getattr(document, "short_id_index", None)
    if isinstance(short_index, dict):
        for key, val in list(short_index.items()):
            if val == old_node_id:
                short_index[key] = new_node_id
    target_doc_id = getattr(document, "document_id", None)
    docs: Dict[Any, Any] = {target_doc_id: document}
    for doc_id, doc in (loaded_documents or {}).items():
        docs.setdefault(doc_id, doc)
    for doc_id, doc in docs.items():
        for candidate in (getattr(doc, "nodes_by_id", None) or {}).values():
            refs = getattr(candidate, "references", None)
            if not refs:
                continue
            updated = tuple(_retarget(addr, old_node_id, new_node_id, doc_id, target_doc_id) for addr in refs)
            if updated != tuple(refs):
                try:
                    candidate.references = updated
                except AttributeError:
                    pass
    return remap
