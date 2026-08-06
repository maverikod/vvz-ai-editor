"""Registry tests for the format-plugin registry (concept C-010,
step G-020/T-001/A-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises ``tree_engine.plugins.registry.FormatPluginRegistry`` and the
module-level ``convert``/``generate_output`` facade against the REAL
merged format plugins -- ``PYTHON_FORMAT_PLUGIN``, ``BSL_FORMAT_PLUGIN``,
``PLAIN_TEXT_FORMAT_PLUGIN`` -- not toy doubles. A small local
``_MinimalContractPlugin`` fixture is used only where a failure mode needs
a candidate no single real plugin can exhibit by construction (real
plugins never collide with each other's ``format_id``/alias/extension,
and none carries a broken or incompatible ``contract_version``); that is
a fixture, never a mock of the registry itself.

Isolation: every test builds its own throw-away ``FormatPluginRegistry()``
and, where the public ``convert``/``generate_output`` facade is exercised,
always passes that instance explicitly as ``registry=`` -- the process-wide
default registry (``registry._DEFAULT_REGISTRY``) is never imported,
touched, or mutated anywhere in this file. No test therefore leaves any
state another test could observe; test order is provably irrelevant since
there is nothing shared to leak through.

Covered: (1) register/get/list/unregister round trip on a real plugin,
including the documented no-op re-``unregister``; (2) ``replace=True``
semantics -- an unflagged re-registration is rejected with the prior entry
left intact, an explicit ``replace=True`` swaps the entry; (3) registration
conflict detection on a colliding extension, a colliding alias, an empty
``format_id``, and an incompatible ``contract_version`` major, each
rejected before any index mutation; (4) lazy entry-point discovery through
a fake entry-point group -- the candidate is indexed without importing/
loading it, and ``.load()`` runs exactly once, on the first matching
``get_format_plugin`` call, never during scanning or listing; (5)
``get_format_plugin``/``list_format_plugins`` returning stable metadata for
every registered real plugin and raising the typed, ``ErrorCode``-carrying
``FormatPluginNotFoundError`` (never ``KeyError``) for an unknown id; (6)
``convert``/``generate_output`` propagating ``FormatPluginNotFoundError``
and ``UnsupportedTranslationError`` unmasked -- no plain-text or other
fallback is ever substituted for a translation failure.
"""

from __future__ import annotations

import pytest

from tree_engine.core.nodes import make_node
from tree_engine.errors import ErrorCode
from tree_engine.plugins.bsl.plugin import BSL_FORMAT_PLUGIN
from tree_engine.plugins.contract import FormatPluginMetadata, UnsupportedTranslationError
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN, PlainTextTree
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import (
    ENTRY_POINT_GROUP,
    FormatPluginNotFoundError,
    FormatPluginRegistry,
    PluginRegistrationError,
    convert,
    generate_output,
)


class _MinimalContractPlugin:
    """Bare-bones candidate exposing only ``metadata`` -- the one surface
    ``register_format_plugin``/its internal ``_validate_plugin`` actually
    inspects. Used solely to construct registration scenarios (a name/alias/
    extension collision, an empty ``format_id``, an incompatible
    ``contract_version``) that no two of the distinct real plugins can ever
    produce against each other, since each already owns a unique identity."""

    def __init__(
        self,
        *,
        format_id: str,
        aliases: tuple = (),
        file_extensions: tuple = (),
        plugin_version: str = "1.0.0",
        contract_version: str = "1.0.0",
    ) -> None:
        self.metadata = FormatPluginMetadata(
            format_id=format_id,
            aliases=aliases,
            file_extensions=file_extensions,
            plugin_version=plugin_version,
            contract_version=contract_version,
            capabilities={},
        )


class FakeEntryPoint:
    """Fake ``importlib.metadata.EntryPoint`` standing in for a real
    installed package's advertised entry point. Records how many times
    ``.load()`` actually ran, so the lazy-loading test can prove the
    registry never imports a candidate before it is specifically
    requested -- scanning and listing must leave ``load_calls`` at zero."""

    def __init__(self, name: str, loader) -> None:
        self.name = name
        self._loader = loader
        self.load_calls = 0

    def load(self):
        self.load_calls += 1
        return self._loader()


# -- 1. Register / unregister / lookup round trip on a real plugin ----------


