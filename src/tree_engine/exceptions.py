"""Typed public-API exception hierarchy for the tree engine.

Built strictly on top of the frozen error-code catalog in
:mod:`tree_engine.errors` (``ErrorCode``, ``ErrorLayer``,
``ERROR_CODE_LAYER``). This module never redeclares a code and never
restates layer attribution: every leaf class below fixes only its
``code`` class attribute, and ``layer`` is always derived, at access
time, from ``ERROR_CODE_LAYER`` -- so the catalog and this hierarchy can
never desynchronize. Per {p023}, ``FormatContentParseFailed`` is the
single exception permitted to carry the plain-text fallback flag; no
other class in this module exposes any fallback or masking path.
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping, Type

from tree_engine.errors import ErrorCode, ErrorLayer, ERROR_CODE_LAYER

__all__ = [
    "TreeEngineException",
    "CoreLayerException",
    "PluginLayerException",
    "StorageLayerException",
    "NodeNotFound",
    "NodeIdConflict",
    "ShortIdConflict",
    "DocumentVersionConflict",
    "InvalidSelector",
    "InvalidPosition",
    "InvalidParentType",
    "CycleDetected",
    "UnresolvedReference",
    "ConcurrentTreeModification",
    "FormatUnknownExtension",
    "FormatExtensionConflict",
    "FormatPluginNotFound",
    "PluginCapabilityNotSupported",
    "FormatContentParseFailed",
    "FormatFragmentParseFailed",
    "FormatPluginContractError",
    "UnsupportedTranslation",
    "TreePayloadInvalid",
    "TreeSchemaUnsupported",
    "ChecksumMismatch",
    "ConcurrentSourceModification",
    "StorageIOError",
    "CODE_TO_EXCEPTION",
    "exception_for_code",
]


class TreeEngineException(Exception):
    """Common base of every exception this module defines.

    ``code`` is the stable :class:`~tree_engine.errors.ErrorCode` each
    concrete leaf fixes as a class attribute -- never re-derived, never
    guessed from the message. ``layer`` is never stored a second time:
    it is looked up, on every access, in the frozen
    :data:`~tree_engine.errors.ERROR_CODE_LAYER` mapping keyed by
    ``code``, so a leaf's declared layer and its structural base (see
    the three per-layer intermediates below) cannot drift apart.
    """

    code: ClassVar[ErrorCode]

    #: Only ``FormatContentParseFailed`` overrides this to ``True``; it is
    #: the sole class in this hierarchy allowed to advertise a permitted
    #: plain-text fallback per {p023}. No other subclass may set it.
    plain_text_fallback_permitted: ClassVar[bool] = False

    def __init__(self, message: str = "", **details: Any) -> None:
        self.details: Mapping[str, Any] = dict(details)
        rendered = f"[{self.code.value}] {message}" if message else f"[{self.code.value}]"
        super().__init__(rendered)

    @property
    def layer(self) -> ErrorLayer:
        """The owning layer (CORE, PLUGIN, or STORAGE), from ``ERROR_CODE_LAYER``."""
        return ERROR_CODE_LAYER[self.code]


class CoreLayerException(TreeEngineException):
    """Intermediate base for every leaf whose code attributes to ``ErrorLayer.CORE``."""


class PluginLayerException(TreeEngineException):
    """Intermediate base for every leaf whose code attributes to ``ErrorLayer.PLUGIN``."""


class StorageLayerException(TreeEngineException):
    """Intermediate base for every leaf whose code attributes to ``ErrorLayer.STORAGE``."""


# --------------------------------------------------------------------------
# Core-layer leaves (10 codes)
# --------------------------------------------------------------------------


class NodeNotFound(CoreLayerException):
    """An address resolves to no node in the current document."""

    code = ErrorCode.NODE_NOT_FOUND


class NodeIdConflict(CoreLayerException):
    """A new or incoming ``node_id`` collides with an existing one."""

    code = ErrorCode.NODE_ID_CONFLICT


class ShortIdConflict(CoreLayerException):
    """A ``short_id`` collides with an existing entry in the document map."""

    code = ErrorCode.SHORT_ID_CONFLICT


class DocumentVersionConflict(CoreLayerException):
    """An operation's ``expected_version`` does not match the document's."""

    code = ErrorCode.DOCUMENT_VERSION_CONFLICT


class InvalidSelector(CoreLayerException):
    """A query/drill_down selector is malformed or cannot be applied."""

    code = ErrorCode.INVALID_SELECTOR


class InvalidPosition(CoreLayerException):
    """A requested insertion/move position is out of range or malformed."""

    code = ErrorCode.INVALID_POSITION


class InvalidParentType(CoreLayerException):
    """A parent node's kind cannot legally host the given child."""

    code = ErrorCode.INVALID_PARENT_TYPE


class CycleDetected(CoreLayerException):
    """An operation would introduce a cycle in the tree/reference graph."""

    code = ErrorCode.CYCLE_DETECTED


class UnresolvedReference(CoreLayerException):
    """A reference cannot be resolved to a live node."""

    code = ErrorCode.UNRESOLVED_REFERENCE


class ConcurrentTreeModification(CoreLayerException):
    """A post-mutation integrity check found an out-of-band tree change."""

    code = ErrorCode.CONCURRENT_TREE_MODIFICATION


# --------------------------------------------------------------------------
# Plugin-layer leaves (8 codes)
# --------------------------------------------------------------------------


class FormatUnknownExtension(PluginLayerException):
    """No registered plugin claims the given file extension."""

    code = ErrorCode.FORMAT_UNKNOWN_EXTENSION


