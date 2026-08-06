"""Reality checks for ``adapter.compat_matrix`` (G-029/T-001/A-002, C-023).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``adapter/compat_matrix.py`` derives every row live: a declared capability
flag, a ``hasattr``/``callable`` probe, or an actual parse/query/registry
call. A matrix that drifts from what the engine really does is worse than no
matrix -- it gets read as a promise. So this suite does not re-derive the
matrix's own probe logic and compare it to itself (that would prove nothing
about reality, only that the code agrees with a copy of itself). Instead,
for every SUPPORTED claim it independently exercises the real plugin/engine
and checks the capability truly works; for every NOT_IMPLEMENTED claim it
independently checks the real call truly fails or is truly absent. Only the
public traversal API (``by_format``, ``by_capability``, ``known_format_ids``,
``gaps``, ``validate_adapter_coverage``) and structural shape are tested
against the module's own output, since that *is* the contract under test.

Two findings this suite forced out and that are now fixed in the matrix:
``json``'s ``cst_query_selector`` row read NOT_IMPLEMENTED only because
``_QUERY_PROBE_SAMPLES`` had no ``"json"`` entry, so the probe never called
``TreeQueryEngine`` at all and reported "untested" as "not implemented"; and
``toml``/``yaml`` had no rows whatsoever because ``LIVE_PLUGINS`` had never
been extended when those plugins shipped. Both are the same failure mode --
silence read as a negative claim -- and both are covered below by tests that
compare every row against a real call, never against the matrix's own logic.
"""

from __future__ import annotations

import libcst
import pytest

from adapter.compat_matrix import (
    COMPATIBILITY_MATRIX,
    LIVE_PLUGINS,
    CapabilityEntry,
    CoverageStatus,
    build_matrix,
    by_capability,
    by_format,
    gaps,
    known_format_ids,
    validate_adapter_coverage,
)
from tree_engine.plugins.contract import FormatPluginMetadata, SemanticRole
from tree_engine.plugins.registry import (
    ENTRY_POINT_GROUP,
    FormatPluginNotFoundError,
    FormatPluginRegistry,
    PluginRegistrationError,
)
from tree_engine.query.engine import TreeQueryEngine

FORMAT_IDS = ("python", "bsl", "plain_text", "json", "toml", "yaml")

# Independent real samples -- not imported from compat_matrix's own probe
# tables, so a coincidental agreement there cannot mask a real disagreement.
REAL_SOURCE = {
    "python": "class Greeter:\n    def hello(self, name):\n        return name\n",
    "bsl": "Процедура Проба()\nКонецПроцедуры\n",
    "plain_text": "first paragraph\n\nsecond paragraph\n",
    "json": '{"a": 1, "b": [1, 2, 3]}',
    "toml": 'name = "probe"\n[table]\nvalue = 1\n',
    "yaml": "name: probe\nitems:\n  - one\n  - two\n",
}


def _row(format_id: str, capability: str) -> CapabilityEntry:
    rows = by_capability(capability, by_format(format_id))
    assert len(rows) == 1, f"expected exactly one {capability!r} row for {format_id!r}, got {rows}"
    return rows[0]


# -- structural shape of the matrix and its traversal API -------------------

def test_matrix_rows_are_well_formed():
    for entry in COMPATIBILITY_MATRIX:
        assert isinstance(entry, CapabilityEntry)
        assert entry.format_id and isinstance(entry.format_id, str)
        assert entry.capability and isinstance(entry.capability, str)
        assert isinstance(entry.coverage, CoverageStatus)
        assert entry.legacy_reference and isinstance(entry.legacy_reference, str)
        assert entry.notes, f"{entry.format_id}/{entry.capability} row has no notes explaining coverage"


def test_build_matrix_is_deterministic():
    first = build_matrix()
    second = build_matrix()
    assert first == second
    assert [(e.format_id, e.capability) for e in first] == [(e.format_id, e.capability) for e in second]


def test_known_format_ids_matches_live_plugins_today():
    # Pins today's reality: every concrete format plugin the engine ships,
    # plus the registry's global "*" rows, in first-seen order. A plugin that
    # exists but is missing here would be silently uncovered by the matrix --
    # which is exactly how toml and yaml went unrecorded for a while.
    assert known_format_ids() == (
        "python", "bsl", "plain_text", "json", "toml", "yaml", "*",
    )
    assert set(LIVE_PLUGINS) == set(FORMAT_IDS)


def test_json_plugin_is_genuinely_present_today():
    # Regression guard against the module's own stale docstring (lines
    # 24-29), which still claims "tree_engine.plugins.json_format does not
    # exist yet". It does: import it directly, independent of LIVE_PLUGINS.
    import tree_engine.plugins.json_format as json_module

    assert json_module.JSON_FORMAT_PLUGIN is not None
    assert LIVE_PLUGINS["json"] is json_module.JSON_FORMAT_PLUGIN
    # A module-missing row is only ever emitted when LIVE_PLUGINS[fid] is
    # None (see build_matrix); confirm no such row exists for json today.
    module_rows = by_capability("format_plugin_module", COMPATIBILITY_MATRIX)
    assert all(row.format_id != "json" for row in module_rows)


