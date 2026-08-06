"""Tests for the tree_engine typed exception hierarchy (G-027/T-001/A-003).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Subject under test: ``tree_engine.exceptions`` together with the frozen
error-code catalog it is built on, ``tree_engine.errors``.

NOTE ON TARGET FILE DIVERGENCE: the step's literal target path is
``tests/test_exceptions.py``. That path is already occupied by a legacy
suite covering ``ai_editor.core.exceptions`` (AIEditorError,
ValidationError, RefactoringError, ...), which predates this plan and must
not be touched, weakened, or overwritten. This suite is therefore placed in
the sibling file ``tests/test_tree_engine_exceptions.py`` instead, so both
suites keep running independently.

These tests deliberately drive the hierarchy through introspection
(``ErrorCode`` iteration, ``CODE_TO_EXCEPTION`` iteration) rather than a
hand-copied roster of class names, so coverage does not silently stop when
a new code/class pair is added later.

``tree_engine`` is a standalone package: nothing here imports ``ai_editor``.
"""

from __future__ import annotations

import pytest

from tree_engine.errors import ErrorCode, ErrorLayer, ERROR_CODE_LAYER, error_layer
from tree_engine.exceptions import (
    TreeEngineException,
    CoreLayerException,
    PluginLayerException,
    StorageLayerException,
    FormatContentParseFailed,
    FormatPluginContractError,
    CODE_TO_EXCEPTION,
    exception_for_code,
)

# The legacy, unrelated convention this hierarchy must not be confused
# with: a plain ``Exception`` in the plugin-contract module that predates
# the typed hierarchy and exposes its code under ``.error_code``, not
# ``.code``. Aliased distinctly to keep the two classes visually apart.
from tree_engine.plugins.contract import (
    FormatPluginContractError as LegacyContractError,
)

_LAYER_BASE = {
    ErrorLayer.CORE: CoreLayerException,
    ErrorLayer.PLUGIN: PluginLayerException,
    ErrorLayer.STORAGE: StorageLayerException,
}


def _instantiate(cls):
    return cls("boom", extra="detail")


# ---------------------------------------------------------------------------
# Catalog completeness: one class per code, no gaps, no duplicates.
# ---------------------------------------------------------------------------


def test_catalog_completeness_one_class_per_code():
    for code in ErrorCode:
        assert code in CODE_TO_EXCEPTION, f"{code} has no exception class"
        cls = CODE_TO_EXCEPTION[code]
        assert cls.code is code, (
            f"{cls.__name__}.code round-trips to {cls.code!r}, expected {code!r}"
        )
        assert exception_for_code(code) is cls


def test_no_missing_or_duplicate_codes():
    all_codes = set(ErrorCode)
    mapped_codes = set(CODE_TO_EXCEPTION.keys())
    assert mapped_codes == all_codes
    # One class per code: as many classes as codes, and every class is
    # unique (a dict cannot itself hold duplicate keys, so uniqueness is
    # verified on the class side instead).
    classes = list(CODE_TO_EXCEPTION.values())
    assert len(classes) == len(set(classes)) == len(all_codes)


def test_every_leaf_is_a_tree_engine_exception_subclass():
    for cls in CODE_TO_EXCEPTION.values():
        assert issubclass(cls, TreeEngineException)
        assert issubclass(cls, Exception)


# ---------------------------------------------------------------------------
# Layer attribution: derived, matches ERROR_CODE_LAYER, never stored twice.
# ---------------------------------------------------------------------------


def test_layer_attribution_matches_mapping():
    for code, cls in CODE_TO_EXCEPTION.items():
        instance = _instantiate(cls)
        assert instance.layer == ERROR_CODE_LAYER[code] == error_layer(code)


def test_layer_matches_structural_intermediate_base():
    """A leaf's derived layer must agree with which of the three
    per-layer intermediates it actually inherits from."""
    for code, cls in CODE_TO_EXCEPTION.items():
        expected_base = _LAYER_BASE[ERROR_CODE_LAYER[code]]
        assert issubclass(cls, expected_base), (
            f"{cls.__name__} has layer {ERROR_CODE_LAYER[code]!r} but does not "
            f"inherit {expected_base.__name__}"
        )


def test_layer_is_derived_not_stored():
    """``layer`` must be a computed property, never an instance attribute
    that could desynchronize from ``ERROR_CODE_LAYER``."""
    assert isinstance(TreeEngineException.__dict__["layer"], property)
    instance = _instantiate(FormatContentParseFailed)
    assert "layer" not in vars(instance)
    assert "_layer" not in vars(instance)
    # Only ``details`` (plus whatever BaseException itself stores) may be
    # instance state; layer is always recomputed from ``.code``.
    assert set(vars(instance).keys()) == {"details"}


