"""Controlled plain-text fallback: tree builder and metadata schema (concept C-013).

Scope: this module owns exactly the degraded-representation construction
path described by {p058}, {p060}, {p063}, {p096}, and {7a9b} -- nothing else.
It is entered only after a *resolved, known-or-explicit-format* plugin's
``parse_document`` has already failed with the classified
``ErrorCode.FORMAT_CONTENT_PARSE_FAILED`` ({p058}, {p063}); every other
failure code -- ``FORMAT_UNKNOWN_EXTENSION``, ``FORMAT_EXTENSION_CONFLICT``,
``FORMAT_PLUGIN_NOT_FOUND``, ``UNSUPPORTED_TRANSLATION``,
``FORMAT_PLUGIN_CONTRACT_ERROR``, or any other exception -- must reach the
caller unmasked, never silently opening a fallback tree in its place.

Module boundary: this file never invokes ``parse_document`` (or any other
plugin method) itself -- it only *consumes* a diagnostic a caller already
caught -- never touches a storage layer, performs no file I/O, no checksum
computation, and no atomic write (storage owns the tree-file write contract
per C-012), and imports no plain_text-plugin internals (the plain_text
plugin is a sibling module built independently and is not referenced here).

Lifecycle note ({7a9b}): building a fallback tree never returns a document
to its source format. This module defines no reparse/rebuild operation and
calls no plugin, so the only way back to ``source_format_id`` is a caller
explicitly invoking the source plugin's ``parse_document`` again elsewhere --
never an implicit side effect of anything in this file.

Source-of-truth requirement labels honored here: {p058}, {p060}, {p063},
{p088}, {p096}, {7a9b}.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, List, Mapping, Tuple, Union
from uuid import UUID

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Document, Node, NodeKind, make_node
from tree_engine.errors import ErrorCode

__all__ = [
    "PLAIN_TEXT_FORMAT_ID",
    "FallbackMetadata",
    "FallbackTree",
    "build_fallback_tree",
]

#: The fixed ``representation_format_id`` a fallback document always carries
#: ({p060}, {7a9b}). Never anything else -- there is no configurable
#: alternative degraded representation.
PLAIN_TEXT_FORMAT_ID = "plain_text"

_ROOT_KIND = NodeKind("plain_text:root")
_PARAGRAPH_KIND = NodeKind("plain_text:paragraph")


@dataclass(frozen=True)
class FallbackMetadata:
    """Fallback-document metadata schema ({p060}, {7a9b}).

    ``source_format_id`` is the originally selected/known format, preserved
    unchanged. ``representation_format_id`` is always
    :data:`PLAIN_TEXT_FORMAT_ID` -- fixed, not caller-supplied, so no caller
    can construct a ``FallbackMetadata`` that claims some other degraded
    representation. ``fallback_reason`` is a human-readable explanation of
    why the fallback was built. ``diagnostic`` carries the structured
    ``FORMAT_CONTENT_PARSE_FAILED`` details (at minimum ``error_code`` and
    ``message``; ``plugin_id`` when the originating diagnostic exposed one),
    exactly as raised by the source plugin -- never summarized away.
    """

    source_format_id: str
    fallback_reason: str
    diagnostic: Mapping[str, Any]
    representation_format_id: str = PLAIN_TEXT_FORMAT_ID

    def __post_init__(self) -> None:
        if not isinstance(self.source_format_id, str) or not self.source_format_id:
            raise ValueError(
                f"FallbackMetadata.source_format_id must be a non-empty string, "
                f"got {self.source_format_id!r}"
            )
        if self.representation_format_id != PLAIN_TEXT_FORMAT_ID:
            raise ValueError(
                "FallbackMetadata.representation_format_id must be "
                f"{PLAIN_TEXT_FORMAT_ID!r}, got {self.representation_format_id!r}"
            )
        object.__setattr__(self, "diagnostic", MappingProxyType(dict(self.diagnostic)))


@dataclass(frozen=True)
class FallbackTree:
    """The structured plain-text fallback tree ({p096}) plus its metadata.

    ``document`` is the common-model ``Document`` -- root plus format
    contract -- with ``representation_format_id`` set to ``plain_text`` and
    ``source_format_id`` left exactly as given ({7a9b}). ``paragraphs`` is
    the explicitly ordered dictionary required by {p096}: a plain ``dict``
    (insertion-order-preserving) keyed by each paragraph's canonical UUID4
    ``node_id``, whose values are the same paragraph ``Node`` objects also
    reachable as ``document.root.children``. ``order`` restates that same
    sequence of keys as an explicit tuple, so paragraph order is a directly
    inspectable value in its own right rather than something a caller must
    infer from dict-iteration behavior. ``metadata`` is the attached
    :class:`FallbackMetadata`.
    """

    document: Document
    paragraphs: Mapping[UUID, Node]
    order: Tuple[UUID, ...]
    metadata: FallbackMetadata


def build_fallback_tree(
    source_payload: Union[str, bytes],
    diagnostic: BaseException,
    *,
    source_format_id: str,
) -> FallbackTree:
    """Build the structured plain-text fallback tree for a parse failure.

    Gate ({p058}, {p063}): this function opens the fallback path *only* when
    ``diagnostic`` carries ``error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED``
    (read via a plain ``getattr`` -- no particular exception class is
    required, so any diagnostic shape a plugin raises is accepted as long as
    it exposes that attribute). For every other diagnostic -- a different
    ``error_code``, or none at all -- ``diagnostic`` is re-raised unchanged
    and no tree is built; this is the mechanism that keeps
    unknown-extension, extension-conflict, missing-plugin,
    incompatible-plugin, translator, and plugin-contract errors from ever
    being masked by a fallback.

    Construction ({p096}): ``source_payload`` (``str`` or raw ``bytes``,
    decoded as UTF-8 with lossless-effort replacement of any undecodable
    byte, since the payload is already known to be damaged) is split into
    paragraphs at blank-line boundaries. Each paragraph becomes a
    ``plain_text:paragraph`` ``Node`` carrying its text and structural
    metadata (``index``, the zero-based paragraph position, and
    ``line_start``, its 1-based starting line in the normalized payload) in
    ``fields``, and a fresh UUID4 ``node_id``. A ``plain_text:root`` ``Node``
    is built with those paragraph nodes as its ordered ``children`` --
    tuple order is the paragraph order -- and its own fresh ``node_id``. The
    returned ``document.source_format_id``/``representation_format_id`` are
    exactly as documented on :class:`FallbackTree`.
    """

    error_code, details = _extract_diagnostic(diagnostic)
    if error_code != ErrorCode.FORMAT_CONTENT_PARSE_FAILED:
        raise diagnostic

    text = _decode_payload(source_payload)
    paragraph_specs = _split_paragraphs(text)

    paragraphs: "dict[UUID, Node]" = {}
    order: List[UUID] = []
    for index, (paragraph_text, line_start) in enumerate(paragraph_specs):
        node_id, node = _build_paragraph_node(paragraph_text, index, line_start)
        paragraphs[node_id] = node
        order.append(node_id)

    root = _build_root_node(tuple(paragraphs[node_id] for node_id in order))
    document = Document(
        root=root,
        source_format_id=source_format_id,
        representation_format_id=PLAIN_TEXT_FORMAT_ID,
    )

    metadata = FallbackMetadata(
        source_format_id=source_format_id,
        fallback_reason=details.get("message", "") or ErrorCode.FORMAT_CONTENT_PARSE_FAILED.value,
        diagnostic=details,
    )

    return FallbackTree(
        document=document,
        paragraphs=MappingProxyType(paragraphs),
        order=tuple(order),
        metadata=metadata,
    )


def _extract_diagnostic(diagnostic: BaseException) -> Tuple[Any, Mapping[str, Any]]:
    """Read the classified error code and a plain details mapping off ``diagnostic``.

    Never raises on a malformed or foreign diagnostic shape: an absent
    ``error_code`` attribute simply reads as ``None``, which never equals
    :attr:`ErrorCode.FORMAT_CONTENT_PARSE_FAILED`, so callers with an
    unrelated exception type still get correct (non-fallback) propagation.
    """

    error_code = getattr(diagnostic, "error_code", None)
    details: dict = {
        "error_code": getattr(error_code, "value", error_code),
        "message": str(diagnostic),
    }
    plugin_id = getattr(diagnostic, "plugin_id", None)
    if plugin_id is not None:
        details["plugin_id"] = plugin_id
    return error_code, details


def _decode_payload(source_payload: Union[str, bytes]) -> str:
    """Normalize ``source_payload`` to ``str`` for paragraph splitting.

    ``bytes`` is decoded as UTF-8 with ``errors="replace"``: the payload is
    already known to be damaged content of a known format, so a decode
    failure here must not itself raise and abort fallback construction.
    """

    if isinstance(source_payload, bytes):
        return source_payload.decode("utf-8", errors="replace")
    return source_payload


def _split_paragraphs(text: str) -> List[Tuple[str, int]]:
    """Split ``text`` into paragraphs at blank-line boundaries.

    Each returned entry is ``(paragraph_text, line_start)`` where
    ``line_start`` is the 1-based line number, in the newline-normalized
    text, of the paragraph's first line. Order is exactly the order
    paragraphs appear in ``text``. A payload with no non-blank content
    yields an empty list -- zero paragraphs is a valid (if degenerate)
    fallback tree.
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    paragraphs: List[Tuple[str, int]] = []
    current: List[str] = []
    start_line = 1
    for line_number, line in enumerate(lines, start=1):
        if line.strip() == "":
            if current:
                paragraphs.append(("\n".join(current), start_line))
                current = []
            continue
        if not current:
            start_line = line_number
        current.append(line)
    if current:
        paragraphs.append(("\n".join(current), start_line))
    return paragraphs