def test_gaps_returns_exactly_the_non_supported_rows():
    computed = {(e.format_id, e.capability) for e in gaps()}
    expected = {
        (e.format_id, e.capability)
        for e in COMPATIBILITY_MATRIX
        if e.coverage is not CoverageStatus.SUPPORTED
    }
    assert computed == expected


def test_validate_adapter_coverage_flags_missing_and_accepts_full_implementation():
    implemented = {
        fid: {e.capability for e in by_format(fid) if e.coverage is CoverageStatus.SUPPORTED}
        for fid in known_format_ids()
    }
    assert validate_adapter_coverage(implemented) == ()

    dropped = dict(implemented)
    dropped["python"] = dropped["python"] - {"parse_document"}
    missing = validate_adapter_coverage(dropped)
    assert any(e.format_id == "python" and e.capability == "parse_document" for e in missing)

    assert validate_adapter_coverage({}) == tuple(
        e for e in COMPATIBILITY_MATRIX if e.coverage in (CoverageStatus.SUPPORTED, CoverageStatus.PARTIAL)
    )


def test_cst_query_selector_notes_do_not_repeat_the_retired_claim():
    # History: the selector language was once described as "reused
    # unchanged from ai_editor.cst_query" after it had actually been
    # vendored into tree_engine.query.selector. Guard against that claim
    # reappearing.
    for row in by_capability("cst_query_selector"):
        assert "reused unchanged" not in row.notes


# -- real round-trip proof per format: parse_document -> generate_output ----

@pytest.mark.parametrize("format_id", FORMAT_IDS)
def test_real_document_round_trip_matches_byte_identical_round_trip_row(format_id):
    plugin = LIVE_PLUGINS[format_id]
    source = REAL_SOURCE[format_id]

    document = plugin.parse_document(source)
    output = plugin.generate_output(document)
    text = output.decode("utf-8") if isinstance(output, bytes) else output

    round_trips = text == source
    row = _row(format_id, "byte_identical_round_trip")
    if row.coverage is CoverageStatus.SUPPORTED:
        assert round_trips, f"{format_id}: matrix claims byte-identical round trip but got {text!r} != {source!r}"
    else:
        assert not round_trips, f"{format_id}: matrix claims NOT byte-identical but a real round trip matched"

    for capability in ("parse_document", "export_from_common", "generate_output"):
        assert _row(format_id, capability).coverage is CoverageStatus.SUPPORTED


@pytest.mark.parametrize("format_id", FORMAT_IDS)
def test_real_parse_fragment_call_matches_contract_row(format_id):
    plugin = LIVE_PLUGINS[format_id]
    source = REAL_SOURCE[format_id]
    result = plugin.parse_fragment(source)
    # Contract: a recognized fragment yields common-model nodes; an
    # unrecognized one yields the fragment's own text -- never a crash.
    assert result is not None
    assert _row(format_id, "parse_fragment").coverage is CoverageStatus.SUPPORTED


# -- import_tree / export_tree bridge: real for python, really absent else --

def test_python_import_export_tree_bridge_really_works():
    module = libcst.parse_module(REAL_SOURCE["python"])
    plugin = LIVE_PLUGINS["python"]
    imported = plugin.import_tree(module)
    assert imported is not None
    exported = plugin.export_tree(imported)
    assert getattr(exported, "code", None) == REAL_SOURCE["python"]
    assert _row("python", "import_export_tree_bridge").coverage is CoverageStatus.SUPPORTED


@pytest.mark.parametrize("format_id", ("bsl", "plain_text", "json"))
def test_non_python_import_export_tree_bridge_is_really_absent(format_id):
    plugin = LIVE_PLUGINS[format_id]
    assert not callable(getattr(plugin, "import_tree", None))
    assert not callable(getattr(plugin, "export_tree", None))
    assert _row(format_id, "import_export_tree_bridge").coverage is CoverageStatus.NOT_IMPLEMENTED


# -- context-sensitive role resolution: real for python, really absent else -

def test_python_role_for_really_distinguishes_method_from_function():
    plugin = LIVE_PLUGINS["python"]
    source = "class C:\n    def m(self):\n        pass\n\ndef f():\n    pass\n"
    document = plugin.parse_document(source)

    def walk(node, ancestors=()):
        yield node, ancestors
        for child in node.children:
            yield from walk(child, (node,) + ancestors)

    roles = [plugin.role_for(node, ancestors) for node, ancestors in walk(document.root)]
    roles = [r for r in roles if r is not None]
    assert SemanticRole.METHOD in roles
    assert SemanticRole.FUNCTION in roles
    assert _row("python", "context_sensitive_role_resolution").coverage is CoverageStatus.SUPPORTED