def test_register_unregister_roundtrip() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PYTHON_FORMAT_PLUGIN)

    resolved = registry.get_format_plugin("python")
    assert resolved is PYTHON_FORMAT_PLUGIN

    metadatas = registry.list_format_plugins()
    assert len(metadatas) == 1
    assert metadatas[0].format_id == "python"
    assert metadatas[0].file_extensions == ("py", "pyi")

    registry.unregister_format_plugin("python")
    with pytest.raises(FormatPluginNotFoundError) as excinfo:
        registry.get_format_plugin("python")
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_NOT_FOUND
    assert excinfo.value.format_id == "python"
    assert registry.list_format_plugins() == ()

    # Unregistering an already-unknown format_id is a documented no-op,
    # never an error -- calling it twice must not raise.
    registry.unregister_format_plugin("python")


# -- 2. replace=True semantics -----------------------------------------------


def test_replace_semantics() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PYTHON_FORMAT_PLUGIN)

    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(PYTHON_FORMAT_PLUGIN)
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert "python" in str(excinfo.value)
    # The rejected attempt must not have disturbed the existing entry.
    assert registry.get_format_plugin("python") is PYTHON_FORMAT_PLUGIN

    # replace=True lets a *different* object claim the same format_id --
    # a real second Python plugin instance doesn't exist, so a minimal
    # fixture stands in to prove the swap actually happens.
    replacement = _MinimalContractPlugin(format_id="python", plugin_version="9.9.9")
    registry.register_format_plugin(replacement, replace=True)

    resolved = registry.get_format_plugin("python")
    assert resolved is replacement
    assert resolved is not PYTHON_FORMAT_PLUGIN
    metadatas = registry.list_format_plugins()
    assert len(metadatas) == 1
    assert metadatas[0].plugin_version == "9.9.9"


# -- 3. Registration conflict detection --------------------------------------


def test_registration_conflict_detection() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PYTHON_FORMAT_PLUGIN)

    # A different format_id claiming an extension "python" already owns.
    conflicting_extension = _MinimalContractPlugin(format_id="python2", file_extensions=("py",))
    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.register_format_plugin(conflicting_extension)
    assert excinfo.value.error_code == ErrorCode.FORMAT_EXTENSION_CONFLICT
    assert excinfo.value.details["extension"] == "py"
    assert excinfo.value.details["existing_format_id"] == "python"
    with pytest.raises(FormatPluginNotFoundError):
        registry.get_format_plugin("python2")

    # A different format_id claiming "python" itself as an alias.
    conflicting_alias = _MinimalContractPlugin(format_id="python3", aliases=("python",))
    with pytest.raises(PluginRegistrationError) as excinfo2:
        registry.register_format_plugin(conflicting_alias)
    assert excinfo2.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert excinfo2.value.details["alias"] == "python"

    # A structurally invalid candidate (empty format_id) never reaches the
    # index tables at all -- the plugin count stays exactly what it was.
    before = registry.list_format_plugins()
    invalid = _MinimalContractPlugin(format_id="", file_extensions=("zzz",))
    with pytest.raises(PluginRegistrationError) as excinfo3:
        registry.register_format_plugin(invalid)
    assert excinfo3.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert registry.list_format_plugins() == before

    # An incompatible contract_version major is rejected the same way.
    incompatible = _MinimalContractPlugin(format_id="future", contract_version="2.0.0")
    with pytest.raises(PluginRegistrationError) as excinfo4:
        registry.register_format_plugin(incompatible)
    assert excinfo4.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    assert "2.0.0" in str(excinfo4.value)
    assert registry.list_format_plugins() == before


# -- 4. Lazy entry-point discovery -------------------------------------------


def test_lazy_entry_point_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FormatPluginRegistry()
    entry = FakeEntryPoint("python", lambda: PYTHON_FORMAT_PLUGIN)
    scan_calls = 0

    def _fake_entry_points(*, group: str):
        nonlocal scan_calls
        scan_calls += 1
        return (entry,) if group == ENTRY_POINT_GROUP else ()

    monkeypatch.setattr(
        "tree_engine.plugins.registry.importlib_metadata.entry_points", _fake_entry_points
    )

    # Listing before any lookup must not scan, let alone load anything.
    assert registry.list_format_plugins() == ()
    assert scan_calls == 0
    assert entry.load_calls == 0

    resolved = registry.get_format_plugin("python")
    assert resolved is PYTHON_FORMAT_PLUGIN
    assert scan_calls == 1
    assert entry.load_calls == 1

    # A second lookup reuses the now-registered plugin: neither the scan
    # nor the entry point's own .load() run again.
    again = registry.get_format_plugin("python")
    assert again is PYTHON_FORMAT_PLUGIN
    assert scan_calls == 1
    assert entry.load_calls == 1

    # The lazily resolved plugin is now a first-class registered entry.
    listed = registry.list_format_plugins()
    assert len(listed) == 1
    assert listed[0].format_id == "python"


