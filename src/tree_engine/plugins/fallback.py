"""Controlled plain-text fallback: tree builder and metadata schema (concept C-013).

Scope: this module owns exactly the degraded-representation construction
path described by {p058}, {p060}, {p063}, {p096}, and {7a9b} -- nothing
else. It is entered only after a *resolved, known-or-explicit-format*
plugin's ``parse_document`` has failed with the classified
``ErrorCode.FORMAT_CONTENT_PARSE_FAILED`` ({p058}, {p063}); every other
failure -- ``FORMAT_UNKNOWN_EXTENSION``, ``FORMAT_EXTENSION_CONFLICT``,
``FORMAT_PLUGIN_NOT_FOUND``, ``UNSUPPORTED_TRANSLATION``,
``FORMAT_PLUGIN_CONTRACT_ERROR``, or any other exception -- must reach the
caller unmasked, never silently opening a fallback tree in its place.

Module boundary: this file never invokes ``parse_document`` (or any other
plugin method) -- it only *consumes* a diagnostic a caller already caught --
never touches a storage layer, and performs no file I/O, checksum, or
atomic write (storage owns the tree-file write contract per C-012). It
imports exactly one thing from the plain_text plugin, the public
:data:`~tree_engine.plugins.plain_text.VERBATIM_TEXT_FIELD` field name, so
the slice recorded on each paragraph is the one that renderer reads.

Byte fidelity ({p060}): a file its owning plugin cannot parse must still be
openable and savable without corruption, so rendering the fallback document
back out through the plain_text plugin reproduces the input bytes exactly,
for ANY input: CRLF, a BOM, a missing trailing newline, runs of blank
lines, and bytes that are not valid UTF-8 at all. Two mechanisms: ``bytes``
are decoded with ``errors="surrogateescape"`` (round-trip exact, unlike
``errors="replace"``), and every paragraph node records the verbatim source
slice it covers -- blank separators included -- next to its ``text``.

Lifecycle note ({7a9b}): building a fallback tree never returns a document
to its source format. This module defines no reparse/rebuild operation, so
the only way back to ``source_format_id`` is a caller explicitly invoking
the source plugin's ``parse_document`` again elsewhere.

Source-of-truth labels honored here: {p013}, {p023}, {p058}, {p060},
{p063}, {p088}, {p096}, {p097}, {7a9b}.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterator, List, Mapping, NamedTuple, Tuple, Union
from uuid import UUID

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Document, Node, NodeKind, make_node
from tree_engine.errors import ErrorCode
from tree_engine.plugins.plain_text import VERBATIM_TEXT_FIELD

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

#: Line terminators recognized when splitting paragraphs: exactly the three
#: real ones, never the extras ``str.splitlines`` also breaks on (``\x0b``,
#: ``\x0c``, ``\x1c``, ``\u2028``, ...), which would re-cut lines inside
#: content that legitimately contains them.
_LINE_BREAK = re.compile(r"\r\n|\r|\n")

#: Compact per-node ``short_id`` source ({p097}), shared by every node this
#: module builds, mirroring the plain_text plugin.
_short_id_counter = itertools.count(1)


class _Paragraph(NamedTuple):
    """One blank-line-delimited paragraph plus the bytes it stands for.

    ``text`` is the human-facing content: lines joined with ``\\n``, blank
    separators dropped, undecodable bytes shown as ``U+FFFD``.
    ``source_text`` is the verbatim slice covered -- own lines with original
    terminators, plus every blank line up to the next paragraph (and, for
    the first, every blank line before it) -- so concatenating them all in
    order reconstructs the payload exactly. ``line_start`` is the 1-based
    line number of the first content line.
    """

    text: str
    line_start: int
    source_text: str


@dataclass(frozen=True)
class FallbackMetadata:
    """Fallback-document metadata schema ({p060}, {7a9b}).

    ``source_format_id`` is the originally selected/known format, preserved
    unchanged. ``representation_format_id`` is always
    :data:`PLAIN_TEXT_FORMAT_ID` -- fixed, not caller-supplied, so no caller
    can claim some other degraded representation. ``fallback_reason``
    explains why the fallback was built. ``diagnostic`` carries the
    structured ``FORMAT_CONTENT_PARSE_FAILED`` details (at minimum
    ``error_code`` and ``message``; ``plugin_id`` when the originating
    diagnostic exposed one), exactly as raised -- never summarized away.
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
    the explicitly ordered dictionary required by {p096}: keyed by each
    paragraph's canonical UUID4 ``node_id``, its values are the same
    paragraph ``Node`` objects also reachable as ``document.root.children``.
    ``order`` restates that key sequence as an explicit tuple, so paragraph
    order is directly inspectable rather than inferred from dict iteration.
    ``metadata`` is the attached :class:`FallbackMetadata`.
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

    Gate ({p058}, {p063}): the fallback opens *only* for a diagnostic that
    classifies as ``FORMAT_CONTENT_PARSE_FAILED``. Two exception conventions
    coexist in this codebase and BOTH are honored, in this order: the
    canonical typed hierarchy of :mod:`tree_engine.exceptions`, exposing the
    code as ``code`` and marking its single fallback-permitting class with
    ``plain_text_fallback_permitted``; and the older exceptions of
    :mod:`tree_engine.plugins.contract`, exposing it as ``error_code``. Both
    are read with a plain ``getattr``, so no particular exception class is
    required. For every other diagnostic -- a different code, or none at all
    -- ``diagnostic`` is re-raised unchanged and no tree is built; that is
    what keeps unknown-extension, extension-conflict, missing-plugin,
    incompatible-plugin, translator, and plugin-contract errors from ever
    being masked by a fallback.

    Construction ({p096}): ``source_payload`` (``str``, or raw ``bytes``
    decoded as UTF-8 with ``errors="surrogateescape"``) is split into
    paragraphs at blank-line boundaries. Each becomes a
    ``plain_text:paragraph`` ``Node`` whose ``fields`` carry ``text`` (the
    human-facing content), ``index`` (zero-based position), ``line_start``
    (1-based starting line), and ``source_text`` (the verbatim payload slice
    it covers); a ``plain_text:root`` ``Node`` holds them as its ordered
    ``children``. Every node gets a fresh UUID4 ``node_id`` and a positive
    ``short_id`` ({p013}, {p097}), and the returned ``document``'s format
    ids are exactly as documented on :class:`FallbackTree`. Because the
    ``source_text`` slices tile the payload exactly, rendering that document
    through the plain_text plugin reproduces the original bytes.
    """

    error_code, details = _extract_diagnostic(diagnostic)
    if not _fallback_permitted(diagnostic, error_code):
        raise diagnostic

    text = _decode_payload(source_payload)

    paragraphs: "dict[UUID, Node]" = {}
    order: List[UUID] = []
    for index, paragraph in enumerate(_split_paragraphs(text)):
        node_id, node = _build_paragraph_node(paragraph, index)
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

    Never raises on a malformed or foreign diagnostic shape: an absent code
    reads as ``None``, which never equals
    :attr:`ErrorCode.FORMAT_CONTENT_PARSE_FAILED`, so an unrelated exception
    propagates instead of opening a fallback. ``plugin_id`` comes from the
    older exceptions' attribute or the typed hierarchy's ``details``.
    """

    error_code = _classified_error_code(diagnostic)
    details: dict = {
        "error_code": getattr(error_code, "value", error_code),
        "message": str(diagnostic),
    }
    plugin_id = getattr(diagnostic, "plugin_id", None)
    if plugin_id is None:
        carried = getattr(diagnostic, "details", None)
        if isinstance(carried, Mapping):
            plugin_id = carried.get("plugin_id")
    if plugin_id is not None:
        details["plugin_id"] = plugin_id
    return error_code, details


