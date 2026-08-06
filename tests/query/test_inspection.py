"""Contract tests for the ``drill_down`` inspection operation (concept C-018).

Covers G-019/T-001/A-003: ``tree_engine.query.inspection.drill_down`` -- depth
control, ``expand_below_bytes`` auto-expansion driven by a locally cached
``subtree_bytes`` aggregate, address resolution (int/hex short_id, UUID4,
and their rejection), ``expected_version``/``max_output_bytes`` enforcement,
per-field and whole-response truncation with continuation addressing, and
the read-only guarantee. Out of scope, owned by the sibling
``tests/query/test_inspection_outline.py``: the ``model_outline`` response
schema's own field shapes.

Fixture design -- two real ``Document`` instances, both from parsing the
same real repository file (``src/tree_engine/errors.py``) through the real
``PythonFormatPlugin``, never a hand-built ``Node`` graph. ``_PLUGIN_DOCUMENT``
is left exactly as the plugin returns it -- it pins a real limitation: this
``Document`` has no ``nodes_by_id`` (the mapping ``normalize_node_address``
itself requires), so only the default (root) address works against it; any
explicit address, even the root's own real UUID/short_id, is rejected with
``NodeNotFoundError`` -- asserted below rather than hidden. ``_FIXTURE_DOCUMENT``
is a second, independently parsed copy of the same real tree that this file
then extends by plain attribute assignment -- ``document_version``,
``nodes_by_id``, ``resolve_short_id``, ``source_for``, ``subtree_bytes_for``
-- the same "reserved extension point" convention this codebase already
uses (e.g. ``core/transactions.py`` setting ``document.document_version`` in
place; neither dataclass declares ``__slots__``). This is the "hand-built
fixture document" this atomic step's own prompt calls for: real parsed
nodes and identities throughout, with a hand-controlled document-level
facade so ``document_version`` and the ``subtree_bytes`` cache (valid on
some nodes, missing or explicitly ``None`` -- stale -- on others) are under
the test's control.

``tree_engine`` is a standalone package: nothing here imports ``ai_editor``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import pytest

from tree_engine.core.address import build_node_address_view
from tree_engine.core.nodes import walk
from tree_engine.errors import ErrorCode
from tree_engine.plugins.python.plugin import PythonFormatPlugin
from tree_engine.query.inspection import (
    SOURCE_FULL,
    SOURCE_NONE,
    SOURCE_PREVIEW,
    DocumentVersionConflictError,
    NodeNotFoundError,
    drill_down,
)
from tree_engine.query.outline import OutlineNodeRecord, OutlineStubRecord

# --------------------------------------------------------------------------
# Fixture: two real Documents from one real file, real PythonFormatPlugin.
# --------------------------------------------------------------------------

_SOURCE_FILE = Path(__file__).resolve().parents[2] / "src" / "tree_engine" / "errors.py"
_SOURCE_BYTES = _SOURCE_FILE.read_bytes()

def _parse_real_document() -> Any:
    return PythonFormatPlugin().parse_document(_SOURCE_BYTES.decode("utf-8"))

_PLUGIN_DOCUMENT = _parse_real_document()  # pristine -- pins the KNOWN LIMITATION

_FIXTURE_DOCUMENT = _parse_real_document()  # hand-extended below
_ALL_NODES = list(walk(_FIXTURE_DOCUMENT.root))
_NODES_BY_ID = {n.node_id: n for n in _ALL_NODES}
_SHORT_ID_INDEX: Dict[int, list] = {}
for _n in _ALL_NODES:
    _SHORT_ID_INDEX.setdefault(_n.short_id, []).append(_n.node_id)

_FIXTURE_DOCUMENT.document_version = "fixture-doc-v1"
_FIXTURE_DOCUMENT.nodes_by_id = _NODES_BY_ID
_FIXTURE_DOCUMENT.resolve_short_id = lambda short_id: _SHORT_ID_INDEX.get(short_id, [])
_FIXTURE_DOCUMENT.source_for = lambda node: (
    None
    if node.buffer_range is None
    else _SOURCE_BYTES[node.buffer_range[0] : node.buffer_range[1]].decode("utf-8", "replace")
)

def _set_subtree_bytes(document: Any, mapping: Dict[Any, Any]) -> None:
    """(Re)attach a fresh, isolated ``subtree_bytes_for`` closure so one
    test's cache values never leak into the next."""
    table = dict(mapping)
    document.subtree_bytes_for = lambda node_id, _t=table: _t.get(node_id)

