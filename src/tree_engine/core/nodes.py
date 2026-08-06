"""Base node schema and document format contract for concept C-002.

Scope (concept C-002, CommonTreeModel, narrowed to the base node schema and
the document-level format contract): this module defines ``NodeKind``,
``Node``, and ``Document`` -- the core's only working tree representation,
per frozen HRS fragments {p008} and {p045} -- plus the ``make_node``
construction primitive and the ``iter_children``/``walk`` traversal
primitives.

Per {p045}, the core works only with this common model: it never imports,
subclasses, or otherwise depends on LibCST (or any other external
parser/codegen library) as a working type. Format plugins are the only code
allowed to touch such external libraries, and they translate between their
own representation and this common model at their call boundary. Nothing in
this file imports a format plugin, and nothing here performs storage,
persistence, or public-facade work.

Design notes for sibling steps:

* ``Node`` carries five reserved, inert extension-point attributes --
  ``node_id``, ``short_id``, ``extended_type``, ``buffer_range``, and
  ``references`` -- and ``Document`` carries a reserved ``document_id``.
  All default to ``None`` (or an empty tuple for ``references``) and are
  never read or assigned anywhere else in this file. They exist purely so
  the sibling identity (node_id/short_id), extended-node-type, buffer-range,
  and reference-integrity steps have a stable place to attach their own
  behavior without renegotiating this schema.
* Neither ``Node`` nor ``Document`` declares ``__slots__``, and ``fields``
  is an open ``str``-keyed mapping. This deliberately leaves room for the
  sibling ``trivia.py`` module to attach trivia/whitespace/comment data
  later (via a dedicated field, a side table, or a subclass) without this
  file precluding that; no trivia/comment/whitespace storage is defined
  here.
* Per requirement (7) of this step, no ad hoc exception/error-string
  taxonomy is invented for malformed construction. All validation failures
  raise ``NodeSchemaError``, which always carries an ``ErrorCode`` from the
  shared catalog in ``src/tree_engine/errors.py``. Every failure in this
  file is a shape/type mismatch between supplied construction data and the
  node/document schema, so ``ErrorCode.INVALID_PARENT_TYPE`` -- the one
  CORE-layer catalog code about a value not matching the type a
  parent/container expects -- is reused consistently rather than minting a
  new code per call site.

Source-of-truth requirement labels honored here: {p008}, {p045}, {p050}.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import (
    Any,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from tree_engine.errors import ErrorCode

__all__ = [
    "NodeKind",
    "NodeSchemaError",
    "Node",
    "Document",
    "make_node",
    "iter_children",
    "walk",
]


class NodeSchemaError(Exception):
    """Raised when Node/Document construction data violates the schema.

    Always carries the originating ``ErrorCode`` from the shared catalog
    (``src/tree_engine/errors.py``) as ``self.code``, so callers can branch
    on the stable code rather than parsing message text.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code


class NodeKind(str):
    """Opaque, per-format node-kind identifier.

    A ``NodeKind`` is a plain, non-empty string handle that a format plugin
    (or test/caller) assigns to name its own node types, e.g.
    ``"python:FunctionDef"`` or ``"bsl:Procedure"``. The core namespace
    defined in this file does not enumerate, know, or care about the
    universe of kind strings -- per {p045} that knowledge stays inside
    format plugins -- it only requires that a kind be a non-empty string.
    Being a ``str`` subclass, a ``NodeKind`` compares and hashes exactly
    like the string it wraps.
    """

    __slots__ = ()

    def __new__(cls, value: str) -> "NodeKind":
        if not isinstance(value, str) or not value:
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"node kind must be a non-empty string, got {value!r}",
            )
        return super().__new__(cls, value)


Primitive = Union[str, int, float, bool, bytes, None]
FieldValue = Union[Primitive, "Node", Tuple["Node", ...]]


@dataclass(frozen=True)
class Node:
    """An immutable node in the common tree model.

    ``kind`` names the node's format-defined type. ``fields`` is a
    read-only, ``str``-keyed mapping of named node data, where each value
    is either a primitive (``str``, ``int``, ``float``, ``bool``,
    ``bytes``, or ``None``), a single ``Node``, or an ordered ``tuple`` of
    ``Node`` instances (an "ordered child sequence" attached under a named
    field, e.g. a function's ``body`` field). ``children`` is the separate,
    explicit, ordered tuple of every direct child node used by the generic
    traversal primitives below (``iter_children``/``walk``); it may repeat
    or reorganize node references also reachable through ``fields``, or
    stand fully on its own -- this file does not require the two to be
    kept in lockstep, only that each is independently well-formed.

    Nodes are immutable and must be built bottom-up (a child object must
    already exist before it can be placed in its parent's ``children`` or
    ``fields``), so no ``Node`` graph constructed through ``make_node`` can
    ever contain a reference cycle.

    Use ``make_node`` to construct a validated instance; the dataclass
    constructor itself performs no validation, which sibling steps may
    rely on when reconstructing an already-validated node (e.g. to attach
    an identity produced elsewhere).
    """

    kind: NodeKind
    fields: Mapping[str, FieldValue]
    children: Tuple["Node", ...]

    # Reserved extension-point slots for sibling steps. Inert here: default
    # only, never read or written anywhere else in this file.
    node_id: Optional[Any] = None
    short_id: Optional[Any] = None
    extended_type: Optional[Any] = None
    buffer_range: Optional[Any] = None
    references: Tuple[Any, ...] = field(default_factory=tuple)


