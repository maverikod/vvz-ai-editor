"""
NodeIdMap (C-025): short_id↔TreeNodeUuid map owner for one tree file.

Canonical UUID4 (C-024) lives only in the MAP section; TREE carries integer
short_id markers. Exposes exactly three public map-mutation operations:
build, validate_and_repair, resolve.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict

import yaml

SECTION_CHECKSUMS_START = "---CHECKSUMS---"
SECTION_MAP_START = "---MAP---"
SECTION_TREE_START = "---TREE---"
DEFAULT_NEXT_FREE = 1


class ChecksumsSection(TypedDict):
    source_sha256: str


@dataclass
class MapEntry:
    short_id: int
    uuid: str
    content_fingerprint: str
    kind: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MapSection:
    next_free: int
    entries: List[MapEntry]


@dataclass
class TreeSections:
    checksums: ChecksumsSection
    map: MapSection
    tree: str


@dataclass(frozen=True)
class DiscoveredNode:
    """Caller-supplied node discovered from marked TREE + unmarked content."""

    content_fingerprint: str
    kind: str
    marker_short_id: int
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolveResult:
    short_id: int
    uuid: str


class NodeIdMapError(ValueError):
    """Base error for NodeIdMap validation failures."""


class UnknownShortIdError(NodeIdMapError):
    def __init__(self, short_id: int) -> None:
        super().__init__(f"Unknown short_id: {short_id}")
        self.short_id = short_id


class UnknownTreeNodeUuidError(NodeIdMapError):
    def __init__(self, node_uuid: str) -> None:
        super().__init__(f"Unknown TreeNodeUuid: {node_uuid}")
        self.node_uuid = node_uuid


def compute_content_fingerprint(content: str) -> str:
    """Return SHA-256 hex digest of UTF-8 encoded content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _validate_uuid4_string(value: str) -> None:
    """Raise NodeIdMapError if value is not a valid UUID4 string."""
    try:
        parsed = uuid.UUID(value, version=4)
    except ValueError:
        raise NodeIdMapError(f"invalid UUID4: {value!r}") from None
    if str(parsed) != value.lower():
        raise NodeIdMapError(f"invalid UUID4: {value!r}")


def _validate_sha256_hex(value: str, field_name: str) -> None:
    """Raise NodeIdMapError if value is not 64 lowercase hex chars."""
    if len(value) != 64 or not all(c in "0123456789abcdef" for c in value):
        raise NodeIdMapError(f"invalid {field_name}: {value!r}")


def _rebuild_indexes(
    entries: List[MapEntry],
) -> tuple[Dict[int, MapEntry], Dict[str, int]]:
    """Return (short_id→entry, uuid→short_id) dicts; raise on duplicate keys."""
    by_short: Dict[int, MapEntry] = {}
    by_uuid: Dict[str, int] = {}
    for entry in entries:
        if entry.short_id in by_short or entry.uuid in by_uuid:
            raise NodeIdMapError("duplicate map key")
        by_short[entry.short_id] = entry
        by_uuid[entry.uuid] = entry.short_id
    return by_short, by_uuid


def _entry_identity_key(
    *,
    short_id: int,
    content_fingerprint: str,
    attributes: Dict[str, Any],
) -> str:
    """Stable node identity for UUID preservation (fingerprint alone is not unique)."""
    internal_id = attributes.get("internal_node_id")
    if isinstance(internal_id, str) and internal_id:
        return f"internal:{internal_id}"
    return f"short:{short_id}:fp:{content_fingerprint}"


def _identity_index_from_entries(entries: List[MapEntry]) -> Dict[str, str]:
    """Map identity key → uuid for prior MAP entries."""
    index: Dict[str, str] = {}
    for entry in entries:
        key = _entry_identity_key(
            short_id=entry.short_id,
            content_fingerprint=entry.content_fingerprint,
            attributes=entry.attributes,
        )
        index[key] = entry.uuid
    return index


def _parse_map_entry(raw: Dict[str, Any]) -> MapEntry:
    if not isinstance(raw, dict):
        raise NodeIdMapError("map entry must be a mapping")
    short_id = raw.get("short_id")
    if type(short_id) is bool or not isinstance(short_id, int) or short_id < 1:
        raise NodeIdMapError(f"invalid short_id: {short_id!r}")
    node_uuid = raw.get("uuid")
    if not isinstance(node_uuid, str):
        raise NodeIdMapError(f"invalid uuid: {node_uuid!r}")
    _validate_uuid4_string(node_uuid)
    fingerprint = raw.get("content_fingerprint")
    if not isinstance(fingerprint, str):
        raise NodeIdMapError(f"invalid content_fingerprint: {fingerprint!r}")
    _validate_sha256_hex(fingerprint, "content_fingerprint")
    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind:
        raise NodeIdMapError(f"invalid kind: {kind!r}")
    attributes = raw.get("attributes", {})
    if attributes is None:
        attributes = {}
    if not isinstance(attributes, dict):
        raise NodeIdMapError(f"invalid attributes: {attributes!r}")
    return MapEntry(
        short_id=short_id,
        uuid=node_uuid,
        content_fingerprint=fingerprint,
        kind=kind,
        attributes=dict(attributes),
    )