_set_subtree_bytes(_FIXTURE_DOCUMENT, {})

_ROOT = _FIXTURE_DOCUMENT.root
_ERROR_LAYER = _ROOT.children[3]  # ClassDef ErrorLayer: 12 children, 3+ levels deep
_INDENTED_BLOCK = _ERROR_LAYER.children[1]
_ARG_WITHOUT_CACHE = _ERROR_LAYER.children[2]
_LEFT_PAREN = _ERROR_LAYER.children[4]  # 1 child -- a clean auto-expand target
_LEFT_PAREN_CHILD = _LEFT_PAREN.children[0]
_RIGHT_PAREN = _ERROR_LAYER.children[5]
_FUNC_ERROR_LAYER = _ROOT.children[10]  # FunctionDef error_layer: real 281-byte source

assert str(_ROOT.kind) == "python:Module"
assert str(_ERROR_LAYER.kind) == "python:ClassDef" and len(_ERROR_LAYER.children) == 12
assert len(_LEFT_PAREN.children) == 1 and len(_LEFT_PAREN_CHILD.children) == 0
assert _FUNC_ERROR_LAYER.buffer_range is not None

def _nodes_within(node, max_depth: int, depth: int = 0):
    """Independent oracle: every (node, depth) pair reachable from ``node``
    within ``max_depth`` edges, via the real ``Node.children`` -- never
    calling into ``drill_down``'s own traversal."""
    pairs = [(node, depth)]
    if depth < max_depth:
        for child in node.children:
            pairs.extend(_nodes_within(child, max_depth, depth + 1))
    return pairs

def _expected_ids_and_stubs(node, depth: int):
    """The exact node_id set drill_down must emit as full records at
    ``depth``, and the exact node_id set it must emit as stubs (the direct
    children of every node sitting right at the boundary)."""
    pairs = _nodes_within(node, depth)
    node_ids = {str(n.node_id) for n, d in pairs}
    stub_ids = {str(c.node_id) for n, d in pairs if d == depth for c in n.children}
    return node_ids, stub_ids

def _measure(response) -> int:
    """Independent re-measurement of a response's serialized size, using
    the same call shape ``inspection._payload_bytes`` uses, so the ceiling
    can be verified from outside rather than trusted from ``meta.response_bytes``."""
    return len(json.dumps(response, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))

# Depth control ({p066})
def test_depth_zero_returns_only_viewed_node():
    """depth=0 emits exactly one OutlineNodeRecord -- the viewed node -- and
    a stub for every direct child, never a deeper record."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    response = drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=0, expand_below_bytes=0)
    node_ids, stub_ids = _expected_ids_and_stubs(_ERROR_LAYER, 0)
    actual_nodes = {e.node_id for e in response.nodes if isinstance(e, OutlineNodeRecord)}
    actual_stubs = {e.node_id for e in response.nodes if isinstance(e, OutlineStubRecord)}
    assert actual_nodes == node_ids == {str(_ERROR_LAYER.node_id)}
    assert actual_stubs == stub_ids and len(stub_ids) == 12

def test_depth_one_returns_direct_children():
    """depth=1 emits the viewed node plus records for exactly its direct
    children; grandchildren surface only as stubs."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    response = drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=1, expand_below_bytes=0)
    node_ids, stub_ids = _expected_ids_and_stubs(_ERROR_LAYER, 1)
    actual_nodes = {e.node_id for e in response.nodes if isinstance(e, OutlineNodeRecord)}
    actual_stubs = {e.node_id for e in response.nodes if isinstance(e, OutlineStubRecord)}
    assert actual_nodes == node_ids and actual_stubs == stub_ids
    assert max(e.depth for e in response.nodes if isinstance(e, OutlineNodeRecord)) == 1

def test_depth_n_bounds_descendants():
    """depth=N reaches descendants exactly N edges away in real, genuinely
    deeper structure, and never further."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    response = drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=3, expand_below_bytes=0)
    node_ids, stub_ids = _expected_ids_and_stubs(_ERROR_LAYER, 3)
    actual_nodes = {e.node_id for e in response.nodes if isinstance(e, OutlineNodeRecord)}
    actual_stubs = {e.node_id for e in response.nodes if isinstance(e, OutlineStubRecord)}
    assert actual_nodes == node_ids and actual_stubs == stub_ids
    assert stub_ids, "fixture must still have deeper structure left to stub at depth=3"
    assert max(e.depth for e in response.nodes if isinstance(e, OutlineNodeRecord)) == 3

def test_default_depth_is_one():
    """Omitting depth behaves exactly as depth=1."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    default_response = drill_down(_FIXTURE_DOCUMENT, address=_RIGHT_PAREN.node_id, expand_below_bytes=0)
    explicit_response = drill_down(_FIXTURE_DOCUMENT, address=_RIGHT_PAREN.node_id, depth=1, expand_below_bytes=0)
    assert default_response.nodes == explicit_response.nodes
    assert default_response.meta.depth == 1