@dataclass
class Document:
    """A tree document: an immutable ``root`` plus the format contract.

    Per {p050}: ``representation_format_id`` is the mandatory format of the
    document's *current working representation*; ``source_format_id`` is
    the originally selected/preserved format. In the ordinary case the two
    are equal. Under plain-text fallback, ``representation_format_id`` is
    set to ``"plain_text"`` while ``source_format_id`` is left untouched,
    so the original format is still known for the next open and for
    diagnostics. ``format_id`` is the public read-only alias for
    ``representation_format_id`` -- no separate ``language`` entity is
    introduced.

    ``Document`` is a plain (non-frozen) dataclass: unlike ``Node``, its
    format-contract fields are expected to be updated in place as the
    document's lifecycle progresses (e.g. entering or leaving plain-text
    fallback), while ``root`` itself is still replaced wholesale (new
    immutable ``Node`` graph in, old one out) rather than mutated.
    """

    root: Node
    source_format_id: str
    # Omitting it means "ordinary case" and derives it from source_format_id
    # ({p050}); it is set explicitly only when the two genuinely differ, as
    # under plain-text fallback.
    representation_format_id: Optional[str] = None

    # Reserved extension-point slot for a sibling step (cross-document
    # identity). Inert here: default only, never read or written anywhere
    # else in this file.
    document_id: Optional[Any] = None

    def __post_init__(self) -> None:
        if not isinstance(self.root, Node):
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"Document.root must be a Node, got {type(self.root).__name__}",
            )
        _validate_format_id("source_format_id", self.source_format_id)
        if self.representation_format_id is None:
            self.representation_format_id = self.source_format_id
        _validate_format_id("representation_format_id", self.representation_format_id)

    @property
    def format_id(self) -> str:
        """Public read-only alias for ``representation_format_id`` ({p050})."""
        return self.representation_format_id


def make_node(
    kind: Union[NodeKind, str],
    fields: Optional[Mapping[str, Any]] = None,
    children: Sequence[Any] = (),
) -> Node:
    """Build a ``Node``, validating that kind/fields/children are consistent.

    ``kind`` is coerced to (and validated as) a ``NodeKind``. ``fields``
    defaults to empty and each entry is checked against the ``FieldValue``
    union described on ``Node``. ``children`` defaults to empty and every
    entry must itself be a ``Node``; order is preserved exactly as given.

    Raises ``NodeSchemaError`` (carrying ``ErrorCode.INVALID_PARENT_TYPE``)
    on any shape mismatch, before constructing anything.
    """

    validated_kind = kind if isinstance(kind, NodeKind) else NodeKind(kind)
    validated_fields = _validate_fields(fields or {})
    validated_children = _validate_children(children)
    return Node(kind=validated_kind, fields=validated_fields, children=validated_children)


def iter_children(node: Node) -> Iterator[Node]:
    """Yield ``node``'s direct children, in the order given at construction.

    This does not recurse; it is exactly ``iter(node.children)``.
    """

    return iter(node.children)


def walk(node: Node) -> Iterator[Node]:
    """Depth-first, pre-order traversal of ``node``'s subtree.

    Yields ``node`` itself first, then walks each entry of
    ``node.children`` in order, recursively. Because ``Node`` is immutable
    and every child must exist before ``make_node`` can place it in its
    parent, a tree built through this module can never contain a
    reference cycle, so this traversal always terminates; each distinct
    tree position is visited exactly once, in a stable, repeatable order.
    """

    yield node
    for child in node.children:
        yield from walk(child)


def _is_primitive(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, bytes))


def _validate_field_value(name: str, value: Any) -> FieldValue:
    if _is_primitive(value):
        return value
    if isinstance(value, Node):
        return value
    if isinstance(value, (tuple, list)):
        items = tuple(value)
        for item in items:
            if not isinstance(item, Node):
                raise NodeSchemaError(
                    ErrorCode.INVALID_PARENT_TYPE,
                    f"field {name!r}: ordered child sequence entries must be "
                    f"Node instances, got {type(item).__name__}",
                )
        return items
    raise NodeSchemaError(
        ErrorCode.INVALID_PARENT_TYPE,
        f"field {name!r} has unsupported value type {type(value).__name__}; "
        "expected a primitive, a Node, or an ordered sequence of Node",
    )


def _validate_fields(fields: Mapping[str, Any]) -> Mapping[str, FieldValue]:
    if not isinstance(fields, Mapping):
        raise NodeSchemaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"fields must be a mapping, got {type(fields).__name__}",
        )
    validated: Dict[str, FieldValue] = {}
    for name, value in fields.items():
        if not isinstance(name, str) or not name:
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"field name must be a non-empty string, got {name!r}",
            )
        validated[name] = _validate_field_value(name, value)
    return MappingProxyType(validated)


def _validate_children(children: Sequence[Any]) -> Tuple[Node, ...]:
    if not isinstance(children, (tuple, list)):
        raise NodeSchemaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"children must be an ordered sequence, got {type(children).__name__}",
        )
    validated = tuple(children)
    for index, child in enumerate(validated):
        if not isinstance(child, Node):
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"children[{index}] must be a Node instance, got "
                f"{type(child).__name__}",
            )
    return validated


def _validate_format_id(field_name: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise NodeSchemaError(
            ErrorCode.INVALID_PARENT_TYPE,
            f"Document.{field_name} must be a non-empty string, got {value!r}",
        )