def parse_tree_file(text: str) -> TreeSections:
    """Parse on-disk three-section tree file text into TreeSections."""
    if SECTION_CHECKSUMS_START not in text:
        raise NodeIdMapError("missing CHECKSUMS section")
    checksums_block, _, rest = text.partition(SECTION_MAP_START)
    if SECTION_TREE_START not in rest:
        raise NodeIdMapError("missing TREE section")
    map_yaml_text, _, tree_body = rest.partition(SECTION_TREE_START)
    if tree_body.startswith("\n"):
        tree_body = tree_body[1:]

    checksums_yaml_text = checksums_block.replace(
        SECTION_CHECKSUMS_START, "", 1
    ).strip()
    checksums_data = yaml.safe_load(checksums_yaml_text)
    if not isinstance(checksums_data, dict):
        raise NodeIdMapError("invalid CHECKSUMS section")
    source_sha256 = checksums_data.get("source_sha256")
    if not isinstance(source_sha256, str):
        raise NodeIdMapError("missing source_sha256")
    _validate_sha256_hex(source_sha256, "source_sha256")
    checksums: ChecksumsSection = {"source_sha256": source_sha256}

    map_data = yaml.safe_load(map_yaml_text.strip())
    if not isinstance(map_data, dict):
        raise NodeIdMapError("invalid MAP section")
    next_free = map_data.get("next_free")
    if type(next_free) is bool or not isinstance(next_free, int) or next_free < 1:
        raise NodeIdMapError(f"invalid next_free: {next_free!r}")
    entries_raw = map_data.get("entries")
    if not isinstance(entries_raw, list):
        raise NodeIdMapError("missing entries list")
    entries = [_parse_map_entry(item) for item in entries_raw]
    _rebuild_indexes(entries)

    return TreeSections(
        checksums=checksums,
        map=MapSection(next_free=next_free, entries=entries),
        tree=tree_body,
    )


def serialize_tree_file(sections: TreeSections) -> str:
    """Serialize TreeSections to on-disk three-section tree file text."""
    checksums_yaml: str = str(
        yaml.safe_dump(
            {"source_sha256": sections.checksums["source_sha256"]},
            default_flow_style=False,
            sort_keys=False,
        )
    )
    entry_dicts: List[Dict[str, Any]] = []
    for entry in sections.map.entries:
        item: Dict[str, Any] = {
            "short_id": entry.short_id,
            "uuid": entry.uuid,
            "content_fingerprint": entry.content_fingerprint,
            "kind": entry.kind,
        }
        if entry.attributes:
            item["attributes"] = entry.attributes
        entry_dicts.append(item)
    map_yaml: str = str(
        yaml.safe_dump(
            {"next_free": sections.map.next_free, "entries": entry_dicts},
            default_flow_style=False,
            sort_keys=False,
        )
    )
    return (
        SECTION_CHECKSUMS_START
        + "\n"
        + checksums_yaml
        + SECTION_MAP_START
        + "\n"
        + map_yaml
        + SECTION_TREE_START
        + "\n"
        + sections.tree
    )


def _build_entries_from_discovered(
    discovered_nodes: List[DiscoveredNode],
    prior_map: Optional[MapSection],
) -> tuple[List[MapEntry], int]:
    next_free = prior_map.next_free if prior_map is not None else DEFAULT_NEXT_FREE
    identity_to_uuid: Dict[str, str] = {}
    if prior_map is not None:
        identity_to_uuid = _identity_index_from_entries(prior_map.entries)

    new_entries: List[MapEntry] = []
    seen_short_ids: set[int] = set()
    for node in discovered_nodes:
        if node.marker_short_id < 1:
            raise NodeIdMapError("marker_short_id must be >= 1")
        if node.marker_short_id in seen_short_ids:
            raise NodeIdMapError("duplicate marker_short_id in discovered_nodes")
        seen_short_ids.add(node.marker_short_id)

        identity_key = _entry_identity_key(
            short_id=node.marker_short_id,
            content_fingerprint=node.content_fingerprint,
            attributes=node.attributes,
        )
        if identity_key in identity_to_uuid:
            node_uuid = identity_to_uuid[identity_key]
        else:
            node_uuid = str(uuid.uuid4())
            if node.marker_short_id >= next_free:
                next_free = node.marker_short_id + 1

        new_entries.append(
            MapEntry(
                short_id=node.marker_short_id,
                uuid=node_uuid,
                content_fingerprint=node.content_fingerprint,
                kind=node.kind,
                attributes=node.attributes,
            )
        )

    if new_entries:
        next_free = max(next_free, max(e.short_id for e in new_entries) + 1)
    return new_entries, next_free