# expand_below_bytes auto-expansion ({p067})
def test_auto_expansion_on_valid_aggregate_under_threshold():
    """A child whose cached subtree_bytes is valid and <= expand_below_bytes
    is fully unfolded -- itself and its own descendants -- and every node
    revealed this way is marked auto_expanded."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {_LEFT_PAREN.node_id: 10})
    response = drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=0, expand_below_bytes=100)
    by_id = {e.node_id: e for e in response.nodes}
    left_paren, left_paren_child = by_id[str(_LEFT_PAREN.node_id)], by_id[str(_LEFT_PAREN_CHILD.node_id)]
    assert isinstance(left_paren, OutlineNodeRecord) and left_paren.expanded and left_paren.auto_expanded
    assert isinstance(left_paren_child, OutlineNodeRecord) and left_paren_child.auto_expanded
    assert left_paren_child.depth == 2
    others = [c for c in _ERROR_LAYER.children if c is not _LEFT_PAREN]
    assert all(isinstance(by_id[str(c.node_id)], OutlineStubRecord) for c in others)

def test_zero_expand_below_bytes_disables_auto_expansion():
    """expand_below_bytes=0 disables auto-expansion outright, even for a
    child whose cached aggregate is valid and tiny."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {_LEFT_PAREN.node_id: 10})
    response = drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=0, expand_below_bytes=0)
    by_id = {e.node_id: e for e in response.nodes}
    assert isinstance(by_id[str(_LEFT_PAREN.node_id)], OutlineStubRecord)
    assert not any(isinstance(e, OutlineNodeRecord) and e.auto_expanded for e in response.nodes)

def test_missing_or_stale_aggregate_yields_stub():
    """A child never registered in the cache and one whose entry is
    explicitly None (an invalidated/stale figure) both remain stubs -- never
    trusted -- while a sibling with a genuinely valid aggregate still
    expands, proving the threshold check itself still works."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {_LEFT_PAREN.node_id: 10, _INDENTED_BLOCK.node_id: None})
    response = drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=0, expand_below_bytes=100)
    by_id = {e.node_id: e for e in response.nodes}
    stale, missing = by_id[str(_INDENTED_BLOCK.node_id)], by_id[str(_ARG_WITHOUT_CACHE.node_id)]
    assert isinstance(stale, OutlineStubRecord) and stale.subtree_bytes is None
    assert isinstance(missing, OutlineStubRecord) and missing.subtree_bytes is None
    assert isinstance(by_id[str(_LEFT_PAREN.node_id)], OutlineNodeRecord)

# Address resolution and version checking ({p065})
def test_unknown_address_raises_node_not_found():
    """An address resolving to no node raises NodeNotFoundError, carrying
    ErrorCode.NODE_NOT_FOUND and the offending raw address -- never a bare
    KeyError or a None result."""
    bogus = uuid4()
    with pytest.raises(NodeNotFoundError) as excinfo:
        drill_down(_FIXTURE_DOCUMENT, address=bogus)
    assert excinfo.value.code == ErrorCode.NODE_NOT_FOUND
    assert excinfo.value.raw_address == bogus

def test_stale_expected_version_raises_conflict_before_read():
    """A mismatched expected_version raises DocumentVersionConflictError
    before any node is read -- proven by pairing it with an address that
    would otherwise raise NodeNotFoundError; the version conflict wins."""
    with pytest.raises(DocumentVersionConflictError) as excinfo:
        drill_down(_FIXTURE_DOCUMENT, address=uuid4(), expected_version="stale-version")
    assert excinfo.value.code == ErrorCode.DOCUMENT_VERSION_CONFLICT
    assert (excinfo.value.expected_version, excinfo.value.current_version) == (
        "stale-version",
        _FIXTURE_DOCUMENT.document_version,
    )

def test_short_id_and_uuid_address_forms_accepted():
    """int short_id, "0x"-prefixed hex short_id, a UUID object, and a bare
    UUID string all resolve to the same node."""
    expected_view = build_node_address_view(_LEFT_PAREN.node_id, _LEFT_PAREN.short_id)
    for address in (_LEFT_PAREN.short_id, f"0x{_LEFT_PAREN.short_id:x}", _LEFT_PAREN.node_id, str(_LEFT_PAREN.node_id)):
        response = drill_down(_FIXTURE_DOCUMENT, address=address, depth=0, expand_below_bytes=0)
        assert response.meta.viewed == expected_view

# max_output_bytes ceiling and truncation ({p068}, {p069})
def _uniform_full_and_partial():
    """A viewed node with several direct children, source/attributes
    suppressed so every kept entry is byte-uniform (no field ever needs
    shrinking) -- isolating the whole-response cutoff from field-level
    truncation."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    kwargs = dict(
        address=_ERROR_LAYER.node_id, depth=1, expand_below_bytes=0,
        include_source=SOURCE_NONE, include_attributes=False,
    )
    full = drill_down(_FIXTURE_DOCUMENT, max_output_bytes=10**9, **kwargs)
    assert not full.truncation.truncated
    target = full.meta.response_bytes // 2
    partial = drill_down(_FIXTURE_DOCUMENT, max_output_bytes=target, **kwargs)
    return full, partial, target

