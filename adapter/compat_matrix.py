"""AI Editor <-> tree_engine format-plugin compatibility matrix.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope (G-029/T-001/A-001, concept C-023): tracks which capabilities of the
new engine's plugin contract (``tree_engine.plugins.contract``) and query
engine (``tree_engine.query.engine``) are actually present per registered
format plugin, versus what the immutable AI Editor CAS baseline commit
``8fb05d1f`` offered. Every row is read live off a plugin object (declared
``metadata.capabilities``, ``hasattr``/``callable`` probes) or produced by
actually exercising the plugin/registry/query engine while this module is
imported -- never a hand-typed guess. An unobservable capability is recorded
``NOT_IMPLEMENTED`` with a note on what was checked, never omitted.

This module lives under ``adapter/`` -- the compatibility layer explicitly
permitted to reference the legacy surface, unlike anything under
``src/tree_engine/``, which must never import ``ai_editor``. In practice this
module does **not** import ``ai_editor`` at all: every ``legacy_reference``
string is a documentation pointer, not a runtime dependency; the one live
``ai_editor.cst_query`` import (the reused selector parser/AST) lives in
``tree_engine/query/engine.py`` itself, out of this file's scope.

Only three concrete format plugins exist in this worktree at the baseline:
``python`` (LibCST), ``bsl`` (tree-sitter-bsl), ``plain_text`` (the mandatory
fallback). A fourth, ``json``, is named by this step's task context but its
module (``tree_engine.plugins.json_format``) does not exist yet -- verified
live below via ``ModuleNotFoundError``, not assumed; asserting capabilities
that do not exist would itself be the defect this matrix exists to prevent.
"""

from __future__ import annotations

import enum
import importlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from tree_engine.plugins.contract import FormatPluginContract
from tree_engine.plugins.registry import (
    ENTRY_POINT_GROUP,
    FormatPluginNotFoundError,
    FormatPluginRegistry,
    PluginRegistrationError,
)

__all__ = [
    "BASELINE_AI_EDITOR_COMMIT",
    "BASELINE_AI_EDITOR_SUBJECT",
    "CoverageStatus",
    "CapabilityEntry",
    "LIVE_PLUGINS",
    "COMPATIBILITY_MATRIX",
    "by_format",
    "by_capability",
    "known_format_ids",
    "gaps",
    "validate_adapter_coverage",
]

# Immutable baseline ({p004}): confirmed live via
# `git log -1 --format=%H -- ai_editor` in this worktree, which reported
# exactly this hash -- not copied from memory.
BASELINE_AI_EDITOR_COMMIT = "8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a"
BASELINE_AI_EDITOR_SUBJECT = "Bump version to 1.0.83"

class CoverageStatus(str, enum.Enum):
    """Coverage state of one (format_id, capability) pair."""

    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"
    DEPRECATED = "deprecated"

@dataclass(frozen=True)
class CapabilityEntry:
    """One row. ``notes`` always states how ``coverage`` was determined --
    a declared flag, a probe, or a real call -- never left unexplained."""

    format_id: str
    capability: str
    coverage: CoverageStatus
    legacy_reference: str
    notes: str = ""

# -- legacy correspondence (documentation only, never imported) -------------

_LEGACY_REFERENCE: Dict[str, str] = {
    "parse_document": "ai_editor universal_file_edit open/preview commands (full-document load)",
    "parse_fragment": "ai_editor cst_modify_tree_ops_build fragment-insertion helpers",
    "import_external_tree": "no legacy counterpart; new-contract-only bridge for an already-parsed tree",
    "import_to_common": "no legacy counterpart; internal translator shared by the parse_*/import_external_tree stages",
    "export_from_common": "ai_editor universal_file_save_command / universal_file_replace_command",
    "generate_output": "ai_editor universal_file_edit session_write_command (final commit bytes)",
    "semantic_role_mapping": "ai_editor cst_query index_builder's function/method/class/module alias resolution",
    "import_tree": "no legacy counterpart; ai_editor never exposed a raw LibCST object across its MCP boundary",
    "export_tree": "no legacy counterpart; ai_editor never exposed a raw LibCST object across its MCP boundary",
    "byte_identical_round_trip": "ai_editor's LibCST round-trip guarantee, but Python-only in the baseline",
    "fallback_representation": "ai_editor's plain-text fallback path used when a richer parser failed",
    "context_sensitive_role_resolution": "ai_editor cst_query index_builder's class/function name stack",
    "cst_query_selector": "ai_editor.cst_query: jQuery/XPath-like selectors over LibCST, Python only",
    "registry_lookup_by_format_id": "no legacy analogue; ai_editor had one implicit Python/LibCST format",
    "registry_duplicate_rejected": "no legacy analogue; no multi-format plugin registry existed",
    "registry_extension_conflict_rejected": "no legacy analogue; no multi-format plugin registry existed",
    "registry_unknown_format_rejected": "no legacy analogue; no multi-format plugin registry existed",
    "lazy_entry_point_discovery": "no legacy analogue; ai_editor had no installable-plugin entry-point mechanism",
    "format_plugin_module": "n/a -- see notes",
}