class FormatExtensionConflict(PluginLayerException):
    """Two or more registered plugins claim the same file extension."""

    code = ErrorCode.FORMAT_EXTENSION_CONFLICT


class FormatPluginNotFound(PluginLayerException):
    """``format_id`` does not resolve to any registered plugin."""

    code = ErrorCode.FORMAT_PLUGIN_NOT_FOUND


class PluginCapabilityNotSupported(PluginLayerException):
    """The resolved plugin does not support the requested capability."""

    code = ErrorCode.PLUGIN_CAPABILITY_NOT_SUPPORTED


class FormatContentParseFailed(PluginLayerException):
    """A plugin failed to parse document content.

    The single exception in this hierarchy permitted to carry the
    authorized plain-text fallback per {p023}: ``plain_text_fallback_permitted``
    is fixed to ``True`` here and nowhere else.
    """

    code = ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    plain_text_fallback_permitted: ClassVar[bool] = True


class FormatFragmentParseFailed(PluginLayerException):
    """A plugin failed to parse an inserted/replaced fragment."""

    code = ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED


class FormatPluginContractError(PluginLayerException):
    """A plugin violated the format-plugin contract boundary itself."""

    code = ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR


class UnsupportedTranslation(PluginLayerException):
    """A structure has no mappable translation in the target format."""

    code = ErrorCode.UNSUPPORTED_TRANSLATION


# --------------------------------------------------------------------------
# Storage-layer leaves (5 codes)
# --------------------------------------------------------------------------


class TreePayloadInvalid(StorageLayerException):
    """A loaded tree payload fails structural validation."""

    code = ErrorCode.TREE_PAYLOAD_INVALID


class TreeSchemaUnsupported(StorageLayerException):
    """A loaded payload declares a schema version storage cannot handle."""

    code = ErrorCode.TREE_SCHEMA_UNSUPPORTED


class ChecksumMismatch(StorageLayerException):
    """A stored artifact's checksum does not match its recorded value."""

    code = ErrorCode.CHECKSUM_MISMATCH


class ConcurrentSourceModification(StorageLayerException):
    """The on-disk source changed out from under an in-progress operation."""

    code = ErrorCode.CONCURRENT_SOURCE_MODIFICATION


class StorageIOError(StorageLayerException):
    """A file-system or I/O operation failed in the storage layer."""

    code = ErrorCode.STORAGE_IO_ERROR


# --------------------------------------------------------------------------
# Totality and consistency guards (mirrors the pattern in errors.py)
# --------------------------------------------------------------------------

_LAYER_INTERMEDIATE: Mapping[ErrorLayer, Type[TreeEngineException]] = {
    ErrorLayer.CORE: CoreLayerException,
    ErrorLayer.PLUGIN: PluginLayerException,
    ErrorLayer.STORAGE: StorageLayerException,
}

_ALL_EXCEPTIONS: tuple[Type[TreeEngineException], ...] = (
    NodeNotFound,
    NodeIdConflict,
    ShortIdConflict,
    DocumentVersionConflict,
    InvalidSelector,
    InvalidPosition,
    InvalidParentType,
    CycleDetected,
    UnresolvedReference,
    ConcurrentTreeModification,
    FormatUnknownExtension,
    FormatExtensionConflict,
    FormatPluginNotFound,
    PluginCapabilityNotSupported,
    FormatContentParseFailed,
    FormatFragmentParseFailed,
    FormatPluginContractError,
    UnsupportedTranslation,
    TreePayloadInvalid,
    TreeSchemaUnsupported,
    ChecksumMismatch,
    ConcurrentSourceModification,
    StorageIOError,
)

#: Exactly one exception class per ``ErrorCode`` member, built here rather
#: than declared class-by-class elsewhere, so any future drift between the
#: leaf set and the catalog fails loudly at import time.
CODE_TO_EXCEPTION: Mapping[ErrorCode, Type[TreeEngineException]] = {
    cls.code: cls for cls in _ALL_EXCEPTIONS
}

_all_codes = set(ErrorCode)
_mapped_codes = set(CODE_TO_EXCEPTION.keys())
assert _mapped_codes == _all_codes, (
    f"exception hierarchy is not total: missing {_all_codes - _mapped_codes}, "
    f"extra {_mapped_codes - _all_codes}"
)
assert len(_ALL_EXCEPTIONS) == len(CODE_TO_EXCEPTION), (
    "two or more leaf classes share the same ErrorCode"
)

for _cls in _ALL_EXCEPTIONS:
    _expected_layer = ERROR_CODE_LAYER[_cls.code]
    _expected_base = _LAYER_INTERMEDIATE[_expected_layer]
    assert issubclass(_cls, _expected_base), (
        f"{_cls.__name__} carries {_cls.code!r} (layer {_expected_layer!r}) "
        f"but does not inherit from {_expected_base.__name__}"
    )
del _cls, _expected_layer, _expected_base

_fallback_classes = [cls for cls in _ALL_EXCEPTIONS if cls.plain_text_fallback_permitted]
assert _fallback_classes == [FormatContentParseFailed], (
    "plain_text_fallback_permitted must be True for FormatContentParseFailed only, "
    f"found {[c.__name__ for c in _fallback_classes]}"
)
del _fallback_classes


def exception_for_code(code: ErrorCode) -> Type[TreeEngineException]:
    """Return the single exception class that represents ``code``."""
    return CODE_TO_EXCEPTION[code]
