"""
Bridge G-004 EditOperation dispatch to on-disk EditSession tree + post-mutation (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.markdown_line_ranges import (
    resolve_markdown_line_range,
)
from ai_editor.commands.universal_file_edit.insert_position import (
    parse_colon_position,
)
from ai_editor.core.cst_tree.models import ROOT_NODE_ID_SENTINEL
from ai_editor.core.json_tree.json_pointer import pointer_to_segments
from ai_editor.core.cst_tree.tree_modifier_ops_parse import join_code_lines
from ai_editor.core.edit_session.edit_session import (
    EditSession,
    SessionTreeValidity,
)
from ai_editor.core.tree_lifecycle.node_id_map import (
    DiscoveredNode,
    MapSection,
    NodeIdMap,
    NodeIdMapError,
    TreeSections,
    UnknownShortIdError,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from ai_editor.tree.contracts import NodeId, validate_short_id
from ai_editor.tree.edit_operations import (
    EditOperation,
    EditOperationError,
    EditOperationKind,
    apply_edit_operation,
)
from ai_editor.tree.handler_registry import HandlerRegistry

_POSITION_SIBLING = frozenset({"before", "after"})
_POSITION_CHILD = frozenset({"first", "last", "first_child", "last_child"})
_WRAPPER_ID_KEY = "___id___"
_WRAPPER_VAL_KEY = "v"


def session_has_valid_tree(session: EditSession) -> bool:
    """Return True when the core session is open with a valid in-session tree."""
    return (
        session.is_open
        and session.tree_validity == SessionTreeValidity.VALID
        and session.session_tree_path.is_file()
    )


def session_has_map_tree(session: EditSession) -> bool:
    """Return True when the session tree file is a MAP-format unified tree."""
    if not session_has_valid_tree(session):
        return False
    try:
        parse_tree_file(session.session_tree_path.read_text(encoding="utf-8"))
    except (NodeIdMapError, OSError, ValueError):
        return False
    return True


def _read_tree_sections(session: EditSession) -> TreeSections:
    return parse_tree_file(session.session_tree_path.read_text(encoding="utf-8"))


def _parse_marked_tree_root(sections: TreeSections, handler_id: Optional[str]) -> Any:
    if handler_id == "yaml":
        return yaml.safe_load(sections.tree)
    return json.loads(sections.tree)


def _wrapper_short_id(node: Any, field_name: str = "short_id") -> int:
    if not isinstance(node, dict) or _WRAPPER_ID_KEY not in node:
        raise ValueError(f"marked node missing {_WRAPPER_ID_KEY!r}")
    raw = node[_WRAPPER_ID_KEY]
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(f"{field_name} must be integer short_id, got {raw!r}")
    return raw


def _marked_child_at(node: Any, seg: str) -> Any:
    if isinstance(node, list):
        try:
            return node[int(seg)]
        except (IndexError, ValueError) as exc:
            raise ValueError(f"segment {seg!r} not found") from exc
    if isinstance(node, dict) and _WRAPPER_VAL_KEY in node:
        inner = node[_WRAPPER_VAL_KEY]
        if isinstance(inner, dict):
            try:
                return inner[seg]
            except KeyError as exc:
                raise ValueError(f"segment {seg!r} not found") from exc
        if isinstance(inner, list):
            try:
                return inner[int(seg)]
            except (IndexError, ValueError) as exc:
                raise ValueError(f"segment {seg!r} not found") from exc
        raise ValueError(f"cannot traverse segment {seg!r} through scalar")
    if isinstance(node, dict):
        try:
            return node[seg]
        except KeyError as exc:
            raise ValueError(f"segment {seg!r} not found") from exc
    raise ValueError(f"cannot traverse segment {seg!r}")


def _node_at_json_pointer(root: Any, pointer: str) -> Any:
    segs = pointer_to_segments(pointer)
    cur = root
    if not segs:
        return cur
    for seg in segs:
        try:
            cur = _marked_child_at(cur, seg)
        except ValueError as exc:
            raise ValueError(f"JSON Pointer {pointer!r} not found") from exc
    return cur


def _resolve_pointer_to_short_id(
    pointer: str,
    sections: TreeSections,
    handler_id: Optional[str],
) -> int:
    root = _parse_marked_tree_root(sections, handler_id)
    return _wrapper_short_id(_node_at_json_pointer(root, pointer), "json_pointer")


def _map_entries_in_line_range(
    sections: TreeSections, start_line: int, end_line: int
) -> List[Any]:
    matched = []
    for entry in sections.map.entries:
        attrs = entry.attributes or {}
        line = attrs.get("start_line")
        if isinstance(line, int) and start_line <= line <= end_line:
            matched.append(entry)
    return matched


def _resolve_markdown_ref_to_short_id(
    node_ref: str,
    sections: TreeSections,
    *,
    source_abs: Path,
    unmarked_source: str,
) -> int:
    bounds = resolve_markdown_line_range(
        unmarked_source,
        node_ref,
        file_path=str(source_abs.resolve()),
    )
    if isinstance(bounds, PreviewError):
        raise ValueError(bounds.message)
    start_line, end_line = bounds
    matched = _map_entries_in_line_range(sections, start_line, end_line)
    if not matched:
        raise ValueError(f"node_ref {node_ref!r} not found in session MAP")
    return int(min(matched, key=lambda e: e.attributes.get("start_line", 0)).short_id)


def _resolve_markdown_insert_anchor(
    node_ref: str,
    position: str,
    sections: TreeSections,
    *,
    source_abs: Path,
    unmarked_source: str,
) -> Tuple[int, str]:
    bounds = resolve_markdown_line_range(
        unmarked_source,
        node_ref,
        file_path=str(source_abs.resolve()),
    )
    if isinstance(bounds, PreviewError):
        raise ValueError(bounds.message)
    start_line, end_line = bounds
    matched = _map_entries_in_line_range(sections, start_line, end_line)
    if not matched:
        raise ValueError(f"node_ref {node_ref!r} not found in session MAP")
    pos = position.strip().lower()
    if pos == "before":
        anchor = min(matched, key=lambda e: e.attributes.get("start_line", 0))
        return anchor.short_id, "before"
    anchor = max(matched, key=lambda e: e.attributes.get("start_line", 0))
    return anchor.short_id, "after"


def resolve_node_ref_to_short_id(
    node_ref: Any,
    sections: TreeSections,
    *,
    source_abs: Optional[Path] = None,
    unmarked_source: Optional[str] = None,
    handler_id: Optional[str] = None,
) -> int:
    """Resolve API node_ref (short_id, MAP UUID, pointer, markdown slug) to short_id."""
    if node_ref is None or node_ref == "":
        raise ValueError("node_ref is required")
    if isinstance(node_ref, int):
        return int(validate_short_id(node_ref))
    raw = str(node_ref).strip()
    if raw == ROOT_NODE_ID_SENTINEL:
        return _root_short_id(sections)
    if raw.isdigit():
        sid = int(raw)
        validate_short_id(sid)
        if not any(entry.short_id == sid for entry in sections.map.entries):
            raise ValueError(f"short_id {sid} not found in session MAP")
        return sid
    normalized = raw.lower()
    for entry in sections.map.entries:
        if entry.uuid == normalized:
            return entry.short_id
    try:
        uuid.UUID(raw)
    except ValueError:
        pass
    else:
        if source_abs is not None and unmarked_source is not None:
            return _resolve_markdown_ref_to_short_id(
                raw,
                sections,
                source_abs=source_abs,
                unmarked_source=unmarked_source,
            )
    if raw.startswith("/") or raw == "":
        return _resolve_pointer_to_short_id(raw or "/", sections, handler_id)
    if (
        source_abs is not None
        and unmarked_source is not None
        and source_abs.suffix.lower() == ".md"
    ):
        return _resolve_markdown_ref_to_short_id(
            raw,
            sections,
            source_abs=source_abs,
            unmarked_source=unmarked_source,
        )
    raise ValueError(f"node_ref {node_ref!r} not found in session MAP")


def _root_short_id(sections: TreeSections) -> int:
    if sections.map.entries:
        return min(entry.short_id for entry in sections.map.entries)
    return 1


def _content_from_op(op: Dict[str, Any]) -> str:
    raw_code = op.get("code")
    if isinstance(raw_code, str):
        return raw_code
    raw_lines = op.get("code_lines")
    if raw_lines is not None:
        return join_code_lines([str(line) for line in raw_lines])
    for key in ("content", "new_content"):
        val = op.get(key)
        if isinstance(val, str):
            return val
    return ""


def _coalesce_node_ref_keys(op: Dict[str, Any]) -> Dict[str, Any]:
    m = dict(op)
    for ref_key, id_key in (
        ("node_ref", "node_id"),
        ("parent_node_ref", "parent_node_id"),
        ("target_node_ref", "target_node_id"),
    ):
        if ref_key in m and not m.get(id_key):
            m[id_key] = m[ref_key]
    return m


def _normalize_action(op: Dict[str, Any]) -> str:
    raw_action = op.get("action")
    raw_type = op.get("type")
    if isinstance(raw_action, str) and raw_action.strip():
        return raw_action.strip().lower()
    if isinstance(raw_type, str) and raw_type.strip():
        return raw_type.strip().lower()
    return "replace"


def _map_insert_position(position: str, *, sibling: bool) -> str:
    pos = position.strip().lower()
    if sibling:
        if pos in _POSITION_SIBLING:
            return pos
        raise ValueError(
            f"insert sibling position must be before|after, got {position!r}"
        )
    if pos == "first":
        return "first_child"
    if pos == "last":
        return "last_child"
    if pos in ("first_child", "last_child"):
        return pos
    raise ValueError(
        f"insert container position must be first|last|first_child|last_child, "
        f"got {position!r}"
    )


def _map_move_position(position: str) -> str:
    pos = position.strip().lower()
    if pos == "first":
        return "first_child"
    if pos == "last":
        return "last_child"
    if pos in _POSITION_SIBLING or pos in ("first_child", "last_child"):
        return pos
    raise ValueError(f"unsupported move position: {position!r}")


def _ref_resolution_kwargs(
    session: Optional[EditSession],
) -> Dict[str, Any]:
    if session is None:
        return {}
    hid = session.source_abs.suffix.lower()
    resolved_handler_id: Optional[str] = None
    if hid == ".json":
        resolved_handler_id = "json"
    elif hid in (".yml", ".yaml"):
        resolved_handler_id = "yaml"
    elif hid == ".md":
        resolved_handler_id = "markdown"
    try:
        unmarked = session.session_source_path.read_text(encoding="utf-8")
    except OSError:
        unmarked = None
    return {
        "source_abs": session.source_abs,
        "unmarked_source": unmarked,
        "handler_id": resolved_handler_id,
    }


def _resolve_ref(
    node_ref: Any,
    sections: TreeSections,
    session: Optional[EditSession],
) -> int:
    return resolve_node_ref_to_short_id(
        node_ref, sections, **_ref_resolution_kwargs(session)
    )


def _explicit_sibling_insert_anchor(m: Dict[str, Any]) -> tuple[Any | None, str]:
    """Sidecar-style sibling anchor: target/before/after ids or ``before:<addr>`` syntax."""
    target = m.get("target_node_id")
    position = str(m.get("position") or "after")
    if target not in (None, ""):
        return target, position
    before = m.get("before_node_id")
    if before not in (None, ""):
        return before, "before"
    after = m.get("after_node_id")
    if after not in (None, ""):
        return after, "after"
    parsed = parse_colon_position(m.get("position"))
    if parsed is not None:
        side, addr = parsed
        return addr, side
    return None, position


def _try_short_id_sibling_insert(
    node_ref: Any,
    position: str,
    sections: TreeSections,
    session: Optional[EditSession],
    content: str,
) -> EditOperation | None:
    """Insert before/after a MAP short_id when ``node_ref`` is numeric."""
    pos = position.strip().lower()
    if pos not in ("before", "after"):
        return None
    raw = str(node_ref).strip()
    if not raw.isdigit():
        return None
    try:
        sid = resolve_node_ref_to_short_id(
            raw, sections, **_ref_resolution_kwargs(session)
        )
    except ValueError:
        return None
    return EditOperation(
        kind=EditOperationKind.INSERT,
        anchor_short_id=NodeId(sid),
        position=pos,
        new_content=content,
        next_free=sections.map.next_free,
    )


def command_op_to_edit_operation(
    op: Dict[str, Any],
    sections: TreeSections,
    session: Optional[EditSession] = None,
) -> EditOperation:
    """Map universal_file_edit operation dict to G-004 EditOperation."""
    m = _coalesce_node_ref_keys(op)
    action = _normalize_action(m)
    ref_kw = _ref_resolution_kwargs(session)

    if action == "insert":
        parent = m.get("parent_node_id")
        content = _content_from_op(m)
        position = str(m.get("position") or "after")
        explicit_anchor, explicit_position = _explicit_sibling_insert_anchor(m)
        if explicit_anchor not in (None, ""):
            pos_norm = explicit_position.strip().lower()
            short_insert = _try_short_id_sibling_insert(
                explicit_anchor, explicit_position, sections, session, content
            )
            if short_insert is not None:
                return short_insert
            if (
                ref_kw.get("source_abs") is not None
                and str(ref_kw["source_abs"].suffix).lower() == ".md"
                and ref_kw.get("unmarked_source") is not None
                and pos_norm in ("before", "after")
            ):
                anchor_sid, mapped_pos = _resolve_markdown_insert_anchor(
                    str(explicit_anchor),
                    explicit_position,
                    sections,
                    source_abs=ref_kw["source_abs"],
                    unmarked_source=ref_kw["unmarked_source"],
                )
                return EditOperation(
                    kind=EditOperationKind.INSERT,
                    anchor_short_id=NodeId(anchor_sid),
                    position=mapped_pos,
                    new_content=content,
                    next_free=sections.map.next_free,
                )
            return EditOperation(
                kind=EditOperationKind.INSERT,
                anchor_short_id=NodeId(
                    _resolve_ref(explicit_anchor, sections, session)
                ),
                position=_map_insert_position(explicit_position, sibling=True),
                new_content=content,
                next_free=sections.map.next_free,
            )
        node_ref = m.get("node_id") or m.get("node_ref")
        pos_norm = position.strip().lower()
        if node_ref not in (None, "") and pos_norm in ("before", "after"):
            short_insert = _try_short_id_sibling_insert(
                node_ref, pos_norm, sections, session, content
            )
            if short_insert is not None:
                return short_insert
        if (
            node_ref not in (None, "")
            and ref_kw.get("source_abs") is not None
            and str(ref_kw["source_abs"].suffix).lower() == ".md"
            and ref_kw.get("unmarked_source") is not None
            and pos_norm in ("before", "after")
        ):
            anchor_sid, mapped_pos = _resolve_markdown_insert_anchor(
                str(node_ref),
                position,
                sections,
                source_abs=ref_kw["source_abs"],
                unmarked_source=ref_kw["unmarked_source"],
            )
            return EditOperation(
                kind=EditOperationKind.INSERT,
                anchor_short_id=NodeId(anchor_sid),
                position=mapped_pos,
                new_content=content,
                next_free=sections.map.next_free,
            )
        anchor_ref = parent if parent is not None else ROOT_NODE_ID_SENTINEL
        if node_ref not in (None, "") and parent is None:
            anchor_ref = node_ref
        return EditOperation(
            kind=EditOperationKind.INSERT,
            anchor_short_id=NodeId(_resolve_ref(anchor_ref, sections, session)),
            position=_map_insert_position(position, sibling=False),
            new_content=content,
            next_free=sections.map.next_free,
        )

    if action == "delete":
        node_ref = m.get("node_id") or m.get("node_ref")
        return EditOperation(
            kind=EditOperationKind.DELETE,
            short_id=NodeId(_resolve_ref(node_ref, sections, session)),
        )

    if action == "replace":
        node_ref = m.get("node_id") or m.get("node_ref")
        return EditOperation(
            kind=EditOperationKind.REPLACE,
            short_id=NodeId(_resolve_ref(node_ref, sections, session)),
            new_content=_content_from_op(m),
        )

    if action == "move":
        node_ref = m.get("node_id") or m.get("node_ref")
        target = m.get("target_node_id")
        parent = m.get("parent_node_id")
        position = str(m.get("position") or "after")
        if target:
            anchor = _resolve_ref(target, sections, session)
            mapped_pos = _map_move_position(position)
        else:
            anchor_ref = parent if parent is not None else ROOT_NODE_ID_SENTINEL
            anchor = _resolve_ref(anchor_ref, sections, session)
            mapped_pos = _map_move_position(position)
        return EditOperation(
            kind=EditOperationKind.MOVE,
            short_id=NodeId(_resolve_ref(node_ref, sections, session)),
            anchor_short_id=NodeId(anchor),
            position=mapped_pos,
        )

    if action == "edit_attributes":
        node_ref = m.get("node_id") or m.get("node_ref")
        attrs = m.get("attributes")
        if not isinstance(attrs, dict):
            raise ValueError("edit_attributes requires attributes dict")
        return EditOperation(
            kind=EditOperationKind.EDIT_ATTRIBUTES,
            short_id=NodeId(_resolve_ref(node_ref, sections, session)),
            attributes=dict(attrs),
        )

    if action == "edit_content":
        node_ref = m.get("node_id") or m.get("node_ref")
        return EditOperation(
            kind=EditOperationKind.EDIT_CONTENT,
            short_id=NodeId(_resolve_ref(node_ref, sections, session)),
            new_content=_content_from_op(m),
        )

    raise ValueError(f"unsupported edit operation type: {action!r}")


def _merge_prior_map_stable_identity(
    discovered: List[DiscoveredNode],
    prior_map: MapSection,
) -> List[DiscoveredNode]:
    """Keep MAP ``internal_node_id`` when short_id and content fingerprint are unchanged."""
    prior_by_short = {entry.short_id: entry for entry in prior_map.entries}
    merged: List[DiscoveredNode] = []
    for node in discovered:
        prior = prior_by_short.get(node.marker_short_id)
        if prior is None or prior.content_fingerprint != node.content_fingerprint:
            merged.append(node)
            continue
        prior_internal = (prior.attributes or {}).get("internal_node_id")
        if not isinstance(prior_internal, str) or not prior_internal:
            merged.append(node)
            continue
        attrs = dict(node.attributes)
        attrs["internal_node_id"] = prior_internal
        merged.append(
            DiscoveredNode(
                content_fingerprint=node.content_fingerprint,
                kind=node.kind,
                marker_short_id=node.marker_short_id,
                attributes=attrs,
            )
        )
    return merged


def _discovered_nodes_after_mutation(
    handler: object,
    *,
    session: EditSession,
    new_marked: str,
    denuded: str,
) -> List[DiscoveredNode]:
    """Build MAP discovery rows from post-mutation marked TREE (Python: CST stable_id)."""
    from ai_editor.tree.handlers.python_handler import PythonHandler

    if isinstance(handler, PythonHandler):
        return list(
            handler.discover_marked_nodes(
                new_marked,
                denuded,
                Path(session.file_path),
            )
        )
    parsed_nodes = handler.parse_content(Path(session.file_path), denuded)
    return [
        DiscoveredNode(
            marker_short_id=int(node.short_id),
            kind=node.kind,
            content_fingerprint=compute_content_fingerprint(node.content),
            attributes=dict(node.attributes),
        )
        for node in parsed_nodes
    ]


def _sync_map_after_tree_mutation(
    *,
    session: EditSession,
    sections: TreeSections,
    new_marked: str,
    new_next_free: int,
) -> TreeSections:
    handler = HandlerRegistry.default_registry().resolve(session.source_abs)
    denuded = handler.unmark(new_marked)
    discovered = _discovered_nodes_after_mutation(
        handler,
        session=session,
        new_marked=new_marked,
        denuded=denuded,
    )
    if discovered and sections.map.entries:
        discovered = _merge_prior_map_stable_identity(discovered, sections.map)
    if not discovered:
        return TreeSections(
            checksums=sections.checksums,
            map=MapSection(
                next_free=max(sections.map.next_free, new_next_free),
                entries=list(sections.map.entries),
            ),
            tree=new_marked,
        )
    prior = MapSection(
        next_free=max(sections.map.next_free, new_next_free),
        entries=list(sections.map.entries),
    )
    id_map = NodeIdMap(prior)
    return id_map.validate_and_repair(
        tree_marked_text=new_marked,
        discovered_nodes=discovered,
        checksums=sections.checksums,
    )


def apply_edit_on_session_tree(
    session: EditSession,
    operation: EditOperation,
) -> None:
    """Apply one EditOperation to the in-session unified tree file ({d003})."""
    if not session_has_valid_tree(session):
        raise RuntimeError(
            "apply_edit_on_session_tree requires open session with valid tree"
        )

    sections = _read_tree_sections(session)
    new_marked, new_next_free = apply_edit_operation(
        registry=HandlerRegistry.default_registry(),
        source_path=session.source_abs,
        marked_text=sections.tree,
        operation=operation,
        tree_is_valid=True,
        next_free=sections.map.next_free,
    )
    final_sections = _sync_map_after_tree_mutation(
        session=session,
        sections=sections,
        new_marked=new_marked,
        new_next_free=new_next_free,
    )
    file_text = serialize_tree_file(final_sections)
    tmp = session.session_tree_path.with_suffix(
        session.session_tree_path.suffix + ".tmp"
    )
    tmp.write_text(file_text, encoding="utf-8")
    os.replace(tmp, session.session_tree_path)
    session._post_mutation_full()


def sidecar_ops_use_unified_tree(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> bool:
    """Return True when every op address resolves via session MAP short_id."""
    if not session_has_valid_tree(session):
        return False
    try:
        sections = parse_tree_file(
            session.session_tree_path.read_text(encoding="utf-8")
        )
    except Exception:
        return False
    ref_fields = (
        "node_id",
        "node_ref",
        "parent_node_id",
        "parent_node_ref",
        "target_node_id",
        "target_node_ref",
        "before_node_id",
        "after_node_id",
    )
    for op in operations:
        m = _coalesce_node_ref_keys(op)
        for field in ref_fields:
            raw = m.get(field)
            if not raw or raw == ROOT_NODE_ID_SENTINEL or ":" in str(raw):
                continue
            try:
                resolve_node_ref_to_short_id(
                    raw, sections, **_ref_resolution_kwargs(session)
                )
            except ValueError:
                return False
    return True


def _operation_uses_node_address(m: Dict[str, Any]) -> bool:
    """Return True when an op names a node target (preview short_id, slug, etc.)."""
    for key in (
        "node_id",
        "node_ref",
        "parent_node_id",
        "parent_node_ref",
        "target_node_id",
        "target_node_ref",
        "before_node_id",
        "after_node_id",
    ):
        val = m.get(key)
        if val not in (None, "", ROOT_NODE_ID_SENTINEL):
            return True
    position = m.get("position")
    if isinstance(position, str):
        stripped = position.strip()
        if stripped.startswith("before:") or stripped.startswith("after:"):
            return True
    return False


def text_ops_use_unified_tree(operations: List[Dict[str, Any]]) -> bool:
    """Return True when ops target nodes by node_ref rather than line ranges."""
    for op in operations:
        if op.get("position") == "last":
            continue
        m = _coalesce_node_ref_keys(op)
        has_lines = op.get("start_line") is not None
        has_node = _operation_uses_node_address(m)
        if has_lines and not has_node:
            return False
        if _normalize_action(m) == "insert" and not has_node and not has_lines:
            return False
    return True


def expand_markdown_section_ops(
    op: Dict[str, Any],
    sections: TreeSections,
    session: EditSession,
) -> List[Dict[str, Any]]:
    """Split markdown section replace/delete into per-block ops when needed."""
    m = _coalesce_node_ref_keys(op)
    action = _normalize_action(m)
    if action not in ("replace", "delete"):
        return [op]
    if session.source_abs.suffix.lower() != ".md":
        return [op]
    node_ref = m.get("node_id") or m.get("node_ref")
    if node_ref in (None, ""):
        return [op]
    try:
        unmarked = session.session_source_path.read_text(encoding="utf-8")
    except OSError:
        return [op]
    bounds = resolve_markdown_line_range(
        unmarked,
        str(node_ref),
        file_path=str(session.source_abs.resolve()),
    )
    if isinstance(bounds, PreviewError):
        return [op]
    start_line, end_line = bounds
    matched = _map_entries_in_line_range(sections, start_line, end_line)
    if len(matched) <= 1:
        return [op]
    ordered = sorted(matched, key=lambda e: e.attributes.get("start_line", 0))
    if action == "delete":
        return [
            {
                "type": "delete",
                "action": "delete",
                "node_ref": entry.short_id,
                "node_id": entry.short_id,
            }
            for entry in reversed(ordered)
        ]
    tail_deletes = [
        {
            "type": "delete",
            "action": "delete",
            "node_ref": entry.short_id,
            "node_id": entry.short_id,
        }
        for entry in reversed(ordered[1:])
    ]
    head = {
        "type": "replace",
        "action": "replace",
        "node_ref": ordered[0].short_id,
        "node_id": ordered[0].short_id,
        "content": m.get("content", m.get("code", "")),
    }
    return tail_deletes + [head]


def apply_command_ops_on_session_tree(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> None:
    """Apply a batch of command-layer ops via EditOperation dispatch."""
    for op in operations:
        sections = _read_tree_sections(session)
        for expanded in expand_markdown_section_ops(op, sections, session):
            try:
                edit_op = command_op_to_edit_operation(expanded, sections, session)
            except (ValueError, UnknownShortIdError) as exc:
                raise EditOperationError(str(exc)) from exc
            apply_edit_on_session_tree(session, edit_op)
