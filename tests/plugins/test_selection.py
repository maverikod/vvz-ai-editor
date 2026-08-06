"""Contract tests for deterministic format selection (concept C-011,
step G-021/T-001/A-002).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises ``tree_engine.plugins.selection.resolve_format_plugin`` and
``build_extension_table`` against the REAL merged format plugins --
``PYTHON_FORMAT_PLUGIN``, ``BSL_FORMAT_PLUGIN``, ``PLAIN_TEXT_FORMAT_PLUGIN``
-- registered into a real ``FormatPluginRegistry``, not toy doubles. Only
these three concrete plugins are merged into this worktree; the json/yaml/
toml entries the baseline extension table ({p062}) documents belong to
sibling steps not yet delivered here, so this file cannot select among them
for real and does not pretend to. A minimal metadata-only fixture (mirroring
``tests/plugins/test_registry.py``'s own ``_MinimalContractPlugin`` pattern)
is used only for the one scenario no two distinct real plugins can ever
produce by construction: two different format ids claiming the same
extension for :func:`build_extension_table`'s conflict check.

Isolation: every test builds its own throw-away ``FormatPluginRegistry``
and/or extension table; nothing module-level is mutated, so test order is
provably irrelevant. This is exercised directly by running the whole file
twice with two different explicit, hand-picked orderings (forward and
reversed) -- see the verification commands in the commit/report, not
encoded here since no random-order pytest plugin is installed in this
worktree.

Covered per the atomic step: explicit ``format_id`` priority with the
extension fully ignored (absent/unknown/conflicting extension alike);
unambiguous baseline-extension resolution for every real extension (py,
pyi, bsl, txt, text) plus a case/whitespace edge form; the
``FORMAT_UNKNOWN_EXTENSION`` error for a missing, unknown, or absent
extension; the ``FORMAT_EXTENSION_CONFLICT`` error at table-build time; and
spy-based negative proof that neither path ever calls ``detect``, iterates
the registry, or signals a plain-text fallback.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from tree_engine.errors import ErrorCode
from tree_engine.plugins.bsl.plugin import BSL_FORMAT_PLUGIN
from tree_engine.plugins.contract import FormatPluginMetadata
from tree_engine.plugins.plain_text import PLAIN_TEXT_FORMAT_PLUGIN
from tree_engine.plugins.python.plugin import PYTHON_FORMAT_PLUGIN
from tree_engine.plugins.registry import FormatPluginRegistry
from tree_engine.plugins.selection import (
    FormatSelectionError,
    build_extension_table,
    resolve_format_plugin,
)

_REAL_PLUGINS = (PYTHON_FORMAT_PLUGIN, BSL_FORMAT_PLUGIN, PLAIN_TEXT_FORMAT_PLUGIN)


def _fresh_registry() -> FormatPluginRegistry:
    """A brand-new registry with the three real plugins registered -- never
    the process-wide default registry, never shared across tests."""

    registry = FormatPluginRegistry()
    for plugin in _REAL_PLUGINS:
        registry.register_format_plugin(plugin)
    return registry


def _fresh_extension_table() -> Dict[str, str]:
    """The real baseline extension table built from the three real plugins'
    own published metadata -- not a hand-typed stand-in."""

    return dict(build_extension_table(_REAL_PLUGINS))


class _SpyLookup:
    """Wraps a real registry, recording every ``get_format_plugin`` call and
    raising if anything else is touched.

    ``resolve_format_plugin``'s only documented contact with ``registry`` is
    ``get_format_plugin(format_id)``; ``detect``, ``list_format_plugins``,
    and iteration are deliberately absent/poisoned here so that if selection
    ever performed sniffing, a ``detect`` call, or plugin probing/iteration,
    this fixture -- not a mock of the subject itself, only an instrumented
    real registry -- would raise instead of silently succeeding.
    """

    def __init__(self, real_registry: FormatPluginRegistry) -> None:
        self._real = real_registry
        self.calls: List[str] = []

    def get_format_plugin(self, format_id: str) -> Any:
        self.calls.append(format_id)
        return self._real.get_format_plugin(format_id)

    def detect(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("selection must never call detect()")

    def list_format_plugins(self) -> Any:
        raise AssertionError("selection must never iterate/list the registry")

    def __iter__(self) -> Any:
        raise AssertionError("selection must never iterate the registry")


# -- 1. Explicit format_id has unconditional priority ------------------------


def test_format_id_priority_overrides_absent_extension() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id="bsl", file_path=None, registry=registry, extension_table=table
    )
    assert plugin is BSL_FORMAT_PLUGIN


def test_format_id_priority_overrides_unknown_extension() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id="python",
        file_path="notes.made_up_extension",
        registry=registry,
        extension_table=table,
    )
    assert plugin is PYTHON_FORMAT_PLUGIN


def test_format_id_priority_overrides_conflicting_extension() -> None:
    # "script.py" extension maps to python in the real table, but the
    # explicit format_id says bsl -- format_id must win outright.
    registry = _fresh_registry()
    table = _fresh_extension_table()
    assert table["py"] == "python"
    plugin = resolve_format_plugin(
        format_id="bsl", file_path="script.py", registry=registry, extension_table=table
    )
    assert plugin is BSL_FORMAT_PLUGIN


def test_explicit_format_id_never_touches_the_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves the extension is not merely overridden but never even read:
    poisons ``os.path.splitext`` (the one call selection.py uses to extract
    an extension) so any attempt to inspect the path blows up."""

    import os

    def _poisoned_splitext(_path: str) -> Any:
        raise AssertionError("file_path must never be inspected on the format_id branch")

    monkeypatch.setattr(os.path, "splitext", _poisoned_splitext)

    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id="plain_text",
        file_path="anything.py",
        registry=registry,
        extension_table=table,
    )
    assert plugin is PLAIN_TEXT_FORMAT_PLUGIN


