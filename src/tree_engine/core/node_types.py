"""Extension node types outside the base LibCST subset ({p043}/{an01}/{iblr}),
plus the dedicated boolean ``export`` field ({p044}, context {p047}).

Defines ``PreprocessorDirectiveNode``, ``AnnotationNode``,
``VariableDeclarationNode``, ``VariableDeclaratorNode`` and the
``ExportFieldMixin`` that wires ``export`` into each of them.

SIBLING-DEPENDENCY NOTE: the common-tree-model base node contract
(``src/tree_engine/core/nodes.py``, owned by sibling TS G-001/T-001) does
not exist yet in this worktree, and this artifact's integration contract
forbids importing or stubbing it. ``ExtensionNodeBase`` below is therefore
a small, self-contained stand-in that carries only the identity
(UUID4 ``node_id``, ``short_id``, ``parent_id``), byte-range, source
``content``, generic attribute-bag, copy/move/serialize, and
search-predicate surface that {p043}/{an01}/{iblr}/{p044} require of every
extension node type. It depends only on the already-merged
``core.identity`` module. Once the real base class lands, these four node
types are expected to subclass it directly; their public shape should not
need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple
from uuid import UUID

from tree_engine.core.identity import generate_node_id

__all__ = [
    "ExportNotApplicableError",
    "IndexMapHookFn",
    "ExtensionNodeBase",
    "ExportFieldMixin",
    "PreprocessorDirectiveNode",
    "AnnotationNode",
    "VariableDeclaratorNode",
    "VariableDeclarationNode",
]


class ExportNotApplicableError(Exception):
    """Raised when ``export=True`` is requested on a node type where BSL's
    EXPORT_KEYWORD is not semantically applicable, per {p044}/{p047}."""


IndexMapHookFn = Callable[["ExtensionNodeBase", str, Any], None]


def _noop_index_map_hook(node: "ExtensionNodeBase", field_name: str, value: Any) -> None:
    """Default index-map hook.

    The real sibling-owned index-map update interface is delivered by a
    later artifact and does not exist in this worktree. Callers that need
    genuine index-map reflection inject their own hook via
    ``index_map_hook``; this module only guarantees it is invoked
    synchronously on every field change, per {p044}.
    """


@dataclass
class ExtensionNodeBase:
    """Self-contained identity/range/content/attribute surface shared by
    every extension node type (see the sibling-dependency note above).

    ``start_byte``/``end_byte`` are the node's byte range; ``content`` is
    its verbatim source content. Line/column position tracking is layered
    separately (by a sibling ``positions.py``-style module, out of scope
    here), matching the byte-preservation guarantees these node types
    must honor.
    """

    start_byte: int
    end_byte: int
    content: str = ""
    node_id: UUID = field(default_factory=generate_node_id)
    parent_id: Optional[UUID] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    index_map_hook: IndexMapHookFn = field(default=_noop_index_map_hook, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.end_byte < self.start_byte:
            raise ValueError(
                f"end_byte ({self.end_byte}) precedes start_byte ({self.start_byte})"
            )

    @property
    def short_id(self) -> str:
        """Short display identifier derived from ``node_id``."""
        return str(self.node_id)[:8]

    @property
    def byte_range(self) -> Tuple[int, int]:
        return (self.start_byte, self.end_byte)

    def get_attribute(self, name: str, default: Any = None) -> Any:
        return self.attributes.get(name, default)

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value
        self.index_map_hook(self, name, value)

    def matches(self, **predicates: Any) -> bool:
        """Search-predicate helper: true when every keyword matches a
        first-class field (a property, e.g. ``export``) or an
        ``attributes`` entry."""
        for key, expected in predicates.items():
            descriptor = getattr(self.__class__, key, None)
            actual = getattr(self, key) if isinstance(descriptor, property) else self.attributes.get(key)
            if actual != expected:
                return False
        return True

    def _copy_kwargs(self) -> Dict[str, Any]:
        return dict(
            start_byte=self.start_byte,
            end_byte=self.end_byte,
            content=self.content,
            node_id=self.node_id,
            parent_id=self.parent_id,
            attributes=dict(self.attributes),
            index_map_hook=self.index_map_hook,
        )

    def copy(self) -> "ExtensionNodeBase":
        """Deep copy preserving node identity, range, content and
        attributes (including ``export``); no core-added semantics."""
        return self.__class__(**self._copy_kwargs())

    def move_to(self, new_parent_id: Optional[UUID]) -> "ExtensionNodeBase":
        """Reparent in place. Identity, range, content and attributes
        (including ``export``) are left untouched."""
        self.parent_id = new_parent_id
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Serialize verbatim: identity, byte range, content and
        attributes round-trip with no core-added semantics."""
        return {
            "type": self.__class__.__name__,
            "node_id": str(self.node_id),
            "short_id": self.short_id,
            "parent_id": str(self.parent_id) if self.parent_id is not None else None,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "content": self.content,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **extra: Any) -> "ExtensionNodeBase":
        return cls(
            start_byte=data["start_byte"],
            end_byte=data["end_byte"],
            content=data.get("content", ""),
            node_id=UUID(data["node_id"]),
            parent_id=UUID(data["parent_id"]) if data.get("parent_id") else None,
            attributes=dict(data.get("attributes", {})),
            **extra,
        )