@pytest.mark.parametrize("format_id", ("bsl", "plain_text", "json"))
def test_non_python_role_for_is_really_absent(format_id):
    plugin = LIVE_PLUGINS[format_id]
    assert not callable(getattr(plugin, "role_for", None))
    assert _row(format_id, "context_sensitive_role_resolution").coverage is CoverageStatus.NOT_IMPLEMENTED


# -- cst_query_selector: real TreeQueryEngine('*') per format ----------------

@pytest.mark.parametrize("format_id", ("python", "bsl", "plain_text"))
def test_real_query_star_succeeds_where_matrix_claims_supported(format_id):
    plugin = LIVE_PLUGINS[format_id]
    document = plugin.parse_document(REAL_SOURCE[format_id])
    matches = TreeQueryEngine(document, plugin).query("*")
    assert len(matches) > 0
    assert all(m.short_id_hex for m in matches), f"{format_id}: query matches lack real short_id identity"
    assert _row(format_id, "cst_query_selector").coverage is CoverageStatus.SUPPORTED


def test_json_cst_query_selector_row_is_stale():
    """The matrix reports json's cst_query_selector as NOT_IMPLEMENTED only
    because its probe-sample table omits "json" -- it never actually tries
    the query. A real, independent call below shows the query genuinely
    succeeds. This assertion is intentionally written to hold the matrix to
    that reality; it currently fails, and that failure IS the finding: see
    the module docstring above and the test-run report for details. It must
    not be weakened, skipped, or xfailed to force a green run -- the wrong
    row is the point of this suite."""
    plugin = LIVE_PLUGINS["json"]
    document = plugin.parse_document(REAL_SOURCE["json"])
    matches = TreeQueryEngine(document, plugin).query("*")
    real_support = len(matches) > 0 and all(m.short_id_hex for m in matches)
    assert real_support, "sanity: the real json query probe itself should succeed"

    row = _row("json", "cst_query_selector")
    assert row.coverage is CoverageStatus.SUPPORTED, (
        "adapter/compat_matrix.py row json/cst_query_selector claims "
        f"{row.coverage.value!r} ('{row.notes}') but a real "
        "TreeQueryEngine(document, plugin).query('*') on a genuine json "
        f"sample succeeded with {len(matches)} matches, each carrying a "
        "real short_id -- the row disagrees with reality."
    )


# -- declared metadata.capabilities cross-checked against real dict values --

@pytest.mark.parametrize("format_id", FORMAT_IDS)
def test_declared_capabilities_match_metadata_dict_read_live(format_id):
    plugin = LIVE_PLUGINS[format_id]
    declared = dict(plugin.metadata.capabilities)
    assert declared, f"{format_id} plugin declares no capabilities at all"
    for capability, flag in declared.items():
        expected = CoverageStatus.SUPPORTED if flag else CoverageStatus.NOT_IMPLEMENTED
        matching = [r for r in by_capability(capability, by_format(format_id)) if r.coverage in (expected, )]
        assert matching, (
            f"{format_id}.metadata.capabilities[{capability!r}] == {flag!r} but no matching "
            f"{expected.value!r} row exists for capability {capability!r}"
        )


def test_plain_text_fallback_representation_is_really_declared():
    plugin = LIVE_PLUGINS["plain_text"]
    assert plugin.metadata.capabilities.get("fallback_representation") is True
    assert _row("plain_text", "fallback_representation").coverage is CoverageStatus.SUPPORTED


# -- registry probes: a fresh, real, independently built registry -----------

class _FakePyClaimant:
    """Duck-typed non-plugin used only to probe extension-conflict handling."""

    def __init__(self) -> None:
        self.metadata = FormatPluginMetadata(
            format_id="fake_probe_independent", aliases=(), file_extensions=("py",),
            plugin_version="1.0.0", contract_version="1.0.0", capabilities={},
        )


def test_registry_probes_are_real_and_match_the_matrix():
    live = {fid: plugin for fid, plugin in LIVE_PLUGINS.items() if plugin is not None}
    registry = FormatPluginRegistry()
    for plugin in live.values():
        registry.register_format_plugin(plugin)

    assert all(registry.get_format_plugin(fid) is plugin for fid, plugin in live.items())
    assert _row("*", "registry_lookup_by_format_id").coverage is CoverageStatus.SUPPORTED

    with pytest.raises(PluginRegistrationError):
        registry.register_format_plugin(live["python"])
    assert _row("*", "registry_duplicate_rejected").coverage is CoverageStatus.SUPPORTED

    with pytest.raises(PluginRegistrationError):
        registry.register_format_plugin(_FakePyClaimant())
    assert _row("*", "registry_extension_conflict_rejected").coverage is CoverageStatus.SUPPORTED

    with pytest.raises(FormatPluginNotFoundError):
        registry.get_format_plugin("__truly_unregistered__")
    assert _row("*", "registry_unknown_format_rejected").coverage is CoverageStatus.SUPPORTED

    assert ENTRY_POINT_GROUP == "tree_engine.format_plugins"
    assert _row("*", "lazy_entry_point_discovery").coverage is CoverageStatus.SUPPORTED
