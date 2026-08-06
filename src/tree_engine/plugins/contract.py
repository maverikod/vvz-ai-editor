"""Abstract format-plugin contract (concept C-010).

Scope: this module defines the *interface* boundary between the core tree
engine and format-specific plugins (Python, BSL, JavaScript, ...). It does
not implement, select, or discover any concrete plugin, and it contains no
registry. Registry operations (``register_format_plugin``,
``unregister_format_plugin``, ``get_format_plugin``, ``list_format_plugins``)
and entry-point-based lazy loading are delivered by sibling steps under the
same tactical step (T-001) and must not be duplicated here.

Deviation note: per {p045}/{p051} the plugin contract is meant to sit on top
of a core-side plugin boundary module (``src/tree_engine/core/plugin_boundary.py``).
That module does not exist yet in this worktree at the time this file was
written, and sibling core modules that are not yet merged must not be
imported or stubbed from here. Consequently this file is self-contained: it
defines its own minimal metadata, error, and node-placeholder types instead
of importing them from the not-yet-existing boundary module. Once
``plugin_boundary.py`` lands, this file must be reconciled with it rather
than continuing to duplicate any type it defines.

The common-model node type itself (concept C-002) is not merged into this
worktree either. ``CommonModelNode`` below is therefore a documented
placeholder alias (``Any``) for "one or more nodes of the format-independent
common tree model" -- it is not a new type definition competing with C-002,
only a local name used for type-hinting this contract until the concrete
type is available to import.

Every mandatory stage below is one direction of the bidirectional
translator a format plugin must implement ({p051}, {p056}, {p057}):
``parse_document``/``import_external_tree`` obtain a parser-library
representation, ``import_to_common`` turns that representation into common
nodes, ``export_from_common`` turns common nodes back into a backend
representation, and ``generate_output`` turns that representation into final
text or bytes. External library trees must never cross the boundary back
into caller code: only common-model nodes or, for ``parse_fragment``, a
plain fallback string, may be returned.
"""

from __future__ import annotations

import abc
import enum
from typing import Any, Mapping, Tuple, Union

from tree_engine.errors import ErrorCode

__all__ = [
    "CommonModelNode",
    "SemanticRole",
    "STANDARD_SEMANTIC_ROLES",
    "SemanticRoleMapping",
    "FormatPluginMetadata",
    "UnsupportedTranslationError",
    "FormatPluginContractError",
    "FormatPluginContract",
]

# Placeholder for "one or more nodes of the format-independent common tree
# model" (concept C-002). Not merged into this worktree yet; see the module
# docstring. Using ``Any`` here keeps this contract from inventing a
# competing node type while still documenting intent at every call site.
CommonModelNode = Any