def test_max_output_bytes_cuts_between_node_records():
    """A small ceiling keeps only a prefix of whole node/stub records --
    never a partially-written one -- proven by exact equality against the
    untruncated response's own prefix; the kept response's real, measured
    size never exceeds the ceiling."""
    full, partial, target = _uniform_full_and_partial()
    assert 0 < len(partial.nodes) < len(full.nodes)
    assert partial.nodes == full.nodes[: len(partial.nodes)]
    assert _measure(partial) <= target

def test_truncated_response_reports_continuation_address():
    """A truncated response reports truncated=True, the real omitted-node
    count, a positive omitted_bytes, and a continuation address that is
    exactly where a follow-up call should resume."""
    full, partial, _ = _uniform_full_and_partial()
    kept = len(partial.nodes)
    assert partial.truncation.truncated is True
    assert partial.truncation.omitted_nodes == len(full.nodes) - kept
    assert partial.truncation.omitted_bytes > 0
    assert partial.truncation.continuation == full.nodes[kept].address

def test_field_truncation_preserves_mandatory_fields():
    """When only the source preview is too large for source_preview_bytes,
    it alone is marked field_truncated with its real original size, while
    every mandatory address/structural field stays intact and the record's
    own truncated flag stays false -- this is a preview-size cut, not a
    whole-response ceiling cut."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    full_text = _FIXTURE_DOCUMENT.source_for(_FUNC_ERROR_LAYER)
    response = drill_down(
        _FIXTURE_DOCUMENT, address=_FUNC_ERROR_LAYER.node_id, depth=0, expand_below_bytes=0,
        include_source=SOURCE_PREVIEW, source_preview_bytes=20,
    )
    record = response.nodes[0]
    assert (record.node_id, record.short_id_hex, record.type, record.child_count) == (
        str(_FUNC_ERROR_LAYER.node_id), f"0x{_FUNC_ERROR_LAYER.short_id:x}",
        "python:FunctionDef", len(_FUNC_ERROR_LAYER.children),
    )
    assert record.source_preview.field_truncated is True
    assert record.source_preview.original_field_bytes == len(full_text.encode("utf-8"))
    assert record.source_preview.value.encode("utf-8") == full_text.encode("utf-8")[:20]
    assert record.truncated is False
    assert response.truncation.truncated is False

# include_source modes and parameter contract ({p068})
def test_include_source_modes_produce_genuinely_different_payloads():
    """none/preview/full each shape source_preview differently."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    full_text = _FIXTURE_DOCUMENT.source_for(_FUNC_ERROR_LAYER)

    def _record(mode):
        response = drill_down(
            _FIXTURE_DOCUMENT, address=_FUNC_ERROR_LAYER.node_id, depth=0, expand_below_bytes=0, include_source=mode,
        )
        return response.nodes[0]

    none_r, preview_r, full_r = (_record(m) for m in (SOURCE_NONE, SOURCE_PREVIEW, SOURCE_FULL))
    assert none_r.source_preview is None
    assert preview_r.source_preview.field_truncated is True
    assert preview_r.source_preview.value.encode("utf-8") == full_text.encode("utf-8")[:256]
    assert full_r.source_preview.field_truncated is False and full_r.source_preview.value == full_text
    assert preview_r.source_preview.value != full_r.source_preview.value