def _classified_error_code(diagnostic: BaseException) -> Any:
    """Return the :class:`ErrorCode` ``diagnostic`` classifies as, if any.

    Prefers the typed hierarchy's ``code`` over the contract exceptions'
    ``error_code``. An attribute holding a non-``ErrorCode`` -- a foreign
    exception that happens to own a ``code``, e.g. ``SystemExit`` -- is
    never mistaken for a classification, but is still returned when no real
    code is present so the details report what the object carried.
    """

    typed = getattr(diagnostic, "code", None)
    if isinstance(typed, ErrorCode):
        return typed
    legacy = getattr(diagnostic, "error_code", None)
    if isinstance(legacy, ErrorCode):
        return legacy
    return typed if legacy is None else legacy


def _fallback_permitted(diagnostic: BaseException, error_code: Any) -> bool:
    """Decide whether ``diagnostic`` may open the plain-text fallback.

    True for the typed hierarchy's single fallback-permitting class, which
    advertises ``plain_text_fallback_permitted = True`` ({p023}), and for
    any diagnostic classified ``FORMAT_CONTENT_PARSE_FAILED`` -- how the
    older contract exceptions, carrying no such flag, reach this path.
    """

    if getattr(diagnostic, "plain_text_fallback_permitted", False) is True:
        return True
    return error_code == ErrorCode.FORMAT_CONTENT_PARSE_FAILED