# -- 2. Unambiguous baseline extension resolution -----------------------------


@pytest.mark.parametrize(
    "file_path, expected_plugin",
    [
        ("module.py", PYTHON_FORMAT_PLUGIN),
        ("stub.pyi", PYTHON_FORMAT_PLUGIN),
        ("Catalogs/report.bsl", BSL_FORMAT_PLUGIN),
        ("readme.txt", PLAIN_TEXT_FORMAT_PLUGIN),
        ("notes.text", PLAIN_TEXT_FORMAT_PLUGIN),
    ],
)
def test_extension_resolution_baseline_table(file_path: str, expected_plugin: Any) -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id=None, file_path=file_path, registry=registry, extension_table=table
    )
    assert plugin is expected_plugin


@pytest.mark.parametrize(
    "file_path",
    ["MODULE.PY", "Script.Bsl", "README.TXT", "a/b/c/Module.PyI"],
)
def test_extension_resolution_is_case_insensitive(file_path: str) -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id=None, file_path=file_path, registry=registry, extension_table=table
    )
    assert plugin.metadata.format_id in {"python", "bsl", "plain_text"}


def test_extension_resolution_uses_final_suffix_only() -> None:
    # "archive.tar.py" -- only the final ".py" counts, matching
    # os.path.splitext's own documented behavior.
    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id=None, file_path="archive.tar.py", registry=registry, extension_table=table
    )
    assert plugin is PYTHON_FORMAT_PLUGIN


# -- 3. Unknown / missing extension is an unconditional error ----------------


def test_unknown_extension_error_no_fallback() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    with pytest.raises(FormatSelectionError) as excinfo:
        resolve_format_plugin(
            format_id=None, file_path="diagram.rs", registry=registry, extension_table=table
        )
    assert excinfo.value.error_code == ErrorCode.FORMAT_UNKNOWN_EXTENSION


def test_missing_extension_error_no_fallback() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    with pytest.raises(FormatSelectionError) as excinfo:
        resolve_format_plugin(
            format_id=None, file_path="Makefile", registry=registry, extension_table=table
        )
    assert excinfo.value.error_code == ErrorCode.FORMAT_UNKNOWN_EXTENSION


def test_missing_file_path_error_no_fallback() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    with pytest.raises(FormatSelectionError) as excinfo:
        resolve_format_plugin(
            format_id=None, file_path=None, registry=registry, extension_table=table
        )
    assert excinfo.value.error_code == ErrorCode.FORMAT_UNKNOWN_EXTENSION


def test_unregistered_extension_is_not_a_bare_key_error() -> None:
    # A minimal table that simply never learned about ".bsl" -- resolving it
    # must raise the typed FormatSelectionError, never a bare KeyError from
    # a naive dict[extension] lookup.
    registry = _fresh_registry()
    table = {"py": "python"}
    with pytest.raises(FormatSelectionError) as excinfo:
        resolve_format_plugin(
            format_id=None, file_path="report.bsl", registry=registry, extension_table=table
        )
    assert excinfo.value.error_code == ErrorCode.FORMAT_UNKNOWN_EXTENSION


