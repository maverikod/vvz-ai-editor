"""
JSON FormatHandler (C-007).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ai_editor.tree.contracts import NodeId, UnknownNodeIdError
from ai_editor.tree.format_handler import FormatHandler, ShortIdAllocator
from ai_editor.tree.tree_node import TreeNode

_ID_KEY = "___id___"
_VAL_KEY = "v"
_META_KEY = "___meta___"

_VALID_POSITIONS = frozenset({"before", "after", "first_child", "last_child"})


class JsonEditGateError(ValueError):
    """Raised when short_id edit ops are attempted while tree is invalid."""


@dataclass
class _Location:
    parent: Any
    key: Any
    node: dict[str, Any]


def _detect_json_format(text: str) -> Tuple[Optional[int], str]:
    lines = text.splitlines()
    if len(lines) <= 1:
        return None, "compact"
    for line in lines[1:]:
        stripped = line.lstrip(" ")
        if stripped and stripped[0] not in ("}", "]"):
            indent = len(line) - len(stripped)
            if indent > 0:
                return indent, "indented"
    return None, "compact"


def _wrap(obj: Any, allocator: ShortIdAllocator) -> Any:
    if isinstance(obj, dict):
        return {
            _ID_KEY: allocator.allocate(),
            _VAL_KEY: {k: _wrap(v, allocator) for k, v in obj.items()},
        }
    if isinstance(obj, list):
        return {
            _ID_KEY: allocator.allocate(),
            _VAL_KEY: [_wrap(i, allocator) for i in obj],
        }
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


def _unwrap(obj: Any) -> Any:
    if isinstance(obj, dict) and _ID_KEY in obj and _VAL_KEY in obj:
        val = obj[_VAL_KEY]
        if isinstance(val, dict):
            return {k: _unwrap(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_unwrap(i) for i in val]
        return val
    return obj


def _collect_nodes(
    wrapped: Any,
    pointer: str,
    nodes: List[TreeNode],
    *,
    parent_short_id: Optional[NodeId] = None,
) -> None:
    if isinstance(wrapped, dict) and _ID_KEY in wrapped and _VAL_KEY in wrapped:
        sid = int(wrapped[_ID_KEY])
        val = wrapped[_VAL_KEY]
        node_sid = NodeId(sid)
        if isinstance(val, dict):
            kind = "object"
            for k, v in val.items():
                _collect_nodes(v, f"{pointer}/{k}", nodes, parent_short_id=node_sid)
        elif isinstance(val, list):
            kind = "array"
            for i, v in enumerate(val):
                _collect_nodes(v, f"{pointer}[{i}]", nodes, parent_short_id=node_sid)
        else:
            kind = "scalar"
        attrs: Dict[str, Any] = {"json_pointer": pointer or "/"}
        attrs.update(_extract_wrapper_meta(wrapped))
        nodes.append(
            TreeNode(
                short_id=node_sid,
                kind=kind,
                content=json.dumps(val, ensure_ascii=False),
                attributes=attrs,
                parent_short_id=parent_short_id,
            )
        )


def _load_marked(marked_text: str) -> Any:
    return json.loads(marked_text)


def _dump_marked(root: Any, marked_text: str) -> str:
    indent, _ = _detect_json_format(marked_text)
    result = json.dumps(
        root,
        indent=indent,
        ensure_ascii=False,
        sort_keys=False,
    )
    return _preserve_trailing_newline(marked_text, result)


def _preserve_trailing_newline(original: str, result: str) -> str:
    if original.endswith("\n"):
        if not result.endswith("\n"):
            return result + "\n"
        return result
    return result


def _parse_new_content(new_content: str) -> Any:
    try:
        return json.loads(new_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON new_content: {exc}") from exc


def _max_id_in_tree(obj: Any) -> int:
    best = 0
    if isinstance(obj, dict):
        if _ID_KEY in obj:
            best = max(best, int(obj[_ID_KEY]))
        if _VAL_KEY in obj:
            best = max(best, _max_id_in_tree(obj[_VAL_KEY]))
        for k, v in obj.items():
            if k not in (_ID_KEY, _VAL_KEY):
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
    if isinstance(root, dict) and _VAL_KEY in root:
        val = root[_VAL_KEY]
        if isinstance(val, dict):
            for k, v in val.items():
                found = _locate(v, sid, val, k)
                if found is not None:
                    return found
        elif isinstance(val, list):
            for i, item in enumerate(val):
                found = _locate(item, sid, val, i)
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


def _is_object_node(node: dict[str, Any]) -> bool:
    return (
        isinstance(node, dict)
        and _ID_KEY in node
        and isinstance(node.get(_VAL_KEY), dict)
    )


def _object_entries(inner: dict[str, Any]) -> List[Tuple[str, Any]]:
    return list(inner.items())


def _set_object_entries(inner: dict[str, Any], entries: List[Tuple[str, Any]]) -> None:
    inner.clear()
    inner.update(entries)


def _prepare_object_insert_entries(
    new_obj: Any, next_free: int
) -> List[Tuple[str, Any]]:
    if next_free < 1:
        raise ValueError("next_free must be >= 1")
    if not isinstance(new_obj, dict):
        raise ValueError("object insert requires JSON object new_content")
    allocator = ShortIdAllocator(next_free)
    return [(key, _wrap(value, allocator)) for key, value in new_obj.items()]


def _prepare_list_insert_item(new_obj: Any, next_free: int) -> Any:
    if next_free < 1:
        raise ValueError("next_free must be >= 1")
    if isinstance(new_obj, (dict, list)):
        return _wrap(new_obj, ShortIdAllocator(next_free))
    return {_ID_KEY: next_free, _VAL_KEY: new_obj}


def _insert_into_object(
    inner: dict[str, Any], new_entries: List[Tuple[str, Any]], position: str
) -> None:
    existing = _object_entries(inner)
    if position == "first_child":
        combined = new_entries + existing
    elif position == "last_child":
        combined = existing + new_entries
    else:
        raise ValueError(f"invalid position for object insert: {position!r}")
    _set_object_entries(inner, combined)


def _insert_object_sibling(
    parent_inner: dict[str, Any],
    anchor_key: str,
    new_entries: List[Tuple[str, Any]],
    position: str,
) -> None:
    existing = _object_entries(parent_inner)
    idx = next(i for i, (k, _) in enumerate(existing) if k == anchor_key)
    insert_at = idx if position == "before" else idx + 1
    combined = existing[:insert_at] + new_entries + existing[insert_at:]
    _set_object_entries(parent_inner, combined)


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
    if _is_object_node(moved_node):
        return _object_entries(moved_node[_VAL_KEY])
    if isinstance(src_loc.parent, dict) and isinstance(src_loc.key, str):
        return [(str(src_loc.key), moved_node)]
    raise ValueError("cannot move node into object position")


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
        if not _is_object_node(anchor):
            raise ValueError("first_child/last_child require an object anchor")
        if moved_node is not None:
            assert src_loc is not None
            new_entries = _entries_for_moved_node(moved_node, src_loc)
        else:
            assert new_obj is not None
            new_entries = _prepare_object_insert_entries(new_obj, next_free)
        _insert_into_object(anchor[_VAL_KEY], new_entries, position)
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
            new_entries = _prepare_object_insert_entries(new_obj, next_free)
        _insert_object_sibling(
            anchor_loc.parent, str(anchor_loc.key), new_entries, position
        )
        return

    raise ValueError("unsupported parent container for insert")


def _replace_container_node(node: dict[str, Any], new_obj: Any, root: Any) -> None:
    preserved = int(node[_ID_KEY])
    preserved_meta = _extract_wrapper_meta(node)
    start = _max_id_in_tree(root) + 1
    injected = _wrap(new_obj, ShortIdAllocator(start))
    node.clear()
    node[_ID_KEY] = preserved
    node[_VAL_KEY] = injected[_VAL_KEY]
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


class JsonHandler(FormatHandler):
    _tree_is_valid: bool = True

    def set_tree_validity(self, is_valid: bool) -> None:
        self._tree_is_valid = is_valid

    def _enforce_short_id_edit_gate(self) -> None:
        if not self._tree_is_valid:
            raise JsonEditGateError(
                "tree is invalid (text mode); short_id edit operations forbidden until re-validation"
            )

    def parse_content(self, file_path: Path, content: str) -> List[TreeNode]:
        obj = json.loads(content)
        wrapped = _wrap(obj, ShortIdAllocator(1))
        nodes: List[TreeNode] = []
        _collect_nodes(wrapped, "", nodes)
        return nodes

    def mark(self, content: str) -> str:
        obj = json.loads(content)
        indent, _ = _detect_json_format(content)
        wrapped = _wrap(obj, ShortIdAllocator(1))
        result = json.dumps(
            wrapped,
            indent=indent,
            ensure_ascii=False,
            sort_keys=False,
        )
        return _preserve_trailing_newline(content, result)

    def unmark(self, marked_text: str) -> str:
        obj = json.loads(marked_text)
        indent, _ = _detect_json_format(marked_text)
        clean = _unwrap(obj)
        result = json.dumps(
            clean,
            indent=indent,
            ensure_ascii=False,
            sort_keys=False,
        )
        return _preserve_trailing_newline(marked_text, result)

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
        return _dump_marked(root, marked_text)

    def op_delete(self, marked_text: str, short_id: NodeId) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        _delete_at(loc)
        return _dump_marked(root, marked_text)

    def op_replace(self, marked_text: str, short_id: NodeId, new_content: str) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        new_obj = _parse_new_content(new_content)
        node = loc.node
        if _is_scalar_leaf(node):
            _replace_scalar_leaf(node, new_obj)
        elif _is_object_node(node) or isinstance(node.get(_VAL_KEY), list):
            _replace_container_node(node, new_obj, root)
        else:
            raise ValueError("unsupported node kind for replace")
        return _dump_marked(root, marked_text)

    def extract_move_payload(self, marked_text: str, short_id: NodeId) -> str:
        self._enforce_short_id_edit_gate()
        root = _load_marked(marked_text)
        loc = _require_location(root, short_id)
        node = loc.node
        if _is_scalar_leaf(node):
            val = _unwrap(node)
            if isinstance(loc.parent, dict) and isinstance(loc.key, str):
                return json.dumps({loc.key: val}, ensure_ascii=False)
            return json.dumps(val, ensure_ascii=False)
        unmarked = _unwrap(node)
        indent, _ = _detect_json_format(marked_text)
        if isinstance(unmarked, (dict, list)):
            return json.dumps(
                unmarked,
                indent=indent,
                ensure_ascii=False,
                sort_keys=False,
            )
        return json.dumps(unmarked, ensure_ascii=False)

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
        return _dump_marked(root, marked_text)

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
        return _dump_marked(root, marked_text)