class SemanticRole(str, enum.Enum):
    """Standard semantic roles the query engine understands ({p056})."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"


STANDARD_SEMANTIC_ROLES: Tuple[SemanticRole, ...] = (
    SemanticRole.FUNCTION,
    SemanticRole.METHOD,
    SemanticRole.CLASS,
    SemanticRole.MODULE,
)


class SemanticRoleMapping:
    """Declarative node-type -> semantic-role map published by a plugin.

    ``node_type_to_role`` keys are the plugin's own backend/common node-type
    strings (e.g. ``"FunctionDef"``); values are one of
    :class:`SemanticRole`. A format that has no construct for a given
    standard role (e.g. a format without methods) simply contributes no
    entry mapping to that role -- :meth:`roles_for` then returns an empty
    tuple for it rather than raising, satisfying the "empty results for
    inapplicable roles" requirement of {p056}.
    """

    __slots__ = ("_node_type_to_role",)

    def __init__(self, node_type_to_role: Mapping[str, SemanticRole]) -> None:
        self._node_type_to_role: Mapping[str, SemanticRole] = dict(node_type_to_role)

    @property
    def node_type_to_role(self) -> Mapping[str, SemanticRole]:
        """The full declared node-type -> semantic-role dict."""

        return self._node_type_to_role

    def roles_for(self, role: SemanticRole) -> Tuple[str, ...]:
        """Return the node-type strings mapped to ``role``.

        Returns an empty tuple -- never raises -- when the format has no
        node type mapped to ``role``, including when ``role`` is one of the
        standard roles this format simply does not model.
        """

        return tuple(
            node_type
            for node_type, mapped_role in self._node_type_to_role.items()
            if mapped_role == role
        )


class FormatPluginMetadata:
    """Static identity and capability surface of a format plugin ({p055}, {p056}).

    ``capabilities`` is a declarative, introspectable dict a plugin exposes
    without instantiating any translator machinery; it must at minimum be
    able to advertise semantic-role-mapping support (for example via a
    ``"semantic_role_mapping"`` entry mirroring
    :meth:`FormatPluginContract.semantic_role_mapping`), but the method call
    remains the authoritative source of the live mapping. This class carries
    no behavior beyond that of a plain, immutable value holder.
    """

    __slots__ = (
        "format_id",
        "aliases",
        "file_extensions",
        "plugin_version",
        "contract_version",
        "capabilities",
    )

    def __init__(
        self,
        *,
        format_id: str,
        aliases: Tuple[str, ...],
        file_extensions: Tuple[str, ...],
        plugin_version: str,
        contract_version: str,
        capabilities: Mapping[str, Any],
    ) -> None:
        self.format_id = format_id
        self.aliases = tuple(aliases)
        self.file_extensions = tuple(file_extensions)
        self.plugin_version = plugin_version
        self.contract_version = contract_version
        self.capabilities = dict(capabilities)


class UnsupportedTranslationError(Exception):
    """Raised when a structure has no mappable translation ({p049}).

    Carries the offending ``node_type`` and the ``format_id`` of the plugin
    that could not perform the translation, per the contract's error
    interface. ``error_code`` is always
    :attr:`ErrorCode.UNSUPPORTED_TRANSLATION`; silent node loss is never an
    acceptable alternative to raising this error.
    """

    error_code: ErrorCode = ErrorCode.UNSUPPORTED_TRANSLATION

    def __init__(self, *, node_type: str, format_id: str, message: str = "") -> None:
        self.node_type = node_type
        self.format_id = format_id
        super().__init__(
            message
            or f"format '{format_id}' cannot translate node type {node_type!r}"
        )


class FormatPluginContractError(Exception):
    """Raised when a plugin violates the contract boundary itself ({p057}, {p058}).

    Distinct from :class:`UnsupportedTranslationError`: this covers contract
    violations such as returning an external AST/CST where only common
    nodes or a fallback string are permitted, an incompatible
    ``contract_version``, or any other breach of the interface defined
    below. Carries the ``plugin_id`` that violated the contract and the
    specific ``error_code`` describing the violation.
    """

    def __init__(
        self,
        *,
        plugin_id: str,
        error_code: ErrorCode = ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
        message: str = "",
    ) -> None:
        self.plugin_id = plugin_id
        self.error_code = error_code
        super().__init__(
            message or f"plugin '{plugin_id}' contract violation: {error_code.value}"
        )


class FormatPluginContract(abc.ABC):
    """Abstract boundary every concrete format plugin must implement.

    No plugin selection, registry, or entry-point discovery lives here
    ({p055}, {p059}, {p101} are out of scope for this file) -- only the
    shape a single plugin must expose once it has already been resolved.
    """

    @property
    @abc.abstractmethod
    def metadata(self) -> FormatPluginMetadata:
        """Return this plugin's static identity and capability surface."""

        raise NotImplementedError

    @abc.abstractmethod
    def parse_document(
        self, source: str, options: Mapping[str, Any]
    ) -> CommonModelNode:
        """Parse a full document's source text into common-model nodes.

        Internally runs the parser-library representation through the same
        import translator used by :meth:`import_to_common` ({p056}); the
        caller never sees the intermediate parser-library tree. Must raise
        :class:`FormatPluginContractError` (not return a partial or
        sentinel result) if the plugin cannot complete the pipeline for a
        reason other than a classified content-parse failure.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def import_external_tree(
        self, external_tree: Any, options: Mapping[str, Any]
    ) -> CommonModelNode:
        """Translate an already-parsed external AST/CST into common nodes.

        ``external_tree`` is the parser-library's own representation,
        obtained by the caller through means outside this contract (e.g. an
        already-parsed backend object). This method must return only
        common-model nodes: the external tree itself must never be
        returned, wrapped, or otherwise exposed to the caller.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def parse_fragment(
        self, fragment: str, options: Mapping[str, Any]
    ) -> Union[CommonModelNode, str]:
        """Parse a local code fragment, reusing the import translator.

        Returns common-model nodes on a recognized structure. When the
        fragment contains no recognized structure, returns a plain ``str``
        (conventionally the fragment's own text, or a diagnostic string) to
        signal "no structure" -- never an external AST/CST object and never
        ``None`` used to mean the same thing.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def import_to_common(
        self, external_representation: Any, options: Mapping[str, Any]
    ) -> CommonModelNode:
        """Translate a parser-library representation into common nodes.

        This is the single input translator shared by ``parse_document``,
        ``import_external_tree``, and ``parse_fragment`` ({p056}, {p057}).
        Must raise :class:`UnsupportedTranslationError` for a construct with
        no mappable common-model equivalent, carrying the offending
        ``node_type`` and this plugin's ``format_id``.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def export_from_common(
        self, nodes: CommonModelNode, options: Mapping[str, Any]
    ) -> Any:
        """Translate common-model nodes into this plugin's backend representation.

        The returned value is backend-specific (e.g. a parser library's own
        tree/object form) and is only ever consumed by this same plugin's
        :meth:`generate_output`. Must raise
        :class:`UnsupportedTranslationError` for a common-model construct
        this format cannot represent.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def generate_output(
        self, target: Union[CommonModelNode, Any], options: Mapping[str, Any]
    ) -> Union[str, bytes]:
        """Produce final output text or bytes for ``target``.

        ``target`` is either common-model nodes (in which case this method
        is responsible for running :meth:`export_from_common` internally)
        or an already backend-exported representation, per the plugin's own
        documented facade choice ({p056} permits combining stages behind a
        facade as long as the boundary stays testable). Must raise
        :class:`FormatPluginContractError` if generation cannot complete
        after a successful export.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def semantic_role_mapping(self) -> SemanticRoleMapping:
        """Return this plugin's declarative node-type -> semantic-role map.

        Must cover the standard roles in :data:`STANDARD_SEMANTIC_ROLES`
        (function, method, class, module) to the extent this format models
        them; a role this format has no construct for is simply absent from
        the mapping, which callers observe as
        ``SemanticRoleMapping.roles_for(role) == ()`` rather than an error.
        """

        raise NotImplementedError
