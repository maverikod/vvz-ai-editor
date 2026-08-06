"""
Tests for the stable error-code catalog in src/tree_engine/errors.py.

Validates ErrorCode (str enum), ErrorLayer (CORE/PLUGIN/STORAGE), the
immutable ERROR_CODE_LAYER mapping, and the error_layer() helper, per
frozen HRS fragment {p023}.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re

import pytest

from tree_engine.errors import ErrorCode, ErrorLayer, ERROR_CODE_LAYER, error_layer

REQUIRED_CODE_NAMES = {
    "NODE_NOT_FOUND",
    "NODE_ID_CONFLICT",
    "SHORT_ID_CONFLICT",
    "DOCUMENT_VERSION_CONFLICT",
    "INVALID_SELECTOR",
    "INVALID_POSITION",
    "INVALID_PARENT_TYPE",
    "CYCLE_DETECTED",
    "UNRESOLVED_REFERENCE",
    "FORMAT_UNKNOWN_EXTENSION",
    "FORMAT_EXTENSION_CONFLICT",
    "FORMAT_PLUGIN_NOT_FOUND",
    "PLUGIN_CAPABILITY_NOT_SUPPORTED",
    "FORMAT_CONTENT_PARSE_FAILED",
    "FORMAT_FRAGMENT_PARSE_FAILED",
    "FORMAT_PLUGIN_CONTRACT_ERROR",
    "UNSUPPORTED_TRANSLATION",
    "TREE_PAYLOAD_INVALID",
    "TREE_SCHEMA_UNSUPPORTED",
    "CHECKSUM_MISMATCH",
    "CONCURRENT_SOURCE_MODIFICATION",
    "CONCURRENT_TREE_MODIFICATION",
    "STORAGE_IO_ERROR",
}

_VALUE_FORMAT_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def test_all_required_codes_present() -> None:
    actual_names = {member.name for member in ErrorCode}
    assert actual_names == REQUIRED_CODE_NAMES, (
        f"symmetric difference: {actual_names ^ REQUIRED_CODE_NAMES}"
    )


def test_error_code_values_unique_and_stable_format() -> None:
    values = [member.value for member in ErrorCode]
    for member in ErrorCode:
        assert isinstance(member.value, str)
        assert member.value != ""
        assert member.value == member.name
        assert _VALUE_FORMAT_RE.match(member.value), member.value
    assert len(values) == len(set(values))


def test_layer_mapping_total() -> None:
    assert set(ERROR_CODE_LAYER.keys()) == set(ErrorCode)
    seen = []
    for code, layer in ERROR_CODE_LAYER.items():
        assert isinstance(layer, ErrorLayer)
        assert code not in seen
        seen.append(code)


@pytest.mark.parametrize(
    ("code", "expected_layer"),
    [
        (ErrorCode.NODE_NOT_FOUND, ErrorLayer.CORE),
        (ErrorCode.CYCLE_DETECTED, ErrorLayer.CORE),
        (ErrorCode.CONCURRENT_TREE_MODIFICATION, ErrorLayer.CORE),
        (ErrorCode.FORMAT_PLUGIN_NOT_FOUND, ErrorLayer.PLUGIN),
        (ErrorCode.UNSUPPORTED_TRANSLATION, ErrorLayer.PLUGIN),
        (ErrorCode.TREE_SCHEMA_UNSUPPORTED, ErrorLayer.STORAGE),
        (ErrorCode.CHECKSUM_MISMATCH, ErrorLayer.STORAGE),
        (ErrorCode.CONCURRENT_SOURCE_MODIFICATION, ErrorLayer.STORAGE),
        (ErrorCode.STORAGE_IO_ERROR, ErrorLayer.STORAGE),
    ],
)
def test_layer_spot_attributions(code: ErrorCode, expected_layer: ErrorLayer) -> None:
    assert ERROR_CODE_LAYER[code] is expected_layer


def test_error_layer_helper_agrees() -> None:
    for code in ErrorCode:
        assert error_layer(code) is ERROR_CODE_LAYER[code]


def test_mapping_immutable() -> None:
    with pytest.raises(TypeError):
        ERROR_CODE_LAYER[ErrorCode.NODE_NOT_FOUND] = ErrorLayer.STORAGE