def _decode_payload(source_payload: Union[str, bytes]) -> str:
    """Normalize ``source_payload`` to ``str`` for paragraph splitting.

    ``bytes`` is decoded as UTF-8 with ``errors="surrogateescape"``: a
    decode failure must not abort fallback construction, and -- unlike
    ``errors="replace"`` -- every undecodable byte is preserved as a lone
    surrogate that re-encodes to exactly itself, so the fallback cannot
    corrupt the latin-1 or binary file it was invoked to rescue.
    """

    if isinstance(source_payload, (bytes, bytearray)):
        return bytes(source_payload).decode("utf-8", errors="surrogateescape")
    return source_payload


def _display_text(text: str) -> str:
    """Render ``text`` for human reading: every surrogateescaped byte -- one
    the payload could not decode as UTF-8 -- becomes ``U+FFFD``. Lossy by
    design; the bytes stay on the node's ``source_text`` field."""

    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


def _iter_lines(text: str) -> Iterator[Tuple[str, str]]:
    """Yield ``(content, terminator)`` per line of ``text``, terminator kept
    verbatim (``""`` for a final unterminated line), so concatenating every
    ``content + terminator`` reproduces ``text``."""

    position = 0
    while position < len(text):
        match = _LINE_BREAK.search(text, position)
        if match is None:
            yield text[position:], ""
            return
        yield text[position:match.start()], match.group(0)
        position = match.end()


def _split_paragraphs(text: str) -> List[_Paragraph]:
    """Split ``text`` into paragraphs at blank-line boundaries.

    Order is the order paragraphs appear in ``text``, and their
    ``source_text`` slices tile ``text`` exactly: blank lines attach to the
    preceding paragraph (or, before the first one, to the following one),
    never dropped. A payload with no non-blank content at all yields one
    paragraph with empty ``text`` and the whole payload as ``source_text``
    -- something must carry that blank material for the render to stay
    byte-exact; a genuinely empty payload yields no paragraphs.
    """

    records: List[Tuple[List[str], List[str], int]] = []
    leading: List[str] = []
    open_paragraph = False
    for number, (content, terminator) in enumerate(_iter_lines(text), start=1):
        raw = content + terminator
        if content.strip() == "":
            open_paragraph = False
            (records[-1][1] if records else leading).append(raw)
            continue
        if not open_paragraph:
            # First paragraph adopts the leading blank lines; later ones not.
            records.append(([], leading if not records else [], number))
            open_paragraph = True
        records[-1][0].append(content)
        records[-1][1].append(raw)

    if not records:
        return [_Paragraph("", 1, "".join(leading))] if leading else []
    return [
        _Paragraph(_display_text("\n".join(lines)), line_start, "".join(source))
        for lines, source, line_start in records
    ]


def _build_paragraph_node(paragraph: _Paragraph, index: int) -> Tuple[UUID, Node]:
    """Build one ``plain_text:paragraph`` ``Node`` with a fresh UUID4 identity."""

    node = make_node(
        _PARAGRAPH_KIND,
        fields={
            "text": paragraph.text, "index": index,
            "line_start": paragraph.line_start,
            VERBATIM_TEXT_FIELD: paragraph.source_text,
        },
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
    """Attach ``node_id`` plus a fresh positive ``short_id`` to an
    already-validated ``node``.

    ``Node`` is immutable and ``make_node`` has no ``node_id`` parameter, so
    per ``core/nodes.py``'s own documented pattern for attaching an identity
    produced elsewhere, this constructs a new frozen instance carrying every
    already-validated field plus the identity, re-running no validation. The
    ``short_id`` ({p097}) comes from this module's shared counter: without
    one the query engine cannot address a fallback node at all.
    """

    return Node(
        kind=node.kind,
        fields=node.fields,
        children=node.children,
        node_id=node_id,
        short_id=next(_short_id_counter),
        extended_type=node.extended_type,
        buffer_range=node.buffer_range,
        references=node.references,
    )