def _legacy(capability: str) -> str:
    return _LEGACY_REFERENCE.get(capability, "no legacy reference recorded")

# -- live plugin discovery ---------------------------------------------------

def _load_plugin(module_path: str, attr: str) -> Optional[FormatPluginContract]:
    """Live-import a plugin singleton; ``None`` (never raise) when the
    module genuinely does not exist yet -- e.g. ``json_format``."""

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        return None
    return getattr(module, attr)

LIVE_PLUGINS: Dict[str, Optional[FormatPluginContract]] = {
    "python": _load_plugin("tree_engine.plugins.python.plugin", "PYTHON_FORMAT_PLUGIN"),
    "bsl": _load_plugin("tree_engine.plugins.bsl.plugin", "BSL_FORMAT_PLUGIN"),
    "plain_text": _load_plugin("tree_engine.plugins.plain_text", "PLAIN_TEXT_FORMAT_PLUGIN"),
    "json": _load_plugin("tree_engine.plugins.json_format", "JSON_FORMAT_PLUGIN"),
}

# Minimal real samples used only to probe live behavior; not a claim by themselves.
_QUERY_PROBE_SAMPLES: Dict[str, str] = {
    "python": "def probe():\n    pass\n",
    "bsl": "Процедура Проба()\nКонецПроцедуры\n",
    "plain_text": "probe\n",
}

_CONTRACT_METHODS = (
    "parse_document",
    "parse_fragment",
    "import_external_tree",
    "import_to_common",
    "export_from_common",
    "generate_output",
    "semantic_role_mapping",
)

def _contract_method_rows(format_id: str, plugin: FormatPluginContract) -> List[CapabilityEntry]:
    """Rows for the mandatory contract stages. ``abc`` refuses to instantiate
    a class missing any abstractmethod, so a live instance existing at all is
    itself proof -- checked here via ``callable(getattr(...))``, not assumed."""

    return [
        CapabilityEntry(
            format_id=format_id,
            capability=name,
            coverage=CoverageStatus.SUPPORTED if callable(getattr(plugin, name, None)) else CoverageStatus.NOT_IMPLEMENTED,
            legacy_reference=_legacy(name),
            notes="FormatPluginContract abstractmethod; verified via callable(getattr(plugin, name)).",
        )
        for name in _CONTRACT_METHODS
    ]

def _declared_capability_rows(format_id: str, plugin: FormatPluginContract) -> List[CapabilityEntry]:
    """One row per key the plugin's own ``metadata.capabilities`` declares,
    read live so a plugin change updates this matrix on next import."""

    return [
        CapabilityEntry(
            format_id=format_id,
            capability=key,
            coverage=CoverageStatus.SUPPORTED if value else CoverageStatus.NOT_IMPLEMENTED,
            legacy_reference=_legacy(key),
            notes=f"read live from {format_id}.metadata.capabilities[{key!r}] == {value!r}.",
        )
        for key, value in plugin.metadata.capabilities.items()
    ]

def _role_resolution_row(format_id: str, plugin: FormatPluginContract) -> CapabilityEntry:
    """``role_for`` is not part of the abstract contract and is not declared
    in ``metadata.capabilities``; only an ``hasattr``/``callable`` probe is honest."""
    has_role_for = callable(getattr(plugin, "role_for", None))
    return CapabilityEntry(
        format_id=format_id,
        capability="context_sensitive_role_resolution",
        coverage=CoverageStatus.SUPPORTED if has_role_for else CoverageStatus.NOT_IMPLEMENTED,
        legacy_reference=_legacy("context_sensitive_role_resolution"),
        notes=(
            f"callable(getattr(plugin, 'role_for', None)) == {has_role_for}; "
            "resolve_semantic_role prefers it, else falls back to the flat table."
        ),
    )

