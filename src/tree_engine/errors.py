from __future__ import annotations

import enum
import types


class ErrorLayer(str, enum.Enum):
    """Error layer enumeration per frozen HRS fragment {p023}."""
    CORE = "CORE"
    PLUGIN = "PLUGIN"
    STORAGE = "STORAGE"


class ErrorCode(str, enum.Enum):
    """
    Stable error-code catalog per frozen HRS fragment {p023}.

    This catalog defines all error codes produced by the tree engine.
    FORMAT_CONTENT_PARSE_FAILED is the only code with a permitted plain-text fallback.
    No exception classes are defined in this file; the typed exception hierarchy
    built on this catalog is delivered later by the public-facade step tied to concept C-021.
    """
    NODE_NOT_FOUND = "NODE_NOT_FOUND"
    NODE_ID_CONFLICT = "NODE_ID_CONFLICT"
    SHORT_ID_CONFLICT = "SHORT_ID_CONFLICT"
    DOCUMENT_VERSION_CONFLICT = "DOCUMENT_VERSION_CONFLICT"
    INVALID_SELECTOR = "INVALID_SELECTOR"
    INVALID_POSITION = "INVALID_POSITION"
    INVALID_PARENT_TYPE = "INVALID_PARENT_TYPE"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
    FORMAT_UNKNOWN_EXTENSION = "FORMAT_UNKNOWN_EXTENSION"
    FORMAT_EXTENSION_CONFLICT = "FORMAT_EXTENSION_CONFLICT"
    FORMAT_PLUGIN_NOT_FOUND = "FORMAT_PLUGIN_NOT_FOUND"
    PLUGIN_CAPABILITY_NOT_SUPPORTED = "PLUGIN_CAPABILITY_NOT_SUPPORTED"
    FORMAT_CONTENT_PARSE_FAILED = "FORMAT_CONTENT_PARSE_FAILED"
    FORMAT_FRAGMENT_PARSE_FAILED = "FORMAT_FRAGMENT_PARSE_FAILED"
    FORMAT_PLUGIN_CONTRACT_ERROR = "FORMAT_PLUGIN_CONTRACT_ERROR"
    UNSUPPORTED_TRANSLATION = "UNSUPPORTED_TRANSLATION"
    TREE_PAYLOAD_INVALID = "TREE_PAYLOAD_INVALID"
    TREE_SCHEMA_UNSUPPORTED = "TREE_SCHEMA_UNSUPPORTED"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    CONCURRENT_SOURCE_MODIFICATION = "CONCURRENT_SOURCE_MODIFICATION"
    CONCURRENT_TREE_MODIFICATION = "CONCURRENT_TREE_MODIFICATION"
    STORAGE_IO_ERROR = "STORAGE_IO_ERROR"


_ERROR_CODE_LAYER_MAP = {
    ErrorCode.NODE_NOT_FOUND: ErrorLayer.CORE,
    ErrorCode.NODE_ID_CONFLICT: ErrorLayer.CORE,
    ErrorCode.SHORT_ID_CONFLICT: ErrorLayer.CORE,
    ErrorCode.DOCUMENT_VERSION_CONFLICT: ErrorLayer.CORE,
    ErrorCode.INVALID_SELECTOR: ErrorLayer.CORE,
    ErrorCode.INVALID_POSITION: ErrorLayer.CORE,
    ErrorCode.INVALID_PARENT_TYPE: ErrorLayer.CORE,
    ErrorCode.CYCLE_DETECTED: ErrorLayer.CORE,
    ErrorCode.UNRESOLVED_REFERENCE: ErrorLayer.CORE,
    ErrorCode.CONCURRENT_TREE_MODIFICATION: ErrorLayer.CORE,
    ErrorCode.FORMAT_UNKNOWN_EXTENSION: ErrorLayer.PLUGIN,
    ErrorCode.FORMAT_EXTENSION_CONFLICT: ErrorLayer.PLUGIN,
    ErrorCode.FORMAT_PLUGIN_NOT_FOUND: ErrorLayer.PLUGIN,
    ErrorCode.PLUGIN_CAPABILITY_NOT_SUPPORTED: ErrorLayer.PLUGIN,
    ErrorCode.FORMAT_CONTENT_PARSE_FAILED: ErrorLayer.PLUGIN,
    ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED: ErrorLayer.PLUGIN,
    ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR: ErrorLayer.PLUGIN,
    ErrorCode.UNSUPPORTED_TRANSLATION: ErrorLayer.PLUGIN,
    ErrorCode.TREE_PAYLOAD_INVALID: ErrorLayer.STORAGE,
    ErrorCode.TREE_SCHEMA_UNSUPPORTED: ErrorLayer.STORAGE,
    ErrorCode.CHECKSUM_MISMATCH: ErrorLayer.STORAGE,
    ErrorCode.CONCURRENT_SOURCE_MODIFICATION: ErrorLayer.STORAGE,
    ErrorCode.STORAGE_IO_ERROR: ErrorLayer.STORAGE,
}

# Totality guard: verify that every ErrorCode is mapped exactly once
_all_codes = set(ErrorCode)
_mapped_codes = set(_ERROR_CODE_LAYER_MAP.keys())
assert _mapped_codes == _all_codes, (
    f"ErrorCode mapping is not total: missing {_all_codes - _mapped_codes}, "
    f"extra {_mapped_codes - _all_codes}"
)

ERROR_CODE_LAYER = types.MappingProxyType(_ERROR_CODE_LAYER_MAP)


def error_layer(code: ErrorCode) -> ErrorLayer:
    """
    Return the layer (CORE, PLUGIN, or STORAGE) that owns the given error code.

    Args:
        code: An ErrorCode member.

    Returns:
        The ErrorLayer that owns this code.
    """
    return ERROR_CODE_LAYER[code]
