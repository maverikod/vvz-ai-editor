"""
Author Vasiliy Zdanovskiy, vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import yaml

from ai_editor.tree.contracts import NodeId, UnknownNodeIdError
from ai_editor.tree.format_handler import FormatHandler, ShortIdAllocator
from ai_editor.tree.tree_node import TreeNode

_ID_KEY = "___id___"
_VAL_KEY = "v"
_META_KEY = "___meta___"

_DUMP_KWARGS = {
    "default_flow_style": False,
    "sort_keys": False,
    "allow_unicode": True,
}

_VALID_POSITIONS = frozenset({"before", "after", "first_child", "last_child"})


class YamlEditGateError(ValueError):
    """Raised when short_id edit ops are attempted while tree is invalid."""


@dataclass
class _Location:
    parent: Any
    key: Any
    node: dict[str, Any]


def _wrap_scalar(item: Any, allocator: ShortIdAllocator, path: str) -> Any:
    if isinstance(item, (dict, list)):
        return _inject_ids(item, allocator, path)
    return {_ID_KEY: allocator.allocate(), _VAL_KEY: item}


def _inject_ids(obj: Any, allocator: ShortIdAllocator, path: str = "") -> Any:
    if isinstance(obj, dict):
        injected: dict[str, Any] = {_ID_KEY: allocator.allocate()}
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            injected[k] = _inject_ids(v, allocator, child_path)
        return injected
    if isinstance(obj, list):
        return [
            _wrap_scalar(item, allocator, f"{path}[{i}]") for i, item in enumerate(obj)
        ]
    return {_ID_KEY: allocator.allocate(), _VAL_KEY: obj}


def _extract_wrapper_meta(node: dict[str, Any]) -> Dict[str, Any]:
    raw = node.get(_META_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _merge_wrapper_meta(node: dict[str, Any], attributes: Dict[str, Any]) -> None:
    if not attributes:
        return
    merged = _extract_wrapper_meta(node)
    merged.update(attributes)
    node[_META_KEY] = merged


def _strip_ids(obj: Any) -> Any:
    if isinstance(obj, dict):
        if _ID_KEY in obj and _VAL_KEY in obj:
            val = obj[_VAL_KEY]
            extra = set(obj.keys()) - {_ID_KEY, _VAL_KEY, _META_KEY}
            if not extra:
                if isinstance(val, (dict, list)):
                    return _strip_ids(val)
                return val
        return {
            k: _strip_ids(v) for k, v in obj.items() if k not in (_ID_KEY, _META_KEY)
        }
    if isinstance(obj, list):
        return [_strip_ids(item) for item in obj]
    return obj


def _yaml_dump(value: Any) -> str:
    return cast(str, yaml.dump(value, **_DUMP_KWARGS))


def _load_marked(marked_text: str) -> Any:
    return yaml.safe_load(marked_text)


def _parse_new_content(new_content: str) -> Any:
    try:
        obj = yaml.safe_load(new_content)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML new_content: {exc}") from exc
    if obj is None and not new_content.strip():
        raise ValueError("new_content must not be empty")
    return obj


def _max_id_in_tree(obj: Any) -> int:
    best = 0
    if isinstance(obj, dict):
        if _ID_KEY in obj:
            best = max(best, int(obj[_ID_KEY]))
        for k, v in obj.items():
            if k != _ID_KEY:
                best = max(best, _max_id_in_tree(v))
    elif isinstance(obj, list):
        for item in obj:
            best = max(best, _max_id_in_tree(item))
    return best


def _locate(
    root: Any, sid: int, parent: Any = None, key: Any = None
) -> Optional[_Location]:
    if isinstance(root, dict) and _ID_KEY in root and int(root[_ID_KEY]) == sid:
        return _Location(parent, key, root)
    if isinstance(root, dict):
        for k, v in root.items():
            if k == _ID_KEY:
                continue
            found = _locate(v, sid, root, k)
            if found is not None:
                return found
    elif isinstance(root, list):
        for i, item in enumerate(root):
            found = _locate(item, sid, root, i)
            if found is not None:
                return found
    return None


def _require_location(root: Any, sid: NodeId) -> _Location:
    loc = _locate(root, int(sid))
    if loc is None:
        raise UnknownNodeIdError(sid)
    return loc


def _is_scalar_leaf(node: dict[str, Any]) -> bool:
    if _ID_KEY not in node or _VAL_KEY not in node:
        return False
    extra = set(node.keys()) - {_ID_KEY, _VAL_KEY, _META_KEY}
    if extra:
        return False
    return not isinstance(node[_VAL_KEY], (dict, list))


def _is_mapping_node(node: dict[str, Any]) -> bool:
    return isinstance(node, dict) and _ID_KEY in node and not _is_scalar_leaf(node)


def _mapping_entries(node: dict[str, Any]) -> List[Tuple[str, Any]]:
    return [(k, node[k]) for k in node if k != _ID_KEY]


def _set_mapping_entries(node: dict[str, Any], entries: List[Tuple[str, Any]]) -> None:
    sid = int(node[_ID_KEY])
    preserved_meta = _extract_wrapper_meta(node)
    node.clear()
    node[_ID_KEY] = sid
    for k, v in entries:
        node[k] = v
    if preserved_meta:
        node[_META_KEY] = preserved_meta


def _prepare_mapping_insert_entries(
    new_obj: Any, next_free: int
) -> List[Tuple[str, Any]]:
    if next_free < 1:
        raise ValueError("next_free must be >= 1")
    if not isinstance(new_obj, dict):
        raise ValueError("mapping insert requires YAML mapping new_content")
    allocator = ShortIdAllocator(next_free)
    entries: List[Tuple[str, Any]] = []
    for key, value in new_obj.items():
        if isinstance(value, (dict, list)):
            entries.append((key, _inject_ids(value, allocator)))
        else:
            entries.append((key, {_ID_KEY: allocator.allocate(), _VAL_KEY: value}))
    return entries


def _prepare_list_insert_item(new_obj: Any, next_free: int) -> Any:
    if next_free < 1:
        raise ValueError("next_free must be >= 1")
    if isinstance(new_obj, (dict, list)):
        return _inject_ids(new_obj, ShortIdAllocator(next_free))
    return {_ID_KEY: next_free, _VAL_KEY: new_obj}


def _insert_into_mapping(
    mapping: dict[str, Any], new_entries: List[Tuple[str, Any]], position: str
) -> None:
    existing = _mapping_entries(mapping)
    if position == "first_child":
        combined = new_entries + existing
    elif position == "last_child":
        combined = existing + new_entries
    else:
        raise ValueError(f"invalid position for mapping insert: {position!r}")
    _set_mapping_entries(mapping, combined)


def _insert_mapping_sibling(
    parent: dict[str, Any],
    anchor_key: str,
    new_entries: List[Tuple[str, Any]],
    position: str,
) -> None:
    existing = _mapping_entries(parent)
    idx = next(i for i, (k, _) in enumerate(existing) if k == anchor_key)
    insert_at = idx if position == "before" else idx + 1
    combined = existing[:insert_at] + new_entries + existing[insert_at:]
    _set_mapping_entries(parent, combined)


def _insert_list_sibling(
    parent: list[Any], anchor_idx: int, item: Any, position: str
) -> None:
    insert_at = anchor_idx if position == "before" else anchor_idx + 1
    parent.insert(insert_at, item)


def _delete_at(loc: _Location) -> None:
    if loc.parent is None:
        raise ValueError("cannot delete root document node")
    if isinstance(loc.parent, dict):
        del loc.parent[loc.key]
    elif isinstance(loc.parent, list):
        del loc.parent[loc.key]
    else:
        raise ValueError("invalid parent container for delete")


def _entries_for_moved_node(
    moved_node: dict[str, Any], src_loc: _Location
) -> List[Tuple[str, Any]]:
    if _is_mapping_node(moved_node):
        return _mapping_entries(moved_node)
    if isinstance(src_loc.parent, dict) and isinstance(src_loc.key, str):
        return [(str(src_loc.key), moved_node)]
    raise ValueError("cannot move node into mapping position")


def _insert_relative(
    root: Any,
    anchor_loc: _Location,
    new_obj: Optional[Any],
    position: str,
    next_free: int,
    *,
    moved_node: Optional[dict[str, Any]] = None,
    src_loc: Optional[_Location] = None,
) -> None:
    if position not in _VALID_POSITIONS:
        raise ValueError(f"invalid position: {position!r}")

    if position in ("first_child", "last_child"):
        anchor = anchor_loc.node
        if not _is_mapping_node(anchor):
            raise ValueError("first_child/last_child require a mapping anchor")
        if moved_node is not None:
            assert src_loc is not None
            new_entries = _entries_for_moved_node(moved_node, src_loc)
        else:
            assert new_obj is not None
            new_entries = _prepare_mapping_insert_entries(new_obj, next_free)
        _insert_into_mapping(anchor, new_entries, position)
        return

    if anchor_loc.parent is None:
        raise ValueError("before/after require a non-root anchor")

    if isinstance(anchor_loc.parent, list):
        if moved_node is not None:
            item = moved_node
        else:
            assert new_obj is not None
            item = _prepare_list_insert_item(new_obj, next_free)
        _insert_list_sibling(anchor_loc.parent, int(anchor_loc.key), item, position)
        return

    if isinstance(anchor_loc.parent, dict):
        if moved_node is not None:
            assert src_loc is not None
            new_entries = _entries_for_moved_node(moved_node, src_loc)
        else:
            assert new_obj is not None
            new_entries = _prepare_mapping_insert_entries(new_obj, next_free)
        _insert_mapping_sibling(
            anchor_loc.parent, str(anchor_loc.key), new_entries, position
        )
        return

    raise ValueError("unsupported parent container for insert")


def _replace_mapping_node(node: dict[str, Any], new_obj: Any, root: Any) -> None:
    preserved = int(node[_ID_KEY])
    preserved_meta = _extract_wrapper_meta(node)
    start = _max_id_in_tree(root) + 1
    injected = _inject_ids(new_obj, ShortIdAllocator(start))
    entries = [(k, injected[k]) for k in injected if k != _ID_KEY]
    node.clear()
    node[_ID_KEY] = preserved
    for k, v in entries:
        node[k] = v
    if preserved_meta:
        node[_META_KEY] = preserved_meta


def _replace_scalar_leaf(node: dict[str, Any], new_obj: Any) -> None:
    preserved = int(node[_ID_KEY])
    preserved_meta = _extract_wrapper_meta(node)
    if isinstance(new_obj, (dict, list)):
        raise ValueError("replace on scalar leaf requires scalar new_content")
    node.clear()
    node[_ID_KEY] = preserved
    node[_VAL_KEY] = new_obj
    if preserved_meta:
        node[_META_KEY] = preserved_meta


def _collect_nodes(
    obj: Any,
    path: str,
    nodes: List[TreeNode],
    allocator: ShortIdAllocator,
    *,
    parent_short_id: Optional[NodeId] = None,
) -> None:
    if isinstance(obj, dict):
        sid = allocator.allocate()
        mapping_sid = NodeId(sid)
        attrs: Dict[str, Any] = {"key_path": path}
        attrs.update(_extract_wrapper_meta(obj))
        nodes.append(
            TreeNode(
                short_id=mapping_sid,
                kind="mapping",
                content=_yaml_dump(obj),
                attributes=attrs,
                parent_short_id=parent_short_id,
            )
        )
        for k, v in obj.items():
            if k in (_ID_KEY, _META_KEY):
                continue
            child_path = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)):
                _collect_nodes(
                    v, child_path, nodes, allocator, parent_short_id=mapping_sid
                )
            else:
                scalar_sid = allocator.allocate()
                nodes.append(
                    TreeNode(
                        short_id=NodeId(scalar_sid),
                        kind="scalar",
                        content=_yaml_dump(v),
                        attributes={"key_path": child_path},
                        parent_short_id=mapping_sid,
                    )
                )
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            item_path = f"{path}[{i}]"
            if isinstance(item, (dict, list)):
                _collect_nodes(
                    item, item_path, nodes, allocator, parent_short_id=parent_short_id
                )
            else:
                scalar_sid = allocator.allocate()
                nodes.append(
                    TreeNode(
                        short_id=NodeId(scalar_sid),
                        kind="scalar",
                        content=_yaml_dump(item),
                        attributes={"key_path": item_path},
                        parent_short_id=parent_short_id,
                    )
                )
    else:
        sid = allocator.allocate()
        nodes.append(
            TreeNode(
                short_id=NodeId(sid),
                kind="scalar",
                content=_yaml_dump(obj),
                attributes={"key_path": path},
                parent_short_id=parent_short_id,
            )
        )


class YamlHandler(FormatHandler):
    def __init__(self, id_map: Any = None) -> None:
        super().__init__(id_map)
        self._tree_is_valid = True

    def set_tree_validity(self, is_valid: bool) -> None:
        self._tree_is_valid = is_valid

    def _enforce_short_id_edit_gate(self) -> None:
        if not self._tree_is_valid:
            raise YamlEditGateError(
                "tree is invalid (text mode); short_id edit operations forbidden until re-validation"
            )

    def parse_content(self, file_path: Path, content: str) -> List[TreeNode]:
        obj = yaml.safe_load(content)
        nodes: List[TreeNode] = []
        if obj is None:
            return nodes
        _collect_nodes(obj, "", nodes, ShortIdAllocator(1))
        return nodes

    def mark(self, content: str) -> str:
        obj = yaml.safe_load(content)
        marked = _inject_ids(obj, ShortIdAllocator(1))
        return cast(str, yaml.dump(marked, **_DUMP_KWARGS))

    def unmark(self, marked_text: str) -> str:
        obj = yaml.safe_load(marked_text)
        clean = _strip_ids(obj)
        return cast(str, yaml.dump(clean, **_DUMP_KWARGS))

    def sidecar_path(self, source_abs: Path) -> Path:
        return source_abs.parent / (source_abs.name + ".tree")

    def op_insert(
        self,
        marked_text: str,
        anchor_short_id: NodeId,
        position: str,
        new_content: str,
        next_free: int,
    ) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        anchor_loc = _require_location(root, anchor_short_id)
        new_obj = _parse_new_content(new_content)
        _insert_relative(root, anchor_loc, new_obj, position, next_free)
        return _yaml_dump(root)

    def op_delete(self, marked_text: str, short_id: NodeId) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        _delete_at(loc)
        return _yaml_dump(root)

    def op_replace(self, marked_text: str, short_id: NodeId, new_content: str) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        new_obj = _parse_new_content(new_content)
        node = loc.node
        if _is_scalar_leaf(node):
            _replace_scalar_leaf(node, new_obj)
        elif _is_mapping_node(node):
            _replace_mapping_node(node, new_obj, root)
        else:
            raise ValueError("unsupported node kind for replace")
        return _yaml_dump(root)

    def extract_move_payload(self, marked_text: str, short_id: NodeId) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        node = loc.node
        if _is_scalar_leaf(node):
            val = _strip_ids(node)
            if isinstance(loc.parent, dict) and isinstance(loc.key, str):
                return _yaml_dump({loc.key: val})
            return _yaml_dump(val)
        return _yaml_dump(_strip_ids(node))

    def op_move(
        self,
        marked_text: str,
        short_id: NodeId,
        anchor_short_id: NodeId,
        position: str,
    ) -> str:
        self._enforce_short_id_edit_gate()
        next_free = self.peak_short_id_in_marked(marked_text) + 1
        return self.op_move_via_delete_insert(
            marked_text,
            short_id,
            anchor_short_id,
            position,
            next_free,
        )

    def op_edit_attributes(
        self, marked_text: str, short_id: NodeId, attributes: Dict[str, Any]
    ) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        _merge_wrapper_meta(loc.node, attributes)
        return _yaml_dump(root)

    def op_edit_content(
        self, marked_text: str, short_id: NodeId, new_content: str
    ) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        node = loc.node
        if not _is_scalar_leaf(node):
            raise ValueError("edit-content requires leaf block")
        new_obj = _parse_new_content(new_content)
        if isinstance(new_obj, (dict, list)):
            raise ValueError("edit-content requires scalar new_content")
        node[_VAL_KEY] = new_obj
        return _yaml_dump(root)