def _import_export_tree_bridge_row(format_id: str, plugin: FormatPluginContract) -> CapabilityEntry:
    """Cross-checks declared capability flags against real ``hasattr``
    probes for the ``import_tree``/``export_tree`` bridge ({p048}); a
    mismatch downgrades to PARTIAL instead of trusting either source alone."""

    declared = bool(plugin.metadata.capabilities.get("import_tree")) and bool(plugin.metadata.capabilities.get("export_tree"))
    actual = callable(getattr(plugin, "import_tree", None)) and callable(getattr(plugin, "export_tree", None))
    coverage = (
        CoverageStatus.SUPPORTED if declared and actual
        else CoverageStatus.NOT_IMPLEMENTED if not declared and not actual
        else CoverageStatus.PARTIAL
    )
    return CapabilityEntry(
        format_id=format_id,
        capability="import_export_tree_bridge",
        coverage=coverage,
        legacy_reference=_legacy("import_tree"),
        notes=f"declared metadata.capabilities says {declared}; hasattr/callable probe says {actual}.",
    )

def _probe_cst_query(format_id: str, plugin: Optional[FormatPluginContract]) -> CapabilityEntry:
    """Actually run ``tree_engine.query.engine`` against a freshly parsed
    real document for ``format_id`` and record what truly happened."""

    sample = _QUERY_PROBE_SAMPLES.get(format_id)
    if plugin is None or sample is None:
        return CapabilityEntry(
            format_id=format_id,
            capability="cst_query_selector",
            coverage=CoverageStatus.NOT_IMPLEMENTED,
            legacy_reference=_legacy("cst_query_selector"),
            notes="no live plugin instance and/or no probe sample for this format_id.",
        )
    try:
        document = plugin.parse_document(sample)
    except Exception as exc:  # noqa: BLE001 - reported verbatim, not swallowed
        return CapabilityEntry(
            format_id=format_id,
            capability="cst_query_selector",
            coverage=CoverageStatus.NOT_IMPLEMENTED,
            legacy_reference=_legacy("cst_query_selector"),
            notes=f"probe parse_document failed: {type(exc).__name__}: {exc}",
        )
    try:
        from tree_engine.query.engine import TreeQueryEngine

        TreeQueryEngine(document, plugin).query("*")
    except Exception as exc:  # noqa: BLE001 - reported verbatim, not swallowed
        return CapabilityEntry(
            format_id=format_id,
            capability="cst_query_selector",
            coverage=CoverageStatus.PARTIAL,
            legacy_reference=_legacy("cst_query_selector"),
            notes=(
                "selector parser/AST vendored into tree_engine.query.selector, traversal is "
                f"format-agnostic by construction, but query('*') on a freshly parsed "
                f"{format_id} document raised {type(exc).__name__}: {exc}. short_id assignment "
                "(core.identity/short_id) is out of this module's scope; only python's import "
                "path happened to assign one here."
            ),
        )
    return CapabilityEntry(
        format_id=format_id,
        capability="cst_query_selector",
        coverage=CoverageStatus.SUPPORTED,
        legacy_reference=_legacy("cst_query_selector"),
        notes=f"verified live: TreeQueryEngine(document, plugin).query('*') succeeded for a real {format_id} sample.",
    )

class _FakeExtensionClaimant:
    """Duck-typed non-plugin used only to probe registry conflict handling;
    the registry only requires a ``metadata`` attribute, no ABC subclassing."""

    def __init__(self, format_id: str, extension: str) -> None:
        from tree_engine.plugins.contract import FormatPluginMetadata

        self.metadata = FormatPluginMetadata(
            format_id=format_id, aliases=(), file_extensions=(extension,),
            plugin_version="1.0.0", contract_version="1.0.0", capabilities={},
        )

def _registry_row(capability: str, ok: bool, note: str) -> CapabilityEntry:
    coverage = CoverageStatus.SUPPORTED if ok else CoverageStatus.NOT_IMPLEMENTED
    return CapabilityEntry("*", capability, coverage, _legacy(capability), note)

def _probe_registry() -> List[CapabilityEntry]:
    """Register every live plugin into a throwaway registry and exercise
    every documented rejection path for real."""

    registry = FormatPluginRegistry()
    live = {fid: plugin for fid, plugin in LIVE_PLUGINS.items() if plugin is not None}
    for plugin in live.values():
        registry.register_format_plugin(plugin)

    rows: List[CapabilityEntry] = []

    lookup_ok = all(registry.get_format_plugin(fid) is plugin for fid, plugin in live.items())
    rows.append(_registry_row(
        "registry_lookup_by_format_id", lookup_ok,
        f"get_format_plugin(id) is the original object for all {len(live)} registered live plugins: {lookup_ok}.",
    ))

    duplicate_rejected = False
    try:
        registry.register_format_plugin(next(iter(live.values())))
    except PluginRegistrationError:
        duplicate_rejected = True
    rows.append(_registry_row(
        "registry_duplicate_rejected", duplicate_rejected,
        f"re-registering an already-registered format_id without replace=True raised PluginRegistrationError: {duplicate_rejected}.",
    ))

    conflict_rejected = False
    if "python" in live:
        try:
            registry.register_format_plugin(_FakeExtensionClaimant("fake_probe", "py"))
        except PluginRegistrationError:
            conflict_rejected = True
    rows.append(_registry_row(
        "registry_extension_conflict_rejected", conflict_rejected,
        f"registering a plugin claiming an already-claimed extension ('py') raised PluginRegistrationError: {conflict_rejected}.",
    ))

    unknown_rejected = False
    try:
        registry.get_format_plugin("__does_not_exist__")
    except FormatPluginNotFoundError:
        unknown_rejected = True
    rows.append(_registry_row(
        "registry_unknown_format_rejected", unknown_rejected,
        f"get_format_plugin on an unregistered id raised FormatPluginNotFoundError: {unknown_rejected}.",
    ))

    entry_point_ok = ENTRY_POINT_GROUP == "tree_engine.format_plugins"
    rows.append(_registry_row(
        "lazy_entry_point_discovery", entry_point_ok,
        f"tree_engine.plugins.registry.ENTRY_POINT_GROUP == {ENTRY_POINT_GROUP!r} (read live).",
    ))
    return rows

