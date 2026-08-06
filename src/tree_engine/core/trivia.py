"""Trivia, whitespace/comment, and format-attribute containers for C-002.

Scope (concept C-002, ``CommonTreeModel``, narrowed to the lossless
trivia/whitespace/comment layer and the extensible format-attribute
side-channel): this module defines ``TriviaKind``, ``TriviaPiece``,
``CommentPlacement``, ``CommentSlot``, ``Trivia``, ``FormatAttributes`` and
the ``NodeTriviaBinding`` attachment helper, per frozen HRS fragments
{p008} (the common model must be a structural superset of LibCST's
trivia/whitespace/comment/format-detail representation) and {p022}
(byte-for-byte preservation of unchanged text -- comments, blank lines,
whitespace, line endings, original formatting round-trip exactly; nothing
here silently reformats anything).

Depends on the sibling core-node-schema module
(``src/tree_engine/core/nodes.py``) only for the ``Node`` type used in
annotations; per this step's contract that reference is ``TYPE_CHECKING``
-only so importing this module never triggers a runtime import of
``nodes.py`` (no hard import cycle). This module does not redefine
``Node``, a field type, or a child-sequence type -- ``nodes.py`` remains
the single base schema. It also does not itself carry ``NodeSchemaError``
(that type lives in ``nodes.py`` and, per the same TYPE_CHECKING-only
constraint, is not imported here either); ``TriviaError`` below mirrors
its shape -- an ``ErrorCode`` from the shared catalog plus a message --
without importing it, so every failure in this file still surfaces one of
the stable codes from ``src/tree_engine/errors.py`` rather than an ad hoc
string or a second, unrelated code taxonomy.

Implements exactly the four containers this step scopes:

1. ``TriviaKind`` + ``TriviaPiece`` -- one immutable, unnormalized raw
   source substring plus its kind (whitespace, newline, or comment).
2. ``CommentSlot`` -- classifies a comment ``TriviaPiece`` as leading,
   trailing, or inline relative to its owning node, bundling the
   immediately adjacent whitespace/newline pieces so ordering and
   adjacency -- and therefore exact reconstruction -- survive on their
   own, independent of whatever container later holds the slot.
3. ``Trivia`` -- ordered leading/trailing sequences of ``TriviaPiece``
   and/or ``CommentSlot`` attachable to a node, with a ``raw_text``
   property that concatenates back to the exact original bytes.
4. ``FormatAttributes`` -- a namespaced, mapping-like side-channel for
   arbitrary per-format detail attributes outside the base schema, keyed
   by plugin/format id, that never drops an unrecognized key on
   get/set/merge/copy.

``NodeTriviaBinding`` is the attachment point ``nodes.py`` reserves this
module: since ``Node`` declares no trivia/format-attribute field of its
own (by design -- see its module docstring), a binding pairs a ``Node``
with its optional ``Trivia`` and ``FormatAttributes`` as an external,
copyable side table entry, without touching the base schema.

Non-goals, explicitly out of scope for this artifact: parser/codegen
translation logic (format plugins own that), node identity/addressing,
and storage/persistence.

Source-of-truth requirement labels honored here: {p008}, {p022}.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from tree_engine.errors import ErrorCode

if TYPE_CHECKING:
    from tree_engine.core.nodes import Node

__all__ = [
    "TriviaError",
    "TriviaKind",
    "TriviaPiece",
    "CommentPlacement",
    "CommentSlot",
    "TriviaElement",
    "Trivia",
    "FormatAttributes",
    "NodeTriviaBinding",
]


class TriviaError(Exception):
    """Raised when trivia/format-attribute data violates this module's
    invariants (a malformed piece, an invalid comment classification, or
    a reconstruction mismatch).

    Always carries the originating ``ErrorCode`` from the shared catalog
    (``src/tree_engine/errors.py``) as ``self.code``, the same contract
    the sibling core schema's ``NodeSchemaError`` follows, so callers can
    branch on the stable code rather than parsing message text.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code


class TriviaKind(str, enum.Enum):
    """Kind of one raw trivia substring. A ``str`` enum so values compare
    and serialize like plain strings while staying a closed set."""

    WHITESPACE = "WHITESPACE"
    NEWLINE = "NEWLINE"
    COMMENT = "COMMENT"


@dataclass(frozen=True)
class TriviaPiece:
    """One immutable, unnormalized raw source substring plus its kind.

    ``text`` is stored exactly as it appeared in the source -- no
    trimming, case-folding, tab expansion, or newline-style
    canonicalization -- so concatenating a sequence of pieces always
    reproduces the original bytes, per {p022}. An empty string is a valid
    ``text`` (e.g. a zero-length placeholder piece).
    """

    kind: TriviaKind
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TriviaKind):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"TriviaPiece.kind must be a TriviaKind, got {type(self.kind).__name__}",
            )
        if not isinstance(self.text, str):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"TriviaPiece.text must be a str, got {type(self.text).__name__}",
            )


