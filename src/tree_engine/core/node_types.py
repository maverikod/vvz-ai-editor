"""Extension node types outside the base LibCST subset ({p043}/{an01}/{iblr}),
plus the dedicated boolean ``export`` field ({p044}, context {p047}).

Defines ``PreprocessorDirectiveNode``, ``AnnotationNode``,
``VariableDeclarationNode``, ``VariableDeclaratorNode`` and the
``ExportFieldMixin`` that wires ``export`` into each of them.

Builds directly on the common-tree-model base contract in
``src/tree_engine/core/nodes.py`` (``Node``, ``NodeKind``, ``make_node``,
``NodeSchemaError``) instead of a second node model. Each type below is a
thin wrapper composed around exactly one immutable ``Node`` (``.node``):
construction goes through ``make_node``'s validation, per-field data
(content, ``export``, declarator ``name``, child sequences) lives in that
``Node``'s ``fields``/``children``, and the reserved ``extended_type`` slot
records which wrapper class owns a given ``Node`` -- its reserved purpose.
Because ``Node`` is immutable, ``set_attribute`` rebuilds the wrapped
``Node`` through ``make_node`` again while keeping the same
``node_id``/``short_id``; nothing here re-implements identity, validation
or traversal -- ``iter_children``/``walk`` from ``nodes.py`` operate
directly on ``.node``. Non-goals: BSL/1C parsing, tree-sitter integration,
changes to ``nodes.py``, format-plugin code, persistence/index-map
implementation (only a synchronous call to an injectable hook stand-in).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, ClassVar, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from tree_engine.core.identity import generate_node_id
from tree_engine.core.nodes import Node, NodeKind, NodeSchemaError, make_node
from tree_engine.errors import ErrorCode

__all__ = [
    "ExportNotApplicableError",
    "IndexMapHookFn",
    "ExportFieldMixin",
    "PreprocessorDirectiveNode",
    "AnnotationNode",
    "VariableDeclaratorNode",
    "VariableDeclarationNode",
]

IndexMapHookFn = Callable[[Any, str, Any], None]
_SEP = "\x00"


def _noop_index_map_hook(node: Any, field_name: str, value: Any) -> None:
    """Default index-map hook: no-op stand-in for the sibling-owned
    index-map update interface (delivered by a later artifact and not
    present in this worktree). Callers that need real index-map
    reflection inject their own hook via ``index_map_hook``; this module
    only guarantees it is invoked synchronously on every field change,
    per {p044}."""


def _encode_seps(separators: Sequence[str]) -> str:
    """Encode an ordered separator list into one ``Node.fields`` primitive
    string, count-prefixed so an empty list and a list holding a single
    empty separator decode distinctly."""
    seps = list(separators)
    return f"{len(seps)}{_SEP}" + _SEP.join(seps)


def _decode_seps(encoded: str) -> List[str]:
    count_str, _, remainder = encoded.partition(_SEP)
    count = int(count_str) if count_str else 0
    return [] if count == 0 else remainder.split(_SEP)


class ExportNotApplicableError(NodeSchemaError):
    """Raised when ``export=True`` is requested on a node kind where BSL's
    EXPORT_KEYWORD is not semantically applicable, per {p044}/{p047}."""

    def __init__(self, node_type_name: str) -> None:
        super().__init__(
            ErrorCode.INVALID_PARENT_TYPE,
            f"{node_type_name} does not support export (BSL EXPORT_KEYWORD "
            "is inapplicable here, per {p047})",
        )


class _NodeWrapper:
    """Ergonomic wrapper composed around one immutable base ``Node``.

    Not a second node model: every subclass sets ``_KIND`` and delegates
    all shape/validation to ``make_node``. Identity (``node_id``,
    ``short_id``), ``extended_type`` and byte range (``buffer_range``) are
    the reserved ``Node`` slots this module was told to use; ``parent_id``
    has no counterpart on ``Node`` (bottom-up immutable construction keeps
    no back-references) so it is carried as plain wrapper bookkeeping.
    """

    _KIND: ClassVar[NodeKind]

    def __init__(
        self, *, start_byte: int, end_byte: int, content: str = "",
        node_id: Optional[UUID] = None, parent_id: Optional[UUID] = None,
        index_map_hook: Optional[IndexMapHookFn] = None, children: Sequence[Node] = (),
        **extra_fields: Any,
    ) -> None:
        if end_byte < start_byte:
            raise NodeSchemaError(
                ErrorCode.INVALID_POSITION,
                f"end_byte ({end_byte}) precedes start_byte ({start_byte})",
            )
        resolved_id = node_id or generate_node_id()
        # Construction must not be a back door around the export rule that
        # set_attribute enforces: on a kind where export is inapplicable,
        # requesting it here fails just as loudly ({p044}).
        if extra_fields.get("export") and not getattr(self, "_export_applicable", True):
            raise ExportNotApplicableError(type(self).__name__)
        fields: Dict[str, Any] = {"content": content, **extra_fields}
        base = make_node(self._KIND, fields=fields, children=tuple(children))
        self._node: Node = replace(
            base,
            node_id=resolved_id,
            short_id=str(resolved_id)[:8],
            extended_type=type(self).__name__,
            buffer_range=(start_byte, end_byte),
        )
        self.index_map_hook: IndexMapHookFn = index_map_hook or _noop_index_map_hook
        self.parent_id: Optional[UUID] = parent_id

    @classmethod
    def from_node(
        cls, node: Node, *, index_map_hook: Optional[IndexMapHookFn] = None,
        parent_id: Optional[UUID] = None,
    ) -> "_NodeWrapper":
        """Wrap an already-validated ``Node`` with no re-validation, as
        ``nodes.py`` documents for sibling steps attaching identity/
        extension data produced elsewhere."""
        self = object.__new__(cls)
        self._node = node
        self.index_map_hook = index_map_hook or _noop_index_map_hook
        self.parent_id = parent_id
        return self

    @property
    def node(self) -> Node:
        return self._node

    @property
    def node_id(self) -> UUID:
        return self._node.node_id

    @property
    def short_id(self) -> str:
        return self._node.short_id

    @property
    def byte_range(self) -> Tuple[int, int]:
        return self._node.buffer_range

    @property
    def content(self) -> str:
        return self._node.fields.get("content", "")

    def get_attribute(self, name: str, default: Any = None) -> Any:
        return self._node.fields.get(name, default)

    def set_attribute(self, name: str, value: Any) -> None:
        """Rebuild the wrapped ``Node`` through ``make_node`` (reusing its
        validation path) with ``name`` set, keeping identity/extension
        reserved slots, then invoke the index-map hook synchronously."""
        new_fields = dict(self._node.fields)
        new_fields[name] = value
        rebuilt = make_node(self._node.kind, fields=new_fields, children=self._node.children)
        self._node = replace(
            rebuilt,
            node_id=self._node.node_id,
            short_id=self._node.short_id,
            extended_type=self._node.extended_type,
            buffer_range=self._node.buffer_range,
            references=self._node.references,
        )
        self.index_map_hook(self, name, value)

    def matches(self, **predicates: Any) -> bool:
        """Search-predicate helper: true when every keyword matches a
        first-class property (e.g. ``export``) or a ``fields`` entry."""
        for key, expected in predicates.items():
            descriptor = getattr(type(self), key, None)
            actual = getattr(self, key) if isinstance(descriptor, property) else self._node.fields.get(key)
            if actual != expected:
                return False
        return True

    def copy(self, *, preserve_ids: bool = False) -> "_NodeWrapper":
        """Copy content, range and every field (including ``export``).

        By default the copy gets a FRESH ``node_id`` and no ``short_id``:
        two live nodes must never share an identifier, and the document
        that receives the copy allocates its own short id. ``preserve_ids``
        keeps the original identity for the {p074} copy mode that moves a
        subtree into a new document under its existing UUIDs.
        """
        node = self._node
        if not preserve_ids:
            node = replace(node, node_id=generate_node_id(), short_id=None)
        return type(self).from_node(node, index_map_hook=self.index_map_hook, parent_id=self.parent_id)

    def move_to(self, new_parent_id: Optional[UUID]) -> "_NodeWrapper":
        """Reparent in place; the wrapped ``Node`` (identity, range,
        content, fields) is left completely untouched."""
        self.parent_id = new_parent_id
        return self

    def to_dict(self) -> Dict[str, Any]:
        start, end = self._node.buffer_range
        return {
            "type": type(self).__name__,
            "node_id": str(self._node.node_id),
            "parent_id": str(self.parent_id) if self.parent_id is not None else None,
            "start_byte": start,
            "end_byte": end,
            "content": self.content,
            "fields": {k: v for k, v in self._node.fields.items() if k != "content"},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **extra: Any) -> "_NodeWrapper":
        parent_id = UUID(data["parent_id"]) if data.get("parent_id") else None
        fields = dict(data.get("fields", {}))
        fields.update(extra)
        return cls(
            start_byte=data["start_byte"],
            end_byte=data["end_byte"],
            content=data.get("content", ""),
            node_id=UUID(data["node_id"]),
            parent_id=parent_id,
            **fields,
        )


def _as_node(value: Any) -> Node:
    return value.node if isinstance(value, _NodeWrapper) else value


class ExportFieldMixin:
    """Wires a dedicated boolean ``export`` field into the stable node
    contract ({p044}): a first-class field, not a loose entry a caller
    stumbles into. Applied in accepting form to ``VariableDeclarationNode``
    and ``VariableDeclaratorNode`` (BSL's EXPORT_KEYWORD is semantically
    applicable there, per {p047}), and in rejecting form -- via
    ``_export_applicable = False`` -- to ``PreprocessorDirectiveNode`` and
    ``AnnotationNode`` (export is inapplicable there).
    """

    _export_applicable: ClassVar[bool] = True

    @property
    def export(self) -> bool:
        return self._node.fields.get("export", False)  # type: ignore[attr-defined]

    def get_attribute(self, name: str, default: Any = None) -> Any:
        if name == "export":
            return self._node.fields.get("export", False)  # type: ignore[attr-defined]
        return super().get_attribute(name, default)  # type: ignore[misc]

    def set_attribute(self, name: str, value: Any) -> None:
        if name != "export":
            super().set_attribute(name, value)  # type: ignore[misc]
            return
        if not isinstance(value, bool):
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE, f"export must be a bool, got {type(value).__name__}"
            )
        if not self._export_applicable:
            if value:
                raise ExportNotApplicableError(type(self).__name__)
            return  # setting False on a rejecting node type is a no-op
        super().set_attribute("export", value)  # type: ignore[misc]


class PreprocessorDirectiveNode(ExportFieldMixin, _NodeWrapper):
    """Ordinary content-bearing node for BSL/1C preprocessor directives
    ({p043}). The core applies no preprocessor semantics: no directive
    parsing, no conditional-branch logic. Stored, addressed, copied,
    moved and serialized exactly like any other node via ``_NodeWrapper``;
    ``export`` is inapplicable (rejecting form).
    """

    _KIND: ClassVar[NodeKind] = NodeKind("core:preprocessor_directive")
    _export_applicable: ClassVar[bool] = False


class AnnotationNode(ExportFieldMixin, _NodeWrapper):
    """Standalone content-bearing node for BSL annotations such as
    &НаСервере/&AtServer ({an01}), structurally distinct from
    ``PreprocessorDirectiveNode`` -- never merged or unioned with it.
    Carries an optional ordered collection of child argument-value nodes,
    stored via the base contract's own ``fields``/``children`` child-
    sequence mechanism, with inter-argument separators preserved. The core
    performs no BSL-specific recognition of annotation syntax. ``export``
    is inapplicable (rejecting form).
    """

    _KIND: ClassVar[NodeKind] = NodeKind("core:annotation")
    _export_applicable: ClassVar[bool] = False

    def __init__(
        self, *, start_byte: int, end_byte: int, content: str = "",
        node_id: Optional[UUID] = None, parent_id: Optional[UUID] = None,
        index_map_hook: Optional[IndexMapHookFn] = None,
        arguments: Sequence[Any] = (), argument_separators: Sequence[str] = (),
        **extra: Any,
    ) -> None:
        arg_nodes = tuple(_as_node(a) for a in arguments)
        extra["arguments"] = arg_nodes
        extra["argument_separators"] = _encode_seps(argument_separators)
        super().__init__(
            start_byte=start_byte, end_byte=end_byte, content=content, node_id=node_id,
            parent_id=parent_id, index_map_hook=index_map_hook, children=arg_nodes, **extra,
        )

    @property
    def arguments(self) -> Tuple[Node, ...]:
        return self._node.fields.get("arguments", ())

    @property
    def argument_separators(self) -> List[str]:
        return _decode_seps(self._node.fields.get("argument_separators", ""))

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **extra: Any) -> "AnnotationNode":
        fields = dict(data.get("fields", {}))
        arguments = fields.pop("arguments", ())
        argument_separators = _decode_seps(fields.pop("argument_separators", ""))
        parent_id = UUID(data["parent_id"]) if data.get("parent_id") else None
        return cls(
            start_byte=data["start_byte"], end_byte=data["end_byte"], content=data.get("content", ""),
            node_id=UUID(data["node_id"]), parent_id=parent_id,
            arguments=arguments, argument_separators=argument_separators, **fields, **extra,
        )


class VariableDeclaratorNode(ExportFieldMixin, _NodeWrapper):
    """One declared variable inside a ``VariableDeclarationNode``
    ({iblr}). Carries its own identity and byte-range fields independent
    of its siblings and of the parent declaration. ``export`` reflects
    BSL's EXPORT_KEYWORD when present on this declarator (accepting
    form).
    """

    _KIND: ClassVar[NodeKind] = NodeKind("core:variable_declarator")

    @property
    def name(self) -> str:
        return self._node.fields.get("name", "")


class VariableDeclarationNode(ExportFieldMixin, _NodeWrapper):
    """Owns an ordered list of ``VariableDeclaratorNode`` children
    ({iblr}), preserving inter-declarator separators and formatting
    exactly as stored. Represents constructs like ``Перем а, с;`` as one
    ``variable_declaration`` node with multiple declarator children --
    never as an assignment node. ``export`` is accepting form.
    """

    _KIND: ClassVar[NodeKind] = NodeKind("core:variable_declaration")

    def __init__(
        self, *, start_byte: int, end_byte: int, content: str = "",
        node_id: Optional[UUID] = None, parent_id: Optional[UUID] = None,
        index_map_hook: Optional[IndexMapHookFn] = None,
        declarators: Sequence[Any] = (), separators: Sequence[str] = (),
        **extra: Any,
    ) -> None:
        expected = max(0, len(declarators) - 1)
        if len(separators) != expected:
            raise NodeSchemaError(
                ErrorCode.INVALID_PARENT_TYPE,
                f"expected {expected} separators for {len(declarators)} "
                f"declarators, got {len(separators)}",
            )
        decl_nodes = tuple(_as_node(d) for d in declarators)
        extra["declarators"] = decl_nodes
        extra["separators"] = _encode_seps(separators)
        super().__init__(
            start_byte=start_byte, end_byte=end_byte, content=content, node_id=node_id,
            parent_id=parent_id, index_map_hook=index_map_hook, children=decl_nodes, **extra,
        )

    @property
    def declarators(self) -> List[VariableDeclaratorNode]:
        return [VariableDeclaratorNode.from_node(n) for n in self._node.fields.get("declarators", ())]

    @property
    def separators(self) -> List[str]:
        return _decode_seps(self._node.fields.get("separators", ""))

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **extra: Any) -> "VariableDeclarationNode":
        fields = dict(data.get("fields", {}))
        declarators = fields.pop("declarators", ())
        separators = _decode_seps(fields.pop("separators", ""))
        parent_id = UUID(data["parent_id"]) if data.get("parent_id") else None
        return cls(
            start_byte=data["start_byte"], end_byte=data["end_byte"], content=data.get("content", ""),
            node_id=UUID(data["node_id"]), parent_id=parent_id,
            declarators=declarators, separators=separators, **fields, **extra,
        )