def test_storage_codes_are_not_core():
    storage_codes = {
        ErrorCode.TREE_PAYLOAD_INVALID,
        ErrorCode.TREE_SCHEMA_UNSUPPORTED,
        ErrorCode.CHECKSUM_MISMATCH,
        ErrorCode.CONCURRENT_SOURCE_MODIFICATION,
        ErrorCode.STORAGE_IO_ERROR,
    }
    for code in storage_codes:
        assert ERROR_CODE_LAYER[code] is ErrorLayer.STORAGE
        assert issubclass(CODE_TO_EXCEPTION[code], StorageLayerException)
        assert not issubclass(CODE_TO_EXCEPTION[code], CoreLayerException)


# ---------------------------------------------------------------------------
# Layer-level catching: each intermediate catches exactly its own leaves.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layer", list(ErrorLayer))
def test_layer_base_catches_only_its_own_layer(layer):
    base = _LAYER_BASE[layer]
    own_codes = {c for c, l in ERROR_CODE_LAYER.items() if l is layer}
    foreign_codes = set(ErrorCode) - own_codes
    assert own_codes, f"no codes attributed to {layer}"

    for code in own_codes:
        cls = CODE_TO_EXCEPTION[code]
        with pytest.raises(base):
            raise _instantiate(cls)

    for code in foreign_codes:
        cls = CODE_TO_EXCEPTION[code]
        with pytest.raises(TreeEngineException) as excinfo:
            try:
                raise _instantiate(cls)
            except base:
                pytest.fail(
                    f"{base.__name__} incorrectly caught foreign-layer "
                    f"exception {cls.__name__} ({code})"
                )
        assert not isinstance(excinfo.value, base)


def test_core_base_catches_core_only():
    with pytest.raises(CoreLayerException):
        raise CODE_TO_EXCEPTION[ErrorCode.NODE_NOT_FOUND]("missing")
    with pytest.raises(TreeEngineException):
        try:
            raise CODE_TO_EXCEPTION[ErrorCode.STORAGE_IO_ERROR]("io")
        except CoreLayerException:
            pytest.fail("CoreLayerException must not catch a storage exception")


def test_plugin_base_catches_plugin_only():
    with pytest.raises(PluginLayerException):
        raise CODE_TO_EXCEPTION[ErrorCode.FORMAT_UNKNOWN_EXTENSION]("ext")
    with pytest.raises(TreeEngineException):
        try:
            raise CODE_TO_EXCEPTION[ErrorCode.NODE_ID_CONFLICT]("conflict")
        except PluginLayerException:
            pytest.fail("PluginLayerException must not catch a core exception")


def test_storage_base_catches_storage_only():
    with pytest.raises(StorageLayerException):
        raise CODE_TO_EXCEPTION[ErrorCode.CHECKSUM_MISMATCH]("checksum")
    with pytest.raises(TreeEngineException):
        try:
            raise CODE_TO_EXCEPTION[ErrorCode.FORMAT_PLUGIN_NOT_FOUND]("missing")
        except StorageLayerException:
            pytest.fail("StorageLayerException must not catch a plugin exception")


def test_tree_engine_exception_catches_every_leaf():
    for cls in CODE_TO_EXCEPTION.values():
        with pytest.raises(TreeEngineException):
            raise _instantiate(cls)


def test_intermediate_layers_do_not_catch_each_other():
    assert not issubclass(CoreLayerException, PluginLayerException)
    assert not issubclass(CoreLayerException, StorageLayerException)
    assert not issubclass(PluginLayerException, CoreLayerException)
    assert not issubclass(PluginLayerException, StorageLayerException)
    assert not issubclass(StorageLayerException, CoreLayerException)
    assert not issubclass(StorageLayerException, PluginLayerException)


# ---------------------------------------------------------------------------
# Exact-code catching: a leaf catches only itself, not its siblings.
# ---------------------------------------------------------------------------


def test_exact_code_catching():
    for code, cls in CODE_TO_EXCEPTION.items():
        with pytest.raises(cls):
            raise _instantiate(cls)

        for other_code, other_cls in CODE_TO_EXCEPTION.items():
            if other_cls is cls:
                continue
            # Sibling leaves must not be related by inheritance in either
            # direction, so catching one specific leaf can never silently
            # swallow another specific leaf.
            assert not issubclass(cls, other_cls)
            assert not issubclass(other_cls, cls)