class CommentPlacement(str, enum.Enum):
    """Where a comment sits relative to the node it is attached to."""

    LEADING = "LEADING"
    TRAILING = "TRAILING"
    INLINE = "INLINE"


def _coerce_piece_tuple(name: str, value: Any) -> Tuple[TriviaPiece, ...]:
    if not isinstance(value, (tuple, list)):
        raise TriviaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"{name} must be an ordered sequence, got {type(value).__name__}",
        )
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, TriviaPiece):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"{name}[{index}] must be a TriviaPiece, got {type(item).__name__}",
            )
        if item.kind is TriviaKind.COMMENT:
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"{name}[{index}] must not itself be a COMMENT piece "
                "(comments nest only via CommentSlot.piece)",
            )
    return items


@dataclass(frozen=True)
class CommentSlot:
    """Classifies a comment ``TriviaPiece`` as leading, trailing, or
    inline relative to its owning node.

    ``leading_whitespace``/``trailing_whitespace`` bundle the
    whitespace/newline pieces immediately adjacent to the comment inside
    the slot itself, so a ``CommentSlot`` reconstructs its own exact
    original byte run through ``raw_text`` regardless of what sequence
    later holds it -- ordering and adjacency of the surrounding pieces
    survive with the classification rather than depending on external
    list position.
    """

    piece: TriviaPiece
    placement: CommentPlacement
    leading_whitespace: Tuple[TriviaPiece, ...] = field(default_factory=tuple)
    trailing_whitespace: Tuple[TriviaPiece, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.piece, TriviaPiece):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"CommentSlot.piece must be a TriviaPiece, got {type(self.piece).__name__}",
            )
        if self.piece.kind is not TriviaKind.COMMENT:
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"CommentSlot.piece must carry TriviaKind.COMMENT, got {self.piece.kind!r}",
            )
        if not isinstance(self.placement, CommentPlacement):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"CommentSlot.placement must be a CommentPlacement, got "
                f"{type(self.placement).__name__}",
            )
        object.__setattr__(
            self, "leading_whitespace",
            _coerce_piece_tuple("CommentSlot.leading_whitespace", self.leading_whitespace),
        )
        object.__setattr__(
            self, "trailing_whitespace",
            _coerce_piece_tuple("CommentSlot.trailing_whitespace", self.trailing_whitespace),
        )

    @property
    def raw_text(self) -> str:
        """Exact original byte run this slot covers: adjacent leading
        whitespace, then the comment itself, then adjacent trailing
        whitespace -- byte-for-byte, no normalization."""
        leading = "".join(p.text for p in self.leading_whitespace)
        trailing = "".join(p.text for p in self.trailing_whitespace)
        return f"{leading}{self.piece.text}{trailing}"


TriviaElement = Union[TriviaPiece, CommentSlot]


def _coerce_element_tuple(name: str, value: Any) -> Tuple[TriviaElement, ...]:
    if not isinstance(value, (tuple, list)):
        raise TriviaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"{name} must be an ordered sequence, got {type(value).__name__}",
        )
    items = tuple(value)
    for index, item in enumerate(items):
        if not isinstance(item, (TriviaPiece, CommentSlot)):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"{name}[{index}] must be a TriviaPiece or CommentSlot, got "
                f"{type(item).__name__}",
            )
    return items


def _render(elements: Tuple[TriviaElement, ...]) -> str:
    parts = []
    for element in elements:
        parts.append(element.text if isinstance(element, TriviaPiece) else element.raw_text)
    return "".join(parts)


@dataclass(frozen=True)
class Trivia:
    """Ordered leading and trailing trivia attachable to a ``Node``.

    ``leading`` is the trivia that precedes the owning node (blank lines,
    indentation, standalone comments); ``trailing`` is the trivia that
    follows it on the way to the next token (inline/trailing comments,
    the line's newline). Each entry is either a plain ``TriviaPiece`` or a
    ``CommentSlot``. ``raw_text`` concatenates every element of
    ``leading`` then every element of ``trailing``, in order, reproducing
    the exact original surrounding bytes with no trimming or
    normalization, per {p022}.
    """

    leading: Tuple[TriviaElement, ...] = field(default_factory=tuple)
    trailing: Tuple[TriviaElement, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "leading", _coerce_element_tuple("Trivia.leading", self.leading))
        object.__setattr__(self, "trailing", _coerce_element_tuple("Trivia.trailing", self.trailing))

    @property
    def leading_text(self) -> str:
        return _render(self.leading)

    @property
    def trailing_text(self) -> str:
        return _render(self.trailing)

    @property
    def raw_text(self) -> str:
        """Full original byte run this trivia covers: ``leading_text``
        followed by ``trailing_text``, byte-for-byte."""
        return self.leading_text + self.trailing_text


