"""Read-only ``drill_down`` inspection operation for concept C-018 (TreeInspection).

Scope ({p064}-{p071}): one public entry point, :func:`drill_down`, plus the
two exceptions it raises, :class:`NodeNotFoundError` and
:class:`DocumentVersionConflictError`. Turns an already loaded common-model
``Document`` into a compact ``model_outline`` response built exclusively
through the already-merged :mod:`tree_engine.query.outline` model -- this
file never redefines ``OutlineMeta``/``OutlineNodeRecord``/``OutlineStubRecord``/
``OutlineTruncation``/``OutlineResponse``, only assembles values via
``build_outline_response``. Selector/query-language parsing is entirely out
of scope (sibling TreeQueryEngine step).

Address resolution is delegated whole to the already-merged
``normalize_node_address``; this file only translates its
``NodeAddressError`` family into the dedicated, catalog-coded exception this
step requires. Depth control and ``expand_below_bytes`` auto-expansion
consume the already-merged ``subtree_bytes`` aggregate
(``tree_engine.core.positions.SubtreeBytesAggregate``) through one
duck-typed accessor, ``document.subtree_bytes_for(node_id)`` -- never by
re-serializing a subtree; a missing accessor reads back ``None`` for every
node, the safe "skip auto-expansion" case.

Read-only guarantee ({p064}): no helper below ever assigns to a ``Node``/
``Document`` attribute, a short_id map, a position index, or
``document_version`` -- only reads. Source text (``include_source``) comes
from ``document.source_for(node)`` if supplied, else from slicing
``document.buffer`` at ``node.buffer_range`` via its public ``iter_regions()``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, List, Mapping, Optional, Tuple, Union
from uuid import UUID

from tree_engine.core.address import (
    NodeAddressError,
    NodeAddressView,
    build_node_address_view,
    normalize_node_address,
)
from tree_engine.core.identity import NodeAddress
from tree_engine.core.nodes import Node, walk
from tree_engine.errors import ErrorCode
from tree_engine.query.outline import (
    OutlineMeta,
    OutlineNodeRecord,
    OutlineResponse,
    OutlineStubRecord,
    OutlineTruncation,
    TruncatedField,
    build_outline_response,
)

__all__ = [
    "SOURCE_NONE",
    "SOURCE_PREVIEW",
    "SOURCE_FULL",
    "NodeNotFoundError",
    "DocumentVersionConflictError",
    "drill_down",
]

SOURCE_NONE = "none"
SOURCE_PREVIEW = "preview"
SOURCE_FULL = "full"
_VALID_SOURCE_MODES = (SOURCE_NONE, SOURCE_PREVIEW, SOURCE_FULL)

_ABSENT = object()
_OutlineEntry = Union[OutlineNodeRecord, OutlineStubRecord]

class NodeNotFoundError(Exception):
    """``address`` did not resolve to a node of ``document`` ({p065}).

    Carries ``ErrorCode.NODE_NOT_FOUND`` as ``self.code``; never lets the
    lower-level ``NodeAddressError`` it wraps escape :func:`drill_down`."""
    def __init__(self, raw_address: Any) -> None:
        self.code = ErrorCode.NODE_NOT_FOUND
        self.raw_address = raw_address
        super().__init__(f"[{self.code.value}] unknown node address: {raw_address!r}")

class DocumentVersionConflictError(Exception):
    """``expected_version`` did not match the document's current version.

    Carries ``ErrorCode.DOCUMENT_VERSION_CONFLICT`` as ``self.code`` ({p065});
    raised before any node is read."""
    def __init__(self, expected_version: Any, current_version: Any) -> None:
        self.code = ErrorCode.DOCUMENT_VERSION_CONFLICT
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"[{self.code.value}] expected_version {expected_version!r} does not "
            f"match current document_version {current_version!r}"
        )

def _current_version(document: Any) -> Any:
    current = getattr(document, "document_version", _ABSENT)
    if current is _ABSENT:
        current = getattr(document, "version", None)
    return current

def _check_expected_version(document: Any, expected_version: Any) -> None:
    if expected_version is None:
        return
    current = _current_version(document)
    if current != expected_version:
        raise DocumentVersionConflictError(expected_version, current)

def _subtree_bytes_for(document: Any, node_id: Any) -> Optional[int]:
    accessor = getattr(document, "subtree_bytes_for", None)
    return None if accessor is None else accessor(node_id)

def _slice_buffer_bytes(buffer: Any, start: int, end: int) -> bytes:
    """Read-only ``[start, end)`` slice via the public ``iter_regions()`` only."""
    chunks: List[bytes] = []
    offset = 0
    for _is_original, chunk in buffer.iter_regions():
        chunk_start, chunk_end = offset, offset + len(chunk)
        offset = chunk_end
        if chunk_end <= start:
            continue
        if chunk_start >= end:
            break
        chunks.append(chunk[max(start, chunk_start) - chunk_start : min(end, chunk_end) - chunk_start])
    return b"".join(chunks)

def _source_for(document: Any, node: Node) -> Optional[str]:
    accessor = getattr(document, "source_for", None)
    if accessor is not None:
        return accessor(node)
    buffer_range = getattr(node, "buffer_range", None)
    buffer = getattr(document, "buffer", None)
    if buffer_range is None or buffer is None:
        return None
    start, end = buffer_range
    try:
        raw = _slice_buffer_bytes(buffer, start, end)
    except Exception:
        return None
    return raw.decode("utf-8", "replace")

def _name_or_value(node: Node) -> str:
    for key in ("name", "value"):
        candidate = node.fields.get(key)
        if isinstance(candidate, str):
            return candidate
    return ""

def _select_attributes(node: Node) -> Mapping[str, Any]:
    return {
        key: value
        for key, value in node.fields.items()
        if value is None or isinstance(value, (str, int, float, bool, bytes))
    }

def _source_preview(document: Any, node: Node, include_source: str, source_preview_bytes: int) -> Optional[TruncatedField]:
    if include_source == SOURCE_NONE:
        return None
    text = _source_for(document, node)
    if text is None:
        return TruncatedField(value="", field_truncated=False, original_field_bytes=None)
    if include_source == SOURCE_FULL:
        return TruncatedField(value=text, field_truncated=False, original_field_bytes=None)
    raw = text.encode("utf-8")
    if len(raw) <= source_preview_bytes:
        return TruncatedField(value=text, field_truncated=False, original_field_bytes=None)
    trimmed = raw[:source_preview_bytes].decode("utf-8", "ignore")
    return TruncatedField(value=trimmed, field_truncated=True, original_field_bytes=len(raw))

def _build_stub(node: Node, subtree_bytes: Optional[int]) -> OutlineStubRecord:
    view = build_node_address_view(node.node_id, node.short_id)
    return OutlineStubRecord(
        node_id=view.node_id, short_id_hex=view.short_id_hex, type=str(node.kind),
        child_count=len(node.children), subtree_node_count=sum(1 for _ in walk(node)),
        subtree_bytes=subtree_bytes,
    )

@dataclass(frozen=True)
class _Ctx:
    document: Any
    requested_depth: int
    expand_below_bytes: int
    include_attributes: bool
    include_source: str
    source_preview_bytes: int

def _walk(
    ctx: _Ctx, node: Node, parent_view: Optional[NodeAddressView], child_index: int,
    depth_from_view: int, blanket_auto: bool, emit: bool, entries: List[_OutlineEntry],
) -> None:
    """Depth-first preorder traversal, appending records/stubs to ``entries``.

    ``blanket_auto`` True means an ancestor already triggered unconditional
    full expansion ({p067}): every node reached this way is shown in full
    and marked ``auto_expanded``, no further check. Otherwise, within
    ``ctx.requested_depth`` children are shown normally ({p066}); once that
    depth is reached, each child is gated by its *own* aggregate -- fully
    revealed (entering blanket mode) or collapsed into a stub ({p067})."""
    view = build_node_address_view(node.node_id, node.short_id)
    if emit:
        agg = _subtree_bytes_for(ctx.document, node.node_id)
        record = OutlineNodeRecord(
            node_id=view.node_id, short_id_hex=view.short_id_hex, depth=depth_from_view,
            parent_id=parent_view.node_id if parent_view else None,
            parent_short_id_hex=parent_view.short_id_hex if parent_view else None,
            child_index=child_index, type=str(node.kind), name_or_value=_name_or_value(node),
            attributes=_select_attributes(node) if ctx.include_attributes else None,
            child_count=len(node.children), shown_child_count=len(node.children), subtree_bytes=agg,
            source_preview=_source_preview(ctx.document, node, ctx.include_source, ctx.source_preview_bytes),
            expanded=blanket_auto or depth_from_view < ctx.requested_depth,
            auto_expanded=blanket_auto, truncated=False,
        )
        entries.append(record)
        this_view = record.address
    else:
        this_view = view

    if blanket_auto or depth_from_view < ctx.requested_depth:
        for index, child in enumerate(node.children):
            _walk(ctx, child, this_view, index, depth_from_view + 1, blanket_auto, True, entries)
        return

    for index, child in enumerate(node.children):
        child_agg = _subtree_bytes_for(ctx.document, child.node_id)
        auto_ok = child_agg is not None and ctx.expand_below_bytes != 0 and child_agg <= ctx.expand_below_bytes
        if auto_ok:
            _walk(ctx, child, this_view, index, depth_from_view + 1, True, True, entries)
        else:
            entries.append(_build_stub(child, child_agg))

def _payload_bytes(payload: Any) -> int:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))

def _entry_bytes(entry: _OutlineEntry) -> int:
    """Approximate per-entry cost, used only for the shrink heuristic below.
    The ceiling decision itself never trusts a sum of these -- it always
    re-measures the real assembled response (see ``_assemble``)."""
    return _payload_bytes(entry)

def _mandatory_entry_bytes(entry: _OutlineEntry) -> int:
    if isinstance(entry, OutlineStubRecord):
        return _entry_bytes(entry)
    return _entry_bytes(replace(entry, attributes=None, source_preview=None))

def _shrink_entry(entry: OutlineNodeRecord, budget: int) -> OutlineNodeRecord:
    """Truncate oversized optional fields to fit ``budget`` bytes ({p069}):
    mandatory fields stay intact; only ``source_preview`` (then, as a last
    resort, ``attributes``) is cut, marked ``field_truncated`` with size."""
    budget = max(budget, 0)
    preview = entry.source_preview
    if preview is not None and preview.value:
        raw = preview.value.encode("utf-8")
        original = preview.original_field_bytes if preview.field_truncated else len(raw)
        kept = raw[: max(budget - 32, 0)]
        preview = TruncatedField(value=kept.decode("utf-8", "ignore"), field_truncated=True, original_field_bytes=original)
        entry = replace(entry, source_preview=preview, truncated=True)
    if entry.attributes and _entry_bytes(entry) - _mandatory_entry_bytes(entry) > budget:
        entry = replace(entry, attributes={}, truncated=True)
    return entry

def _truncation_for(entries: List[_OutlineEntry], kept_count: int, viewed: NodeAddressView) -> OutlineTruncation:
    remainder = entries[kept_count:]
    if not remainder:
        return OutlineTruncation(truncated=False, omitted_nodes=0, omitted_bytes=0, continuation=None)
    omitted_bytes = sum(_entry_bytes(e) for e in remainder)
    return OutlineTruncation(
        truncated=True, omitted_nodes=len(remainder), omitted_bytes=omitted_bytes, continuation=remainder[0].address
    )

def _assemble(
    kept: List[_OutlineEntry], truncation: OutlineTruncation, viewed: NodeAddressView,
    depth: int, expand_below_bytes: int, version: Any,
) -> Tuple[int, OutlineMeta]:
    """The response's real, exact serialized size for a candidate ``kept``/
    ``truncation`` pair -- built and measured the same way a caller actually
    receives it (``build_outline_response`` then ``_payload_bytes`` on the
    real object), not estimated. ``response_bytes`` is self-referential (the
    field reports the size of the response that contains it); this resolves
    it by fixed point, which converges in a couple of steps since the digit
    width of a byte count only changes at a power-of-ten boundary."""
    response_bytes = 0
    meta = OutlineMeta(
        viewed=viewed, depth=depth, expand_below_bytes=expand_below_bytes,
        document_version=version, node_count=len(kept), response_bytes=response_bytes,
    )
    for _ in range(6):
        size = _payload_bytes(build_outline_response(meta, kept, truncation))
        if size == response_bytes:
            return size, meta
        response_bytes = size
        meta = replace(meta, response_bytes=response_bytes)
    return response_bytes, meta

def _fits(
    kept: List[_OutlineEntry], truncation: OutlineTruncation, viewed: NodeAddressView,
    depth: int, expand_below_bytes: int, version: Any, max_output_bytes: int,
) -> bool:
    size, _ = _assemble(kept, truncation, viewed, depth, expand_below_bytes, version)
    return size <= max_output_bytes

def _apply_ceiling(
    entries: List[_OutlineEntry], max_output_bytes: int, viewed: NodeAddressView, depth: int, expand_below_bytes: int, version: Any
) -> Tuple[List[_OutlineEntry], OutlineTruncation]:
    """Pick the largest prefix of ``entries`` whose real, exactly measured
    response fits ``max_output_bytes`` ({p069}). A binary search over the
    prefix length keeps this to O(log n) real (not estimated) measurements
    for the common case; response size is non-decreasing in prefix length
    for any realistic content, so the search is sound, and every candidate
    it accepts is verified against the exact size a caller would see -- no
    breach can hide behind an approximation. One shrink attempt on the
    first excluded entry avoids wasting a large leftover budget on a bare
    cutoff ({p069}); a final linear safety net re-verifies (and, if needed,
    trims) the exact size, so the ceiling holds even if that shrink guess
    was too optimistic."""
    n = len(entries)
    lo, hi, fit_k = 0, n, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        truncation = _truncation_for(entries, mid, viewed)
        if _fits(entries[:mid], truncation, viewed, depth, expand_below_bytes, version, max_output_bytes):
            fit_k, lo = mid, mid + 1
        else:
            hi = mid - 1

    kept: List[_OutlineEntry] = list(entries[:fit_k])
    truncation = _truncation_for(entries, fit_k, viewed)

    if fit_k < n and not isinstance(entries[fit_k], OutlineStubRecord):
        trial_truncation = _truncation_for(entries, fit_k + 1, viewed)
        used, _ = _assemble(kept, trial_truncation, viewed, depth, expand_below_bytes, version)
        mandatory = _mandatory_entry_bytes(entries[fit_k])
        if used + mandatory <= max_output_bytes:
            shrunk = _shrink_entry(entries[fit_k], max_output_bytes - used - mandatory)
            if _fits(kept + [shrunk], trial_truncation, viewed, depth, expand_below_bytes, version, max_output_bytes):
                kept.append(shrunk)
                truncation = trial_truncation

    while kept and not _fits(kept, truncation, viewed, depth, expand_below_bytes, version, max_output_bytes):
        kept.pop()
        truncation = _truncation_for(entries, len(kept), viewed)

    return kept, truncation

def drill_down(
    document: Any,
    address: Optional[Union[UUID, int, str, NodeAddress]] = None,
    *,
    depth: int = 1,
    expand_below_bytes: int = 8192,
    expected_version: Optional[Any] = None,
    include_self: bool = True,
    include_attributes: bool = True,
    include_source: str = SOURCE_PREVIEW,
    source_preview_bytes: int = 256,
    max_output_bytes: int = 65536,
) -> OutlineResponse:
    """Read-only compact-view inspection of ``document`` around ``address``.

    Per {p064}: never mutates the tree, an index, ``document_version``, or
    format-plugin state. ``expected_version``, when given, is checked first
    -- before any node is read -- raising :class:`DocumentVersionConflictError`
    on a mismatch ({p065}). ``address`` defaults to the root; otherwise
    resolved via ``normalize_node_address`` (int/hex short_id or UUID4),
    with an unresolvable address raised as :class:`NodeNotFoundError`. The
    remaining parameters behave exactly as {p066}-{p069} specify; the
    response is the compact ``model_outline`` shape from
    ``build_outline_response`` ({p070}, {p071})."""
    if include_source not in _VALID_SOURCE_MODES:
        raise ValueError(f"include_source must be one of {_VALID_SOURCE_MODES}, got {include_source!r}")

    _check_expected_version(document, expected_version)
    version = _current_version(document)

    if address is None:
        viewed_node = document.root
    else:
        current_document_id = getattr(document, "document_id", None)
        try:
            viewed_id = normalize_node_address(document, address, current_document_id=current_document_id)
        except NodeAddressError as exc:
            raise NodeNotFoundError(address) from exc
        viewed_node = document.nodes_by_id[viewed_id]

    depth = max(int(depth), 0)
    ctx = _Ctx(
        document=document, requested_depth=depth, expand_below_bytes=expand_below_bytes,
        include_attributes=include_attributes, include_source=include_source, source_preview_bytes=source_preview_bytes,
    )
    entries: List[_OutlineEntry] = []
    _walk(ctx, viewed_node, None, 0, 0, False, include_self, entries)

    viewed_view = build_node_address_view(viewed_node.node_id, viewed_node.short_id)
    kept, truncation = _apply_ceiling(entries, max_output_bytes, viewed_view, depth, expand_below_bytes, version)
    _, meta = _assemble(kept, truncation, viewed_view, depth, expand_below_bytes, version)

    return build_outline_response(meta, kept, truncation)