def test_lazy_entry_point_duplicate_name_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FormatPluginRegistry()
    first = FakeEntryPoint("python", lambda: PYTHON_FORMAT_PLUGIN)
    duplicate = FakeEntryPoint("python", lambda: PYTHON_FORMAT_PLUGIN)
    monkeypatch.setattr(
        "tree_engine.plugins.registry.importlib_metadata.entry_points",
        lambda **_: (first, duplicate),
    )

    with pytest.raises(PluginRegistrationError) as excinfo:
        registry.get_format_plugin("python")
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR
    # Neither candidate is ever loaded: the duplicate is caught while
    # indexing entry-point metadata, before any .load() call.
    assert first.load_calls == 0
    assert duplicate.load_calls == 0


# -- 5. get/list lookup across every real plugin -----------------------------


def test_get_list_lookup() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PYTHON_FORMAT_PLUGIN)
    registry.register_format_plugin(BSL_FORMAT_PLUGIN)
    registry.register_format_plugin(PLAIN_TEXT_FORMAT_PLUGIN)

    assert registry.get_format_plugin("python") is PYTHON_FORMAT_PLUGIN
    assert registry.get_format_plugin("bsl") is BSL_FORMAT_PLUGIN
    assert registry.get_format_plugin("plain_text") is PLAIN_TEXT_FORMAT_PLUGIN

    by_id = {metadata.format_id: metadata for metadata in registry.list_format_plugins()}
    assert set(by_id) == {"python", "bsl", "plain_text"}
    assert by_id["python"].file_extensions == ("py", "pyi")
    assert by_id["bsl"].file_extensions == ("bsl",)
    assert by_id["plain_text"].file_extensions == ("txt", "text")
    # Listed metadata is the plugin's own live object, not a copy.
    assert by_id["python"] is PYTHON_FORMAT_PLUGIN.metadata

    with pytest.raises(FormatPluginNotFoundError) as excinfo:
        registry.get_format_plugin("does-not-exist")
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_NOT_FOUND
    assert "does-not-exist" in str(excinfo.value)


# -- 6. convert/generate_output error propagation ----------------------------


def test_convert_generate_output_error_propagation() -> None:
    registry = FormatPluginRegistry()
    registry.register_format_plugin(PLAIN_TEXT_FORMAT_PLUGIN)

    with pytest.raises(FormatPluginNotFoundError) as excinfo:
        convert(object(), target_format_id="does-not-exist", registry=registry)
    assert excinfo.value.error_code == ErrorCode.FORMAT_PLUGIN_NOT_FOUND

    with pytest.raises(FormatPluginNotFoundError):
        generate_output(object(), "does-not-exist", registry=registry)

    # A node kind plain_text has no translation for triggers
    # UnsupportedTranslationError from inside the plugin's own
    # export_from_common, unmasked all the way out through the facade --
    # never silently replaced by a plain-text (or any other) fallback.
    foreign_node = make_node("foreign:unsupported")
    with pytest.raises(UnsupportedTranslationError) as excinfo2:
        convert(foreign_node, target_format_id="plain_text", registry=registry)
    assert excinfo2.value.node_type == "foreign:unsupported"
    assert excinfo2.value.format_id == "plain_text"
    assert excinfo2.value.error_code == ErrorCode.UNSUPPORTED_TRANSLATION

    with pytest.raises(UnsupportedTranslationError):
        generate_output(foreign_node, "plain_text", registry=registry)

    # A genuine successful round trip through the same public facade,
    # proving the two error paths above are the exception, not the rule.
    document = PLAIN_TEXT_FORMAT_PLUGIN.parse_document("hello\nworld\n")
    exported = convert(document, target_format_id="plain_text", registry=registry)
    assert isinstance(exported, PlainTextTree)
    rendered = generate_output(document, "plain_text", registry=registry)
    assert rendered == "hello\nworld\n"