def _build_paragraph_node(text: str, index: int, line_start: int) -> Tuple[UUID, Node]:
    """Build one ``plain_text:paragraph`` ``Node`` with a fresh UUID4 identity."""

    node = make_node(
        _PARAGRAPH_KIND,
        fields={"text": text, "index": index, "line_start": line_start},
    )
    node_id = generate_node_id()
    node = _with_node_id(node, node_id)
    return node_id, node


def _build_root_node(paragraph_nodes: Tuple[Node, ...]) -> Node:
    """Build the ``plain_text:root`` container over ``paragraph_nodes``, in order."""

    node = make_node(
        _ROOT_KIND,
        fields={"paragraph_count": len(paragraph_nodes)},
        children=paragraph_nodes,
    )
    return _with_node_id(node, generate_node_id())


def _with_node_id(node: Node, node_id: UUID) -> Node:
    """Attach ``node_id`` to an already-validated ``node``.

    ``Node`` is immutable and ``make_node`` has no ``node_id`` parameter, so
    per ``core/nodes.py``'s own documented pattern for sibling steps
    attaching an identity produced elsewhere, this constructs a new frozen
    instance carrying every already-validated field of ``node`` plus the
    identity -- it does not re-run field/children validation.
    """

    return Node(
        kind=node.kind,
        fields=node.fields,
        children=node.children,
        node_id=node_id,
        short_id=node.short_id,
        extended_type=node.extended_type,
        buffer_range=node.buffer_range,
        references=node.references,
    )
