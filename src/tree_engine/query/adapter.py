"""Traversal adapter binding the ported cst_query engine to the common tree
(concept C-009, atomic step G-018/T-001/A-002).

Scope, per {p005} and {p018}: this is the *only* piece of the cst_query
port that changes. The legacy engine in ``ai_editor/cst_query`` walked a
LibCST tree via ``ai_editor/cst_query/index_builder.py`` (``build_index``,
producing one ``NodeInfo`` per visited node with its LibCST parent, a
``kind`` alias -- ``module``/``class``/``function``/``method``/``stmt``/
``smallstmt``/``import``/``node`` -- resolved from a class/function name
stack, plus position/name/qualname) and matched selector steps against
that flat list in ``ai_editor/cst_query/executor.py`` (``_matches_node_type``:
a known alias compares against ``kind``, anything else compares against the
literal LibCST class name). This module reproduces exactly that traversal
contract -- "walk every node, tag it with a role if one applies, keep every
node reachable by its own literal type name regardless" -- over the common
tree model instead of LibCST, so the selector language, predicates,
combinators, pseudo-selectors, result models and exceptions living in
sibling files (this same tactical step, T-001) need no functional
redesign, only a new traversal source.

Two differences from the legacy adapter, both required by the common
model: (1) the four legacy alias buckets ``function``/``method``/``class``/
``module`` are no longer a hand-written class/function name stack -- they
are the standard semantic roles a loaded format plugin declares via
:meth:`~tree_engine.plugins.contract.FormatPluginContract.semantic_role_mapping`
(and, where a plugin exposes it, its own context-sensitive
``role_for(node, ancestors)`` resolver -- see ``tree_engine.plugins.python
.plugin.PythonFormatPlugin.role_for``, whose docstring explains why a flat
kind -> role table alone cannot distinguish a method from a top-level
function); (2) every produced match is a sibling ``QueryMatch`` (see
``tree_engine.query.results``), carrying the {p021} ``node_id``/
``short_id_hex`` pair for the node itself and for every ancestor on its
``parent_path``, instead of the legacy ``NodeInfo``/``Match`` shape.

This module reads only already-loaded ``Document``/``Node`` state (see
``tree_engine.core.nodes``): it never parses or reparses source text, and
it never mutates the tree, a document version, or any index. Predicate
evaluation, combinators, pseudo-selectors, and full selector orchestration
are sibling concerns under this same tactical step and are out of scope
here -- this module only walks the tree, resolves each node's role, and
assembles the compact result record for a node the caller already decided
is a match by type/role.

Source-of-truth requirement labels honored here: {p005}, {p018}, {p021},
{p040}.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional, Sequence, Tuple

from tree_engine.core.address import NodeAddressView, build_node_address_view
from tree_engine.core.nodes import Document, Node, iter_children
from tree_engine.core.short_id import to_hex
from tree_engine.query.results import QueryMatch, build_query_match

__all__ = [
    "TreeTraversalAdapter",
    "iter_matching_nodes",
    "resolve_semantic_role",
]

# The four standard semantic roles the selector language's pseudo-types
# (function, method, class, module) resolve to, per {p018}. Anything else
# passed as ``node_type`` is treated as a literal, format-specific type
# name (e.g. ``core:preprocessor_directive``), matched against the node's
# own ``kind`` -- never against a role.
_STANDARD_ROLE_NAMES = frozenset({"function", "method", "class", "module"})


def resolve_semantic_role(
    plugin: Any, node: Node, ancestors: Sequence[Node] = ()
) -> str:
    """Ask ``plugin`` which standard semantic role (if any) ``node`` plays.

    ``plugin`` is duck-typed against
    ``tree_engine.plugins.contract.FormatPluginContract``: this function
    never imports a concrete plugin or a registry, it only calls whatever
    the caller already resolved and injected.

    Preference order, mirroring
    ``tree_engine.plugins.python.plugin.PythonFormatPlugin``'s own
    documented reasoning: if ``plugin`` exposes a callable ``role_for``
    attribute, it is called as ``role_for(node, ancestors)`` -- the only
    way to resolve a role that depends on structural context, such as
    promoting a function-shaped node to ``method`` when its nearest
    enclosing construct is a class. Otherwise this falls back to the
    mandatory, context-free ``plugin.semantic_role_mapping()`` declarative
    table and looks up ``node.kind`` in it directly.

    Returns the resolved role as a plain lowercase string (``"function"``,
    ``"method"``, ``"class"``, or ``"module"``), or ``""`` when no role
    applies -- never raises for an inapplicable role, per {p018}: "for a
    format where the role is inapplicable, a query correctly returns an
    empty result".
    """

    role_for = getattr(plugin, "role_for", None)
    if callable(role_for):
        return _role_to_str(role_for(node, tuple(ancestors)))

    mapping = plugin.semantic_role_mapping()
    node_type_to_role = getattr(mapping, "node_type_to_role", mapping)
    role = node_type_to_role.get(str(node.kind))
    return _role_to_str(role)


def _role_to_str(role: Any) -> str:
    """Normalize a resolved role to a plain string, ``""`` when absent.

    Accepts ``None`` (no role), a plain ``str``, or an enum member such as
    ``tree_engine.plugins.contract.SemanticRole`` (read via its ``.value``)
    -- whatever shape a duck-typed plugin returns.
    """

    if role is None:
        return ""
    return str(getattr(role, "value", role))


def _matches_node_type(node: Node, role: str, node_type: Optional[str]) -> bool:
    """True when ``node`` (already tagged with ``role``) satisfies ``node_type``.

    ``None`` or ``"*"`` matches every node (the universal selector). A
    ``node_type`` naming one of the four standard roles matches only on
    ``role`` equality. Anything else -- including a format-specific
    extension type such as ``core:preprocessor_directive`` -- matches only
    the node's own literal ``kind`` string, exactly as the legacy engine's
    ``_matches_node_type`` fell back to the literal LibCST class name for
    any non-alias selector, and independent of ``role``.
    """

    if node_type is None or node_type == "*":
        return True
    normalized = node_type.lower()
    if normalized in _STANDARD_ROLE_NAMES:
        return role == normalized
    return str(node.kind) == node_type


def _build_parent_path(ancestors: Sequence[Node]) -> Tuple[NodeAddressView, ...]:
    """Build the ordered {p021} ``parent_path`` for ``ancestors``.

    ``ancestors`` must already be in root-to-immediate-parent order (the
    order :func:`_walk` below produces). Each entry is turned into a
    ``NodeAddressView`` pairing that ancestor's ``node_id`` with its
    compact ``short_id_hex``, via ``tree_engine.core.address
    .build_node_address_view`` -- the sibling helper
    ``tree_engine.query.results`` itself documents as how a caller is
    expected to produce this pair, so this function never formats hex or
    assembles the pair by hand.
    """

    return tuple(
        build_node_address_view(ancestor.node_id, ancestor.short_id)
        for ancestor in ancestors
    )


def _walk(
    node: Node, ancestors: Tuple[Node, ...], plugin: Any
) -> Iterator[Tuple[Node, Tuple[Node, ...], str]]:
    """Depth-first, pre-order walk yielding ``(node, ancestors, role)``.

    ``ancestors`` is ``node``'s own ancestor path, root first, immediate
    parent last -- exactly the order :func:`_build_parent_path` expects.
    Recurses only through ``tree_engine.core.nodes.iter_children``, so it
    reads exactly the children ``Node`` already carries; nothing here
    parses, reparses, or mutates anything.
    """

    role = resolve_semantic_role(plugin, node, ancestors)
    yield node, ancestors, role
    child_ancestors = ancestors + (node,)
    for child in iter_children(node):
        yield from _walk(child, child_ancestors, plugin)


def iter_matching_nodes(
    document: Document, plugin: Any, node_type: Optional[str] = None
) -> Iterator[QueryMatch]:
    """Yield a :class:`~tree_engine.query.results.QueryMatch` for every node
    of ``document.root``'s already-loaded subtree that satisfies ``node_type``.

    ``node_type`` is either one of the four standard semantic roles
    (matched via :func:`resolve_semantic_role`, per plugin, with an
    inapplicable role simply producing no matches -- never an error) or a
    literal format-specific type name (matched against the node's own
    ``kind``, independent of role, per {p018}); ``None``/``"*"`` matches
    every node. Every yielded ``QueryMatch`` carries the node's own
    ``node_id``/``short_id_hex`` and its full root-to-parent ``parent_path``
    (see :func:`_build_parent_path`), assembled solely through the sibling
    ``tree_engine.query.results.build_query_match`` constructor -- this
    function never builds a competing result shape.

    Reads only ``document``/``plugin`` state already given to it: no
    source text is parsed or reparsed, and no node, document version, or
    index is mutated.
    """

    for node, ancestors, role in _walk(document.root, (), plugin):
        if not _matches_node_type(node, role, node_type):
            continue
        parent_path = _build_parent_path(ancestors)
        short_id_hex = to_hex(node.short_id)
        yield build_query_match(node, role, short_id_hex, parent_path)


class TreeTraversalAdapter:
    """Binds one already-loaded ``Document`` and its format plugin to the
    ported cst_query engine's traversal needs (concept C-009).

    Thin, stateless-beyond-construction wrapper around the module-level
    :func:`iter_matching_nodes`/:func:`resolve_semantic_role` functions:
    it exists so sibling selector-orchestration code (predicate
    evaluation, combinators, pseudo-selectors -- out of scope here) can
    hold one adapter instance per open document/plugin pair instead of
    re-threading both through every call.

    ``document`` and ``plugin`` are stored exactly as given -- this class
    performs no validation, resolution, or lookup of its own: the caller
    is expected to have already loaded the document's tree and resolved
    its format plugin (e.g. via ``tree_engine.plugins.selection``)
    beforehand.
    """

    def __init__(self, document: Document, plugin: Any) -> None:
        self._document = document
        self._plugin = plugin

    @property
    def document(self) -> Document:
        """The already-loaded ``Document`` this adapter walks."""

        return self._document

    @property
    def plugin(self) -> Any:
        """The already-loaded format plugin used for role resolution."""

        return self._plugin

    def iter_nodes(self) -> Iterator[Tuple[Node, Tuple[Node, ...], str]]:
        """Depth-first pre-order traversal of the whole document tree.

        Yields ``(node, ancestors, role)`` for every node, ``ancestors``
        in root-to-parent order and ``role`` the standard semantic role
        (``""`` when none applies) -- the raw traversal entry point
        sibling selector-orchestration code builds on top of. Equivalent
        to the module-level :func:`_walk` seeded from ``self.document.root``.
        """

        return _walk(self._document.root, (), self._plugin)

    def iter_matching_nodes(self, node_type: Optional[str] = None) -> Iterator[QueryMatch]:
        """Bound form of the module-level :func:`iter_matching_nodes`,
        using this adapter's own ``document`` and ``plugin``."""

        return iter_matching_nodes(self._document, self._plugin, node_type)

    def resolve_semantic_role(self, node: Node, ancestors: Sequence[Node] = ()) -> str:
        """Bound form of the module-level :func:`resolve_semantic_role`,
        using this adapter's own ``plugin``."""

        return resolve_semantic_role(self._plugin, node, ancestors)