def test_invalid_include_source_rejected():
    """An include_source value outside none/preview/full is rejected up
    front with ValueError, before any node is touched."""
    with pytest.raises(ValueError, match="include_source"):
        drill_down(_FIXTURE_DOCUMENT, include_source="bogus-mode")

def test_default_parameter_values_match_contract():
    """The declared defaults match {p066}-{p069} exactly, and include_self
    genuinely gates whether the viewed node gets its own record."""
    defaults = inspect.signature(drill_down).parameters
    assert defaults["depth"].default == 1
    assert defaults["expand_below_bytes"].default == 8192
    assert defaults["expected_version"].default is None
    assert defaults["include_self"].default is True
    assert defaults["include_attributes"].default is True
    assert defaults["include_source"].default == SOURCE_PREVIEW
    assert defaults["source_preview_bytes"].default == 256
    assert defaults["max_output_bytes"].default == 65536

    _set_subtree_bytes(_FIXTURE_DOCUMENT, {})
    with_self = drill_down(_FIXTURE_DOCUMENT, address=_LEFT_PAREN.node_id, depth=1, expand_below_bytes=0)
    without_self = drill_down(
        _FIXTURE_DOCUMENT, address=_LEFT_PAREN.node_id, depth=1, expand_below_bytes=0, include_self=False,
    )
    assert str(_LEFT_PAREN.node_id) in {e.node_id for e in with_self.nodes}
    assert str(_LEFT_PAREN.node_id) not in {e.node_id for e in without_self.nodes}

# Read-only guarantee ({p064}) and the plugin-document address limitation
def test_drill_down_never_mutates_document_state():
    """Across depth control, auto-expansion, truncation, and every address
    form, drill_down never mutates the tree, the node_id/short_id indexes,
    document_version, or format-plugin rendering."""
    _set_subtree_bytes(_FIXTURE_DOCUMENT, {_LEFT_PAREN.node_id: 10})
    nodes_before = list(walk(_FIXTURE_DOCUMENT.root))
    version_before = _FIXTURE_DOCUMENT.document_version
    nodes_by_id_before = dict(_FIXTURE_DOCUMENT.nodes_by_id)
    rendered_before = PythonFormatPlugin().render_document(_PLUGIN_DOCUMENT)

    drill_down(_FIXTURE_DOCUMENT, address=_ERROR_LAYER.node_id, depth=3, expand_below_bytes=100)
    drill_down(_FIXTURE_DOCUMENT, address=_LEFT_PAREN.short_id, depth=1)
    drill_down(_FIXTURE_DOCUMENT, depth=0, max_output_bytes=64)
    drill_down(_PLUGIN_DOCUMENT, depth=2)
    with pytest.raises(NodeNotFoundError):
        drill_down(_FIXTURE_DOCUMENT, address=uuid4())

    assert list(walk(_FIXTURE_DOCUMENT.root)) == nodes_before
    assert _FIXTURE_DOCUMENT.root is nodes_before[0]
    assert _FIXTURE_DOCUMENT.document_version == version_before
    assert _FIXTURE_DOCUMENT.nodes_by_id == nodes_by_id_before
    assert PythonFormatPlugin().render_document(_PLUGIN_DOCUMENT) == rendered_before == _SOURCE_BYTES

def test_plugin_produced_document_limits_addressing_to_root():
    """KNOWN LIMITATION, pinned rather than hidden: a Document exactly as
    PythonFormatPlugin hands it back carries no nodes_by_id (the mapping
    normalize_node_address itself requires), so the default (root) address
    is the only one that works against it; any explicit address -- even the
    root's own real UUID or short_id -- is rejected with NodeNotFoundError."""
    assert not hasattr(_PLUGIN_DOCUMENT, "nodes_by_id")
    response = drill_down(_PLUGIN_DOCUMENT, depth=1)
    assert response.meta.viewed.node_id == str(_PLUGIN_DOCUMENT.root.node_id)

    with pytest.raises(NodeNotFoundError):
        drill_down(_PLUGIN_DOCUMENT, address=_PLUGIN_DOCUMENT.root.node_id)
    with pytest.raises(NodeNotFoundError):
        drill_down(_PLUGIN_DOCUMENT, address=_PLUGIN_DOCUMENT.root.short_id)