def _require_namespace_key(namespace: Any, key: Any) -> None:
    if not isinstance(namespace, str) or not namespace:
        raise TriviaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"FormatAttributes namespace must be a non-empty str, got {namespace!r}",
        )
    if not isinstance(key, str) or not key:
        raise TriviaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"FormatAttributes key must be a non-empty str, got {key!r}",
        )


@dataclass
class FormatAttributes:
    """Namespaced, mapping-like side-channel for per-format detail
    attributes not covered by the base node schema, keyed by plugin/format
    id (e.g. ``"python"``, ``"bsl"``), per {p008}.

    Every mutator (``set``/``merge``) returns a *new* ``FormatAttributes``
    rather than mutating in place, mirroring the rest of the common
    model's copy-on-write style; ``copy`` is still provided explicitly so
    a caller can snapshot one without going through a no-op mutation.
    Namespaces and keys this module has never heard of are carried
    through unchanged in every case -- nothing here filters, drops, or
    inspects key names.
    """

    _data: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        _require_namespace_key(namespace, key)
        return self._data.get(namespace, {}).get(key, default)

    def set(self, namespace: str, key: str, value: Any) -> "FormatAttributes":
        _require_namespace_key(namespace, key)
        new_data = {ns: dict(attrs) for ns, attrs in self._data.items()}
        new_data.setdefault(namespace, {})[key] = value
        return FormatAttributes(new_data)

    def namespaces(self) -> Tuple[str, ...]:
        return tuple(self._data.keys())

    def items(self, namespace: str) -> Tuple[Tuple[str, Any], ...]:
        return tuple(self._data.get(namespace, {}).items())

    def merge(self, other: "FormatAttributes") -> "FormatAttributes":
        """Combine ``self`` with ``other``, namespace by namespace. On a
        key collision within a namespace, ``other`` wins; every
        non-colliding key from both sides -- known or unknown -- survives.
        """
        if not isinstance(other, FormatAttributes):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"FormatAttributes.merge expects a FormatAttributes, got {type(other).__name__}",
            )
        merged = {ns: dict(attrs) for ns, attrs in self._data.items()}
        for namespace, attrs in other._data.items():
            merged.setdefault(namespace, {}).update(attrs)
        return FormatAttributes(merged)

    def copy(self) -> "FormatAttributes":
        return FormatAttributes({ns: dict(attrs) for ns, attrs in self._data.items()})

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """A plain, independent snapshot: mutating the result never
        affects this ``FormatAttributes``."""
        return {ns: dict(attrs) for ns, attrs in self._data.items()}


@dataclass(frozen=True)
class NodeTriviaBinding:
    """Pairs an immutable ``Node`` with its optional ``Trivia`` and
    ``FormatAttributes`` side channels.

    ``nodes.py`` reserves no dedicated trivia/format-attribute field on
    ``Node`` itself (by design, so this module can attach such data "via
    a dedicated field, a side table, or a subclass" without renegotiating
    the base schema); a binding is that side-table entry, copyable as one
    unit. ``node`` is never validated as a ``Node`` instance here (only
    referenced under ``TYPE_CHECKING`` per this step's import contract),
    so callers may bind trivia to any node-shaped object that later
    proves compatible with the sibling schema.
    """

    node: "Node"
    trivia: Optional[Trivia] = None
    format_attributes: Optional[FormatAttributes] = None

    def __post_init__(self) -> None:
        if self.trivia is not None and not isinstance(self.trivia, Trivia):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"NodeTriviaBinding.trivia must be a Trivia or None, got {type(self.trivia).__name__}",
            )
        if self.format_attributes is not None and not isinstance(self.format_attributes, FormatAttributes):
            raise TriviaError(
                ErrorCode.INVALID_PARENT_TYPE,
                "NodeTriviaBinding.format_attributes must be a FormatAttributes or None, "
                f"got {type(self.format_attributes).__name__}",
            )

    def copy(self) -> "NodeTriviaBinding":
        """Copy this binding for the same ``node``: ``trivia`` is reused
        as-is (it is itself immutable), while ``format_attributes`` -- if
        present -- is snapshotted via its own ``copy`` so every namespaced
        key, known or unknown, survives independently of the original."""
        fa = self.format_attributes.copy() if self.format_attributes is not None else None
        return NodeTriviaBinding(node=self.node, trivia=self.trivia, format_attributes=fa)

    def with_trivia(self, trivia: Trivia) -> "NodeTriviaBinding":
        return NodeTriviaBinding(node=self.node, trivia=trivia, format_attributes=self.format_attributes)

    def with_format_attributes(self, format_attributes: FormatAttributes) -> "NodeTriviaBinding":
        return NodeTriviaBinding(node=self.node, trivia=self.trivia, format_attributes=format_attributes)