def test_inheritance_enforces_layer_isolation():
    core_leaf = CODE_TO_EXCEPTION[ErrorCode.CYCLE_DETECTED]
    plugin_leaf = CODE_TO_EXCEPTION[ErrorCode.UNSUPPORTED_TRANSLATION]
    storage_leaf = CODE_TO_EXCEPTION[ErrorCode.TREE_SCHEMA_UNSUPPORTED]

    with pytest.raises(TreeEngineException):
        try:
            raise _instantiate(plugin_leaf)
        except core_leaf:
            pytest.fail("a core leaf must not catch a plugin leaf")

    with pytest.raises(TreeEngineException):
        try:
            raise _instantiate(storage_leaf)
        except plugin_leaf:
            pytest.fail("a plugin leaf must not catch a storage leaf")

    # But everything is still a TreeEngineException.
    for leaf in (core_leaf, plugin_leaf, storage_leaf):
        with pytest.raises(TreeEngineException):
            raise _instantiate(leaf)


# ---------------------------------------------------------------------------
# Attribute persistence through raise/catch, message shape, details.
# ---------------------------------------------------------------------------


def test_attributes_persist_through_raise_catch():
    for code, cls in CODE_TO_EXCEPTION.items():
        try:
            raise cls("something failed", node_id="n-1", extra=42)
        except TreeEngineException as caught:
            assert caught.code is code
            assert caught.layer == ERROR_CODE_LAYER[code]
            assert caught.details == {"node_id": "n-1", "extra": 42}
            assert str(caught).startswith(f"[{code.value}]")
        else:
            pytest.fail(f"{cls.__name__} did not raise")


def test_message_renders_with_code_prefix_even_when_empty():
    exc = CODE_TO_EXCEPTION[ErrorCode.NODE_NOT_FOUND]()
    assert str(exc) == f"[{ErrorCode.NODE_NOT_FOUND.value}]"


def test_details_default_to_empty_mapping():
    exc = CODE_TO_EXCEPTION[ErrorCode.INVALID_SELECTOR]("bad selector")
    assert exc.details == {}


# ---------------------------------------------------------------------------
# The single authorized plain-text fallback.
# ---------------------------------------------------------------------------


def test_format_content_parse_failed_fallback_authorized():
    assert FormatContentParseFailed.plain_text_fallback_permitted is True
    instance = _instantiate(FormatContentParseFailed)
    assert instance.plain_text_fallback_permitted is True


def test_fallback_flag_false_on_every_other_class():
    permitted = [
        cls
        for cls in CODE_TO_EXCEPTION.values()
        if cls.plain_text_fallback_permitted
    ]
    assert permitted == [FormatContentParseFailed], (
        "plain_text_fallback_permitted leaked to an unauthorized class: "
        f"{[c.__name__ for c in permitted]}"
    )


def test_fallback_flag_false_on_base_and_intermediates():
    assert TreeEngineException.plain_text_fallback_permitted is False
    assert CoreLayerException.plain_text_fallback_permitted is False
    assert PluginLayerException.plain_text_fallback_permitted is False
    assert StorageLayerException.plain_text_fallback_permitted is False


# ---------------------------------------------------------------------------
# ``.code`` is the canonical attribute; the legacy ``.error_code``
# convention used elsewhere in the codebase must not leak into this
# typed hierarchy.
# ---------------------------------------------------------------------------


def test_code_is_the_canonical_attribute_not_error_code():
    for cls in CODE_TO_EXCEPTION.values():
        instance = _instantiate(cls)
        assert hasattr(instance, "code")
        assert not hasattr(instance, "error_code"), (
            f"{cls.__name__} unexpectedly exposes a legacy .error_code "
            "attribute; the typed hierarchy contract is .code only"
        )


def test_typed_and_legacy_contract_error_are_distinct_classes():
    """``tree_engine.exceptions.FormatPluginContractError`` (this
    hierarchy, ``.code``) must never be confused with
    ``tree_engine.plugins.contract.FormatPluginContractError`` (the
    older, unrelated plain-``Exception`` convention, ``.error_code``)."""
    assert FormatPluginContractError is not LegacyContractError
    assert not issubclass(FormatPluginContractError, LegacyContractError)
    assert not issubclass(LegacyContractError, FormatPluginContractError)

    typed = _instantiate(FormatPluginContractError)
    assert typed.code is ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert not hasattr(typed, "error_code")

    legacy = LegacyContractError(
        plugin_id="demo", error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    )
    assert legacy.error_code is ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert not hasattr(legacy, "code")
    assert not isinstance(legacy, TreeEngineException)