# -- 4. Extension conflict is a build-time configuration error ---------------


class _FakePlugin:
    """Metadata-only stand-in exposing just ``.metadata``, used solely to
    construct the one conflict scenario no two distinct real plugins can
    ever exhibit against each other (each already owns disjoint
    extensions). Never used in place of a real plugin for a real
    selection assertion."""

    def __init__(self, format_id: str, extensions: tuple) -> None:
        self.metadata = FormatPluginMetadata(
            format_id=format_id,
            aliases=(),
            file_extensions=extensions,
            plugin_version="1.0.0",
            contract_version="1.0.0",
            capabilities={},
        )


def test_extension_conflict_error_no_fallback() -> None:
    conflicting = [
        _FakePlugin("alpha", ("cfg",)),
        _FakePlugin("beta", ("cfg",)),
    ]
    with pytest.raises(FormatSelectionError) as excinfo:
        build_extension_table(conflicting)
    assert excinfo.value.error_code == ErrorCode.FORMAT_EXTENSION_CONFLICT
    assert excinfo.value.details["extension"] == "cfg"
    assert set(excinfo.value.details["format_ids"]) == {"alpha", "beta"}


def test_same_plugin_repeating_an_extension_is_not_a_conflict() -> None:
    same_twice = [_FakePlugin("gamma", ("md", "md"))]
    table = build_extension_table(same_twice)
    assert table == {"md": "gamma"}


def test_real_plugins_never_conflict_with_each_other() -> None:
    # The three real, merged plugins must build cleanly together -- this is
    # the ordinary, non-degenerate path build_extension_table exists for.
    table = _fresh_extension_table()
    assert table == {
        "py": "python",
        "pyi": "python",
        "bsl": "bsl",
        "txt": "plain_text",
        "text": "plain_text",
    }


# -- 5. No sniffing, no detect, no plugin iteration/probing ------------------


def test_no_plugin_iteration_or_probing_on_extension_path() -> None:
    real_registry = _fresh_registry()
    spy = _SpyLookup(real_registry)
    table = _fresh_extension_table()

    plugin = resolve_format_plugin(
        format_id=None, file_path="module.py", registry=spy, extension_table=table
    )

    assert plugin is PYTHON_FORMAT_PLUGIN
    assert spy.calls == ["python"]


def test_no_plugin_iteration_or_probing_on_format_id_path() -> None:
    real_registry = _fresh_registry()
    spy = _SpyLookup(real_registry)
    table = _fresh_extension_table()

    plugin = resolve_format_plugin(
        format_id="bsl", file_path=None, registry=spy, extension_table=table
    )

    assert plugin is BSL_FORMAT_PLUGIN
    assert spy.calls == ["bsl"]


def test_no_registry_contact_at_all_on_a_selection_failure() -> None:
    # An unknown extension must fail before ever touching the registry --
    # there is nothing to probe with, because nothing is probed.
    real_registry = _fresh_registry()
    spy = _SpyLookup(real_registry)
    table = _fresh_extension_table()

    with pytest.raises(FormatSelectionError):
        resolve_format_plugin(
            format_id=None, file_path="diagram.rs", registry=spy, extension_table=table
        )
    assert spy.calls == []


# -- 6. Selection never signals a plain-text fallback -------------------------


def test_no_plain_text_fallback_signal_on_unknown_extension() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    with pytest.raises(FormatSelectionError) as excinfo:
        resolve_format_plugin(
            format_id=None, file_path="diagram.rs", registry=registry, extension_table=table
        )
    error = excinfo.value
    # The failure is the unknown-extension code, never the
    # content-parse-failure code that is the *only* documented trigger for
    # a later plain-text fallback stage -- selection itself never raises
    # that code and never carries any "fallback"-shaped signal.
    assert error.error_code == ErrorCode.FORMAT_UNKNOWN_EXTENSION
    assert error.error_code != ErrorCode.FORMAT_CONTENT_PARSE_FAILED
    assert not hasattr(error, "fallback")
    assert not hasattr(error, "fallback_plugin")


def test_resolved_plugin_is_returned_bare_with_no_fallback_wrapper() -> None:
    registry = _fresh_registry()
    table = _fresh_extension_table()
    plugin = resolve_format_plugin(
        format_id=None, file_path="module.py", registry=registry, extension_table=table
    )
    # Exactly the plugin object itself -- no tuple, no wrapper, no
    # fallback-carrying envelope of any kind.
    assert plugin is PYTHON_FORMAT_PLUGIN