def build_matrix() -> Tuple[CapabilityEntry, ...]:
    """Assemble the full, live-verified matrix: every row comes from a probe
    function above that reads or exercises a real object."""
    rows: List[CapabilityEntry] = []
    for format_id, plugin in LIVE_PLUGINS.items():
        if plugin is None:
            rows.append(CapabilityEntry(
                format_id, "format_plugin_module", CoverageStatus.NOT_IMPLEMENTED,
                _legacy("format_plugin_module"),
                f"importlib.import_module raised ModuleNotFoundError for the '{format_id}' "
                "plugin module; no such plugin exists in this worktree yet, verified live.",
            ))
            continue
        rows.extend(_contract_method_rows(format_id, plugin))
        rows.extend(_declared_capability_rows(format_id, plugin))
        rows.append(_role_resolution_row(format_id, plugin))
        rows.append(_import_export_tree_bridge_row(format_id, plugin))
        rows.append(_probe_cst_query(format_id, plugin))
    rows.extend(_probe_registry())
    return tuple(rows)

COMPATIBILITY_MATRIX: Tuple[CapabilityEntry, ...] = build_matrix()

# -- traversal / coverage-tracker surface for adapter code and tests --------

def by_format(format_id: str, matrix: Iterable[CapabilityEntry] = COMPATIBILITY_MATRIX) -> Tuple[CapabilityEntry, ...]:
    """All rows for one ``format_id`` (or ``"*"`` for global/registry rows)."""
    return tuple(entry for entry in matrix if entry.format_id == format_id)

def by_capability(capability: str, matrix: Iterable[CapabilityEntry] = COMPATIBILITY_MATRIX) -> Tuple[CapabilityEntry, ...]:
    """All rows named ``capability`` across every format."""
    return tuple(entry for entry in matrix if entry.capability == capability)

def known_format_ids(matrix: Iterable[CapabilityEntry] = COMPATIBILITY_MATRIX) -> Tuple[str, ...]:
    """Every distinct ``format_id`` in the matrix, first-seen order."""
    seen: List[str] = []
    for entry in matrix:
        if entry.format_id not in seen:
            seen.append(entry.format_id)
    return tuple(seen)

def gaps(matrix: Iterable[CapabilityEntry] = COMPATIBILITY_MATRIX) -> Tuple[CapabilityEntry, ...]:
    """Every row not fully ``SUPPORTED`` -- what a coder/tester stage must close or accept."""
    return tuple(entry for entry in matrix if entry.coverage is not CoverageStatus.SUPPORTED)

def validate_adapter_coverage(
    implemented_capabilities: Mapping[str, Iterable[str]],
    matrix: Iterable[CapabilityEntry] = COMPATIBILITY_MATRIX,
) -> Tuple[CapabilityEntry, ...]:
    """Detect gaps between this matrix and a real adapter facade.

    ``implemented_capabilities`` maps a ``format_id`` (or ``"*"``) to the
    capability names an adapter actually implements, supplied by that
    adapter's own code/tests, never invented here. Returns every entry whose
    coverage is ``SUPPORTED``/``PARTIAL`` but absent from
    ``implemented_capabilities``; an entry already ``NOT_IMPLEMENTED`` here
    is never reported as an adapter gap -- the matrix already accounts for it."""

    missing: List[CapabilityEntry] = []
    for entry in matrix:
        if entry.coverage not in (CoverageStatus.SUPPORTED, CoverageStatus.PARTIAL):
            continue
        implemented = set(implemented_capabilities.get(entry.format_id, ()))
        if entry.capability not in implemented:
            missing.append(entry)
    return tuple(missing)