class NodeIdMap:
    """In-memory owner of MAP section state (C-025)."""

    def __init__(self, map_section: MapSection) -> None:
        self._map = map_section
        self._by_short, self._by_uuid = _rebuild_indexes(map_section.entries)

    @property
    def map_section(self) -> MapSection:
        """Return current MAP section snapshot (shallow copy of entries list)."""
        return MapSection(
            next_free=self._map.next_free,
            entries=list(self._map.entries),
        )

    @staticmethod
    def build(
        *,
        tree_marked_text: str,
        discovered_nodes: List[DiscoveredNode],
        source_sha256: str,
        prior_map: Optional[MapSection] = None,
    ) -> tuple[TreeSections, "NodeIdMap"]:
        """Build or refresh MAP from TREE markers and discovered nodes."""
        _validate_sha256_hex(source_sha256, "source_sha256")
        if not discovered_nodes:
            raise NodeIdMapError("discovered_nodes must not be empty")

        new_entries, next_free = _build_entries_from_discovered(
            discovered_nodes, prior_map
        )
        map_section = MapSection(next_free=next_free, entries=new_entries)
        sections = TreeSections(
            checksums={"source_sha256": source_sha256},
            map=map_section,
            tree=tree_marked_text,
        )
        return sections, NodeIdMap(map_section)

    def validate_and_repair(
        self,
        *,
        tree_marked_text: str,
        discovered_nodes: List[DiscoveredNode],
        checksums: ChecksumsSection,
    ) -> TreeSections:
        """Repair MAP/TREE/next_free inconsistencies; preserve UUIDs by fingerprint."""
        _validate_sha256_hex(checksums["source_sha256"], "source_sha256")
        if not discovered_nodes:
            raise NodeIdMapError("discovered_nodes must not be empty")

        prior = MapSection(
            next_free=self._map.next_free,
            entries=list(self._map.entries),
        )
        prior_identity = _identity_index_from_entries(prior.entries)

        new_entries, next_free = _build_entries_from_discovered(discovered_nodes, prior)
        for entry in new_entries:
            identity_key = _entry_identity_key(
                short_id=entry.short_id,
                content_fingerprint=entry.content_fingerprint,
                attributes=entry.attributes,
            )
            prior_uuid = prior_identity.get(identity_key)
            if prior_uuid is not None and entry.uuid != prior_uuid:
                entry.uuid = prior_uuid

        next_free = max(
            prior.next_free,
            (
                max(e.short_id for e in new_entries) + 1
                if new_entries
                else prior.next_free
            ),
        )
        self._map = MapSection(next_free=next_free, entries=new_entries)
        self._by_short, self._by_uuid = _rebuild_indexes(self._map.entries)
        return TreeSections(
            checksums=checksums,
            map=self._map,
            tree=tree_marked_text,
        )

    def resolve(
        self,
        *,
        short_id: Optional[int] = None,
        uuid: Optional[str] = None,
    ) -> ResolveResult:
        """Bidirectional lookup; exactly one argument must be provided."""
        if (short_id is None) == (uuid is None):
            raise NodeIdMapError("provide exactly one of short_id or uuid")

        if short_id is not None:
            entry = self._by_short.get(short_id)
            if entry is None:
                raise UnknownShortIdError(short_id)
            return ResolveResult(short_id=short_id, uuid=entry.uuid)

        assert uuid is not None
        normalized = uuid.lower()
        _validate_uuid4_string(normalized)
        resolved_short_id = self._by_uuid.get(normalized)
        if resolved_short_id is None:
            raise UnknownTreeNodeUuidError(uuid)
        return ResolveResult(short_id=resolved_short_id, uuid=normalized)


__all__ = [
    "ChecksumsSection",
    "DiscoveredNode",
    "MapEntry",
    "MapSection",
    "NodeIdMap",
    "NodeIdMapError",
    "ResolveResult",
    "TreeSections",
    "UnknownShortIdError",
    "UnknownTreeNodeUuidError",
    "compute_content_fingerprint",
    "parse_tree_file",
    "serialize_tree_file",
]