class ExportFieldMixin:
    """Wires a dedicated boolean ``export`` field into the stable node
    contract ({p044}): a first-class field, not a loose ``attributes``
    entry. Applied in accepting form to ``VariableDeclarationNode`` and
    ``VariableDeclaratorNode`` (BSL's EXPORT_KEYWORD is semantically
    applicable there, per {p047}), and in rejecting form -- via
    ``_export_applicable = False`` -- to ``PreprocessorDirectiveNode`` and
    ``AnnotationNode`` (export is inapplicable there).
    """

    _export_applicable: ClassVar[bool] = True

    attributes: Dict[str, Any]
    index_map_hook: IndexMapHookFn

    @property
    def export(self) -> bool:
        return self.attributes.get("export", False)

    def get_attribute(self, name: str, default: Any = None) -> Any:
        if name == "export":
            return self.attributes.get("export", False)
        return super().get_attribute(name, default)  # type: ignore[misc]

    def set_attribute(self, name: str, value: Any) -> None:
        if name != "export":
            super().set_attribute(name, value)  # type: ignore[misc]
            return
        if not isinstance(value, bool):
            raise TypeError(f"export must be a bool, got {type(value).__name__}")
        if not self._export_applicable:
            if value:
                raise ExportNotApplicableError(
                    self.__class__.__name__
                    + " does not support export (BSL EXPORT_KEYWORD is"
                    " inapplicable here, per {p047})"
                )
            return  # setting False on a rejecting node type is a no-op
        self.attributes["export"] = value
        self.index_map_hook(self, "export", value)  # type: ignore[misc]


@dataclass
class PreprocessorDirectiveNode(ExportFieldMixin, ExtensionNodeBase):
    """Ordinary content-bearing node for BSL/1C preprocessor directives
    ({p043}). The core applies no preprocessor semantics here: no
    directive parsing, no conditional-branch logic. Stored, addressed,
    copied, moved and serialized exactly like any other node via the
    inherited base behavior; ``export`` is inapplicable (rejecting form).
    """

    _export_applicable: ClassVar[bool] = False


@dataclass
class AnnotationNode(ExportFieldMixin, ExtensionNodeBase):
    """Standalone content-bearing node for BSL annotations such as
    &НаСервере/&AtServer ({an01}), structurally distinct from
    ``PreprocessorDirectiveNode`` -- never merged or unioned with it.
    Carries an optional ordered collection of child argument-value nodes,
    with their inter-argument separators preserved; the core performs no
    BSL-specific recognition of annotation syntax. ``export`` is
    inapplicable (rejecting form).
    """

    _export_applicable: ClassVar[bool] = False
    arguments: List[Any] = field(default_factory=list)
    argument_separators: List[str] = field(default_factory=list)

    def _copy_kwargs(self) -> Dict[str, Any]:
        kwargs = super()._copy_kwargs()
        kwargs["arguments"] = [a.copy() if hasattr(a, "copy") else a for a in self.arguments]
        kwargs["argument_separators"] = list(self.argument_separators)
        return kwargs

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["arguments"] = [a.to_dict() if hasattr(a, "to_dict") else a for a in self.arguments]
        data["argument_separators"] = list(self.argument_separators)
        return data


@dataclass
class VariableDeclaratorNode(ExportFieldMixin, ExtensionNodeBase):
    """One declared variable inside a ``VariableDeclarationNode``
    ({iblr}). Carries its own identity and byte-range fields independent
    of its siblings and of the parent declaration. ``export`` reflects
    BSL's EXPORT_KEYWORD when present on this declarator (accepting
    form).
    """

    name: str = ""

    def _copy_kwargs(self) -> Dict[str, Any]:
        kwargs = super()._copy_kwargs()
        kwargs["name"] = self.name
        return kwargs

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["name"] = self.name
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **extra: Any) -> "VariableDeclaratorNode":
        return super().from_dict(data, name=data.get("name", ""), **extra)  # type: ignore[return-value]


@dataclass
class VariableDeclarationNode(ExportFieldMixin, ExtensionNodeBase):
    """Owns an ordered list of ``VariableDeclaratorNode`` children
    ({iblr}), preserving inter-declarator separators and formatting
    exactly as stored. Represents constructs like ``Перем а, с;`` as one
    ``variable_declaration`` node with multiple declarator children --
    never as an assignment node. ``export`` is accepting form.
    """

    declarators: List[VariableDeclaratorNode] = field(default_factory=list)
    separators: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        expected = max(0, len(self.declarators) - 1)
        if len(self.separators) != expected:
            raise ValueError(
                f"expected {expected} separators for {len(self.declarators)} "
                f"declarators, got {len(self.separators)}"
            )

    def _copy_kwargs(self) -> Dict[str, Any]:
        kwargs = super()._copy_kwargs()
        kwargs["declarators"] = [d.copy() for d in self.declarators]
        kwargs["separators"] = list(self.separators)
        return kwargs

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["declarators"] = [d.to_dict() for d in self.declarators]
        data["separators"] = list(self.separators)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **extra: Any) -> "VariableDeclarationNode":
        declarators = [VariableDeclaratorNode.from_dict(d) for d in data.get("declarators", [])]
        return super().from_dict(  # type: ignore[return-value]
            data,
            declarators=declarators,
            separators=list(data.get("separators", [])),
            **extra,
        )
