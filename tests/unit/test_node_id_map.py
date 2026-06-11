"""
Unit tests for NodeIdMap module (C-025 / G-006).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import uuid
from unittest.mock import patch

import pytest

from ai_editor.core.tree_lifecycle.node_id_map import (
    DEFAULT_NEXT_FREE,
    SECTION_CHECKSUMS_START,
    SECTION_MAP_START,
    SECTION_TREE_START,
    DiscoveredNode,
    MapEntry,
    MapSection,
    NodeIdMap,
    NodeIdMapError,
    TreeSections,
    UnknownShortIdError,
    UnknownTreeNodeUuidError,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)

SOURCE_SHA256 = "a" * 64
UUID4_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def test_compute_content_fingerprint_empty() -> None:
    result = compute_content_fingerprint("")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_build_first_creation() -> None:
    fp1 = compute_content_fingerprint("alpha")
    fp2 = compute_content_fingerprint("beta")
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
        DiscoveredNode(
            content_fingerprint=fp2,
            kind="text",
            marker_short_id=2,
        ),
    ]
    sections, nm = NodeIdMap.build(
        tree_marked_text="{1} alpha\n{2} beta",
        discovered_nodes=nodes,
        source_sha256=SOURCE_SHA256,
    )
    assert sections.map.next_free == 3
    uuids = [e.uuid for e in sections.map.entries]
    assert len(set(uuids)) == 2
    for entry in sections.map.entries:
        by_short = nm.resolve(short_id=entry.short_id)
        by_uuid = nm.resolve(uuid=entry.uuid)
        assert by_short.uuid == entry.uuid
        assert by_uuid.short_id == entry.short_id


def test_build_rebuild_preserves_uuid_by_fingerprint() -> None:
    fp1 = compute_content_fingerprint("same content")
    u1 = str(uuid.uuid4())
    prior = MapSection(
        next_free=2,
        entries=[
            MapEntry(
                short_id=1,
                uuid=u1,
                content_fingerprint=fp1,
                kind="text",
            )
        ],
    )
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
    ]
    sections, _ = NodeIdMap.build(
        tree_marked_text="{1} same content",
        discovered_nodes=nodes,
        source_sha256=SOURCE_SHA256,
        prior_map=prior,
    )
    assert sections.map.entries[0].uuid == u1


def test_build_preserves_distinct_uuids_for_duplicate_fingerprints() -> None:
    """Python CST can yield multiple nodes with identical line-span content."""
    fp_shared = compute_content_fingerprint('"""doc"""')
    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    assert u1 != u2
    prior = MapSection(
        next_free=3,
        entries=[
            MapEntry(
                short_id=1,
                uuid=u1,
                content_fingerprint=fp_shared,
                kind="smallstmt",
                attributes={"internal_node_id": "aaa"},
            ),
            MapEntry(
                short_id=2,
                uuid=u2,
                content_fingerprint=fp_shared,
                kind="stmt",
                attributes={"internal_node_id": "bbb"},
            ),
        ],
    )
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp_shared,
            kind="smallstmt",
            marker_short_id=1,
            attributes={"internal_node_id": "aaa"},
        ),
        DiscoveredNode(
            content_fingerprint=fp_shared,
            kind="stmt",
            marker_short_id=2,
            attributes={"internal_node_id": "bbb"},
        ),
    ]
    sections, _ = NodeIdMap.build(
        tree_marked_text="marked",
        discovered_nodes=nodes,
        source_sha256=SOURCE_SHA256,
        prior_map=prior,
    )
    uuids = [e.uuid for e in sections.map.entries]
    assert len(set(uuids)) == 2
    assert sections.map.entries[0].uuid == u1
    assert sections.map.entries[1].uuid == u2


def test_validate_and_repair_preserves_uuid() -> None:
    fp1 = compute_content_fingerprint("content")
    correct_uuid = str(uuid.uuid4())
    wrong_uuid = str(uuid.uuid4())
    assert correct_uuid != wrong_uuid
    prior = MapSection(
        next_free=2,
        entries=[
            MapEntry(
                short_id=1,
                uuid=correct_uuid,
                content_fingerprint=fp1,
                kind="text",
            )
        ],
    )
    nm = NodeIdMap(prior)
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
    ]
    wrong_entry = MapEntry(
        short_id=1,
        uuid=wrong_uuid,
        content_fingerprint=fp1,
        kind="text",
    )
    with patch(
        "ai_editor.core.tree_lifecycle.node_id_map._build_entries_from_discovered",
        return_value=([wrong_entry], 2),
    ):
        repaired = nm.validate_and_repair(
            tree_marked_text="{1} content",
            discovered_nodes=nodes,
            checksums={"source_sha256": SOURCE_SHA256},
        )
    assert repaired.map.entries[0].uuid == correct_uuid


def test_validate_and_repair_drops_orphan_entries() -> None:
    fp1 = compute_content_fingerprint("keep")
    fp_orphan = compute_content_fingerprint("orphan")
    map_section = MapSection(
        next_free=3,
        entries=[
            MapEntry(
                short_id=1,
                uuid=str(uuid.uuid4()),
                content_fingerprint=fp1,
                kind="text",
            ),
            MapEntry(
                short_id=2,
                uuid=str(uuid.uuid4()),
                content_fingerprint=fp_orphan,
                kind="text",
            ),
        ],
    )
    nm = NodeIdMap(map_section)
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
    ]
    repaired = nm.validate_and_repair(
        tree_marked_text="{1} keep",
        discovered_nodes=nodes,
        checksums={"source_sha256": SOURCE_SHA256},
    )
    assert len(repaired.map.entries) == 1
    assert repaired.map.entries[0].content_fingerprint == fp1


def test_validate_and_repair_bumps_next_free() -> None:
    fp1 = compute_content_fingerprint("node")
    map_section = MapSection(
        next_free=1,
        entries=[],
    )
    nm = NodeIdMap(map_section)
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=5,
        ),
    ]
    repaired = nm.validate_and_repair(
        tree_marked_text="{5} node",
        discovered_nodes=nodes,
        checksums={"source_sha256": SOURCE_SHA256},
    )
    assert repaired.map.next_free == 6


def test_resolve_bidirectional() -> None:
    fp1 = compute_content_fingerprint("solo")
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
    ]
    _sections, nm = NodeIdMap.build(
        tree_marked_text="{1} solo",
        discovered_nodes=nodes,
        source_sha256=SOURCE_SHA256,
    )
    by_short = nm.resolve(short_id=1)
    by_uuid = nm.resolve(uuid=by_short.uuid)
    assert by_short.short_id == 1
    assert by_uuid.uuid == by_short.uuid


def test_resolve_unknown_short_id() -> None:
    fp1 = compute_content_fingerprint("x")
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
    ]
    _sections, nm = NodeIdMap.build(
        tree_marked_text="{1} x",
        discovered_nodes=nodes,
        source_sha256=SOURCE_SHA256,
    )
    with pytest.raises(UnknownShortIdError):
        nm.resolve(short_id=999)


def test_resolve_unknown_uuid() -> None:
    fp1 = compute_content_fingerprint("x")
    nodes = [
        DiscoveredNode(
            content_fingerprint=fp1,
            kind="text",
            marker_short_id=1,
        ),
    ]
    _sections, nm = NodeIdMap.build(
        tree_marked_text="{1} x",
        discovered_nodes=nodes,
        source_sha256=SOURCE_SHA256,
    )
    with pytest.raises(UnknownTreeNodeUuidError):
        nm.resolve(uuid=str(uuid.uuid4()))


def test_resolve_requires_exactly_one_arg() -> None:
    nm = NodeIdMap(MapSection(next_free=DEFAULT_NEXT_FREE, entries=[]))
    with pytest.raises(NodeIdMapError):
        nm.resolve()
    with pytest.raises(NodeIdMapError):
        nm.resolve(short_id=1, uuid=str(uuid.uuid4()))


def test_parse_serialize_roundtrip() -> None:
    fp1 = compute_content_fingerprint("tree body")
    entry = MapEntry(
        short_id=1,
        uuid=str(uuid.uuid4()),
        content_fingerprint=fp1,
        kind="text",
    )
    sections = TreeSections(
        checksums={"source_sha256": SOURCE_SHA256},
        map=MapSection(next_free=2, entries=[entry]),
        tree="{1} tree body",
    )
    text = serialize_tree_file(sections)
    parsed = parse_tree_file(text)
    assert parsed.map.next_free == sections.map.next_free
    assert len(parsed.map.entries) == len(sections.map.entries)


def test_parse_missing_checksums_section() -> None:
    text = f"{SECTION_MAP_START}\nnext_free: 1\nentries: []\n{SECTION_TREE_START}\n"
    with pytest.raises(NodeIdMapError):
        parse_tree_file(text)


def test_tree_section_has_no_uuid() -> None:
    fp1 = compute_content_fingerprint("no uuid here")
    sections = TreeSections(
        checksums={"source_sha256": SOURCE_SHA256},
        map=MapSection(
            next_free=2,
            entries=[
                MapEntry(
                    short_id=1,
                    uuid=str(uuid.uuid4()),
                    content_fingerprint=fp1,
                    kind="text",
                )
            ],
        ),
        tree="{1} no uuid here",
    )
    text = serialize_tree_file(sections)
    parsed = parse_tree_file(text)
    assert UUID4_PATTERN.search(parsed.tree) is None
