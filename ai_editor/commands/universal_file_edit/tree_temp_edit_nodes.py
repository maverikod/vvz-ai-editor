"""TreeNode mutation helpers for tree-temp universal_file_edit (G-003).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple, cast

import yaml

from ai_editor.core.json_tree.json_pointer import (
    pointer_to_segments,
    segments_to_pointer,
)
from ai_editor.commands.universal_file_edit.insert_position import (
    coalesce_tree_temp_insert_position,
)
from ai_editor.core.tree_temp.tree_node import TreeNode


def _is_uuid_v4_string(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 4
    except ValueError:
        return False


def _stable_index(roots: List[TreeNode]) -> Dict[str, Tuple[List[TreeNode], int]]:
    out: Dict[str, Tuple[List[TreeNode], int]] = {}

    def walk(node: TreeNode, holder: List[TreeNode], idx: int) -> None:
        out[node.stable_id] = (holder, idx)
        if node.children:
            for i, ch in enumerate(node.children):
                walk(ch, node.children, i)

    for i, r in enumerate(roots):
        walk(r, roots, i)
    return out


def serialize_tree_temp_roots(handler_id: str, roots: List[TreeNode]) -> str:
    if handler_id == "json":
        from ai_editor.core.tree_temp.json_source_serializer import (
            serialize_json_source,
        )

        return cast(str, serialize_json_source(roots))
    if handler_id == "yaml":
        from ai_editor.core.tree_temp.yaml_source_serializer import (
            serialize_yaml_source,
        )

        return cast(str, serialize_yaml_source(roots))
    if handler_id == "ini":
        from ai_editor.core.tree_temp.ini_source_serializer import (
            serialize_ini_source,
        )

        return cast(str, serialize_ini_source(roots))
    if handler_id == "toml":
        from ai_editor.core.tree_temp.toml_source_serializer import (
            serialize_toml_source,
        )

        return cast(str, serialize_toml_source(roots))
    raise ValueError(f"Unsupported handler for tree-temp: {handler_id!r}")


def _json_scalar_tree_node(value: Any) -> TreeNode:
    """Build a TreeNode for a JSON scalar without round-tripping via tolerant JSON text.

    Bare integer strings like ``\"7\"`` are mis-parsed by ``parse_json_source`` (exponent
    grammar); replace/insert must still accept Python ``int``/``float`` payloads.
    """
    if value is None:
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="null",
            key=None,
            value=None,
            children=None,
        )
    if isinstance(value, bool):
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="boolean",
            key=None,
            value=value,
            children=None,
        )
    if isinstance(value, int) and not isinstance(value, bool):
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="number",
            key=None,
            value=value,
            children=None,
        )
    if isinstance(value, float):
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="number",
            key=None,
            value=value,
            children=None,
        )
    if isinstance(value, str):
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="string",
            key=None,
            value=value,
            children=None,
        )
    raise ValueError(f"unsupported JSON scalar for tree-temp: {type(value).__name__}")


def _value_to_tree_roots(handler_id: str, value: Any) -> List[TreeNode]:
    """Convert a Python value to a list of TreeNode roots.

    For JSON handler: delegates to parse_json_source (wraps list/dict in one root).
    For YAML handler: dumps to YAML text and parses with parse_yaml_source.
    YAML top-level sequences yield N scalar roots; callers that need exactly one
    node must call _value_to_single_node instead.

    Args:
        handler_id: Format handler identifier ('json' or 'yaml').
        value: Python value to convert.

    Returns:
        List of TreeNode roots representing the value.
    """
    if handler_id == "json":
        from ai_editor.core.tree_temp.json_source_parser import parse_json_source

        if isinstance(value, (dict, list)):
            return cast(
                List[TreeNode],
                parse_json_source(json.dumps(value, ensure_ascii=False)),
            )
        return [_json_scalar_tree_node(value)]

    from ai_editor.core.tree_temp.yaml_source_parser import parse_yaml_source

    dumped = yaml.safe_dump(
        value,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return cast(List[TreeNode], parse_yaml_source(dumped))


def _value_to_single_node(handler_id: str, value: Any) -> TreeNode:
    """Convert a Python value to exactly one TreeNode.

    Unlike _value_to_tree_roots, always returns a single node suitable for
    replace and insert operations. When the YAML parser returns multiple roots
    (top-level sequence yields one scalar per element), wraps them in an
    array TreeNode so the caller always receives exactly one node,
    consistent with JSON behaviour.

    For YAML, container shape is taken from the Python ``value`` (list -> array,
    dict -> object) because ``parse_yaml_source`` returns one root per top-level
    sequence element and loses the array wrapper when N=1. The same ambiguity
    affects ``parse_json_source`` for one-element lists, so both handlers use the
    Python value here instead of inferring container type from parsed roots.

    Args:
        handler_id: Format handler identifier ('json' or 'yaml').
        value: Python value to convert.

    Returns:
        Single TreeNode representing the value.
    """
    if handler_id in {"ini", "toml"}:
        return _generic_value_to_single_node(value)
    if isinstance(value, list):
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="array",
            key=None,
            value=None,
            children=[_value_to_single_node(handler_id, element) for element in value],
        )
    if isinstance(value, dict):
        children: List[TreeNode] = []
        for key, item in value.items():
            child = _value_to_single_node(handler_id, item)
            child.key = str(key)
            children.append(child)
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="object",
            key=None,
            value=None,
            children=children,
        )

    roots = _value_to_tree_roots(handler_id, value)
    if len(roots) == 1:
        return roots[0]
    # YAML top-level sequence (>=2 elements): parser returns one root per element.
    # Wrap them into a single array TreeNode so replace/insert always
    # receive exactly one node, consistent with JSON behaviour.
    return TreeNode(
        stable_id=str(uuid.uuid4()),
        type="array",
        key=None,
        value=None,
        children=list(roots),
    )


def _generic_value_to_single_node(value: Any) -> TreeNode:
    """Build a format-neutral node for the round-trip config serializers."""
    if value is None:
        return TreeNode(stable_id=str(uuid.uuid4()), type="null", value=None)
    if isinstance(value, bool):
        return TreeNode(stable_id=str(uuid.uuid4()), type="boolean", value=value)
    if isinstance(value, (int, float)):
        return TreeNode(stable_id=str(uuid.uuid4()), type="number", value=value)
    if isinstance(value, str):
        return TreeNode(stable_id=str(uuid.uuid4()), type="string", value=value)
    if isinstance(value, list):
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="array",
            value=None,
            children=[_generic_value_to_single_node(item) for item in value],
        )
    if isinstance(value, dict):
        children: List[TreeNode] = []
        for key, item in value.items():
            child = _generic_value_to_single_node(item)
            child.key = str(key)
            children.append(child)
        return TreeNode(
            stable_id=str(uuid.uuid4()),
            type="object",
            value=None,
            children=children,
        )
    raise ValueError(f"unsupported tree-temp value: {type(value).__name__}")


def _regenerate_stable_ids(node: TreeNode) -> TreeNode:
    new_children = None
    if node.children is not None:
        new_children = [_regenerate_stable_ids(ch) for ch in node.children]
    return TreeNode(
        stable_id=str(uuid.uuid4()),
        type=node.type,
        key=node.key,
        value=node.value,
        children=new_children,
        comment_before=node.comment_before,
        comment_inline=node.comment_inline,
    )


def _node_after_segments(cur: TreeNode, segs: List[str]) -> TreeNode:
    for seg in segs:
        if cur.type == "array":
            idx = int(seg)
            ch = cur.children
            if ch is None or idx < 0 or idx >= len(ch):
                raise ValueError(f"JSON Pointer segment {seg!r} out of range")
            cur = ch[idx]
        elif cur.type == "object":
            if cur.children is None:
                raise ValueError("object node missing children during pointer walk")
            found: Optional[TreeNode] = None
            for c in cur.children:
                if c.key == seg:
                    found = c
                    break
            if found is None:
                raise ValueError(f"object has no key {seg!r}")
            cur = found
        else:
            raise ValueError("cannot traverse JSON Pointer through scalar TreeNode")
    return cur


def _resolve_pointer_node(roots: List[TreeNode], pointer: str) -> TreeNode:
    segs = pointer_to_segments(pointer)
    if len(roots) > 1:
        if not segs:
            raise ValueError("non-empty JSON Pointer required for multi-root tree")
        idx = int(segs[0])
        if idx < 0 or idx >= len(roots):
            raise ValueError("root index out of range")
        cur = roots[idx]
        return _node_after_segments(cur, segs[1:])
    if not roots:
        raise ValueError("empty roots")
    if not segs:
        return roots[0]
    return _node_after_segments(roots[0], segs)


def _parent_holder_and_last_seg(
    roots: List[TreeNode], pointer: str
) -> Tuple[List[TreeNode], int, str]:
    segs = pointer_to_segments(pointer)
    if not segs:
        raise ValueError("cannot delete or relocate root via empty JSON Pointer")
    parent_ptr = segments_to_pointer(segs[:-1])
    last_seg = segs[-1]
    if not parent_ptr:
        if len(roots) > 1:
            return roots, int(last_seg), last_seg
        parent_node = roots[0]
    else:
        parent_node = _resolve_pointer_node(roots, parent_ptr)
    if parent_node.type == "object":
        ch = parent_node.children
        if ch is None:
            raise ValueError("object parent missing children")
        for i, c in enumerate(ch):
            if c.key == last_seg:
                return ch, i, last_seg
        raise ValueError(f"object parent has no key {last_seg!r}")
    if parent_node.type == "array":
        ch = parent_node.children
        if ch is None:
            raise ValueError("array parent missing children")
        idx = int(last_seg)
        if idx < 0 or idx >= len(ch):
            raise ValueError("array index out of range")
        return ch, idx, last_seg
    raise ValueError("JSON Pointer parent must be object or array")


def _extract_stable_target(mop: Dict[str, Any]) -> Optional[str]:
    ts = mop.get("target_stable_id")
    if isinstance(ts, str) and ts.strip():
        return ts.strip()
    for key in ("target_node_id", "node_id"):
        raw = mop.get(key)
        if isinstance(raw, str) and raw.strip() and _is_uuid_v4_string(raw.strip()):
            return raw.strip()
    return None


def _resolve_target_node(
    roots: List[TreeNode],
    mop: Dict[str, Any],
    idx_map: Dict[str, Tuple[List[TreeNode], int]],
) -> TreeNode:
    sid = _extract_stable_target(mop)
    if sid is not None:
        loc = idx_map.get(sid)
        if loc is None:
            raise ValueError(f"stable_id not found: {sid}")
        holder, idx = loc
        return holder[idx]
    if "json_pointer" in mop:
        return _resolve_pointer_node(roots, str(mop["json_pointer"]))
    raise ValueError(
        "tree-temp operation requires target_stable_id, uuid-like target_node_id/node_id, "
        "or json_pointer"
    )


def _merge_payload_keep_identity(dst: TreeNode, src: TreeNode) -> None:
    dst.type = src.type
    dst.value = src.value
    dst.children = src.children
    dst.comment_before = src.comment_before
    dst.comment_inline = src.comment_inline


def _resolve_insert_parent(
    roots: List[TreeNode],
    mop: Dict[str, Any],
    idx_map: Dict[str, Tuple[List[TreeNode], int]],
) -> TreeNode:
    """Resolve the parent TreeNode for an insert operation.

    Supports:
    - ``parent_json_pointer``: RFC 6901 pointer to the parent node.
      The special sentinel ``/-`` suffix (e.g. ``/concepts/-``) is accepted
      per RFC 6901 §4 and resolves to the array parent without requiring
      an explicit ``index``; the caller (``_apply_insert``) will append.
    - ``parent_node_id``: opaque stable UUID of the parent node.
    """
    if "parent_json_pointer" in mop:
        ptr = str(mop["parent_json_pointer"])
        # RFC 6901 §4: "-" is the append sentinel for arrays.
        # Strip the trailing "/-" so we resolve the array itself.
        if ptr.endswith("/-"):
            ptr = ptr[:-2] or ""
        # Bare "/" is accepted as a convenience alias for the document root
        # (matching the legacy marked-tree resolver this path replaces for
        # bug b215fbd3): a lone slash is otherwise indistinguishable from
        # "root has a single '' key", which no caller intends here.
        if ptr == "/":
            ptr = ""
        return _resolve_pointer_node(roots, ptr)
    p_raw = mop.get("parent_node_id")
    if isinstance(p_raw, str) and p_raw.strip():
        sid = p_raw.strip()
        loc = idx_map.get(sid)
        if loc is None:
            raise ValueError(f"parent_node_id stable_id not found: {sid}")
        holder, idx = loc
        return holder[idx]
    raise ValueError("insert requires parent_json_pointer or parent_node_id")


def _find_child_index_by_stable(children: List[TreeNode], stable: str) -> Optional[int]:
    for i, ch in enumerate(children):
        if ch.stable_id == stable:
            return i
    return None


def _coalesce_insert_pointer_sibling_ids(
    roots: List[TreeNode],
    mop: Dict[str, Any],
) -> None:
    """Resolve ``before_json_pointer`` / ``after_json_pointer`` to sibling stable UUIDs."""
    before_ptr = mop.get("before_json_pointer")
    after_ptr = mop.get("after_json_pointer")
    if before_ptr is not None and after_ptr is not None:
        raise ValueError(
            "before_json_pointer and after_json_pointer are mutually exclusive"
        )
    if before_ptr is not None:
        if mop.get("before_node_id"):
            raise ValueError(
                "before_json_pointer and before_node_id are mutually exclusive"
            )
        node = _resolve_pointer_node(roots, str(before_ptr))
        mop["before_node_id"] = node.stable_id
    if after_ptr is not None:
        if mop.get("after_node_id"):
            raise ValueError(
                "after_json_pointer and after_node_id are mutually exclusive"
            )
        node = _resolve_pointer_node(roots, str(after_ptr))
        mop["after_node_id"] = node.stable_id


def _find_parent_node(roots: List[TreeNode], stable_id: str) -> Optional[TreeNode]:
    """Return the parent TreeNode of ``stable_id``, or None when it is a root."""

    def walk(node: TreeNode) -> Optional[TreeNode]:
        if not node.children:
            return None
        for child in node.children:
            if child.stable_id == stable_id:
                return node
            found = walk(child)
            if found is not None:
                return found
        return None

    for r in roots:
        if r.stable_id == stable_id:
            return None
        found = walk(r)
        if found is not None:
            return found
    return None


def _legacy_short_id_index(roots: List[TreeNode]) -> Dict[int, TreeNode]:
    """Recompute the legacy preview short_id numbering over ``roots``.

    ``universal_file_preview`` falls back, for a tree-temp session with no
    marked-tree MAP file, to an ephemeral generic re-parse of the draft that
    numbers every node in preorder (root-first depth-first) starting at 1.
    Reproducing that SAME numbering directly against the persistent
    ``tree_temp_roots`` forest (bug b215fbd3) lets ``target_node_id`` /
    ``node_ref`` values copied from a preview response resolve back to the
    node the user actually pointed at, without reviving the retired
    marked-tree MAP file.
    """
    out: Dict[int, TreeNode] = {}
    counter = 0

    def visit(node: TreeNode) -> None:
        nonlocal counter
        counter += 1
        out[counter] = node
        if node.children:
            for ch in node.children:
                visit(ch)

    for r in roots:
        visit(r)
    return out


def _coalesce_legacy_insert_anchor(
    roots: List[TreeNode],
    mop: Dict[str, Any],
    idx_map: Dict[str, Tuple[List[TreeNode], int]],
) -> None:
    """Translate ``target_node_id``/``node_id`` + plain ``position`` into a
    parent + sibling-anchor insert (bug b215fbd3 preview short_id/node_ref
    addressing: a preview ``node_ref`` names the sibling to insert next to,
    not a parent). Formerly resolved via the marked-tree short_id system;
    this resolves directly against the tree-temp ``roots`` instead (stable_id
    UUID, or a legacy preview short_id integer via ``_legacy_short_id_index``).
    A no-op when a parent or sibling anchor is already given explicitly.
    """
    if mop.get("parent_json_pointer") or mop.get("parent_node_id"):
        return
    if (
        mop.get("before_node_id")
        or mop.get("after_node_id")
        or mop.get("before_key")
        or mop.get("after_key")
    ):
        return
    position = mop.get("position")
    if not isinstance(position, str):
        return
    side = position.strip().lower()
    if side not in ("before", "after"):
        return
    anchor_raw = mop.get("target_node_id") or mop.get("node_id")
    if not isinstance(anchor_raw, str) or not anchor_raw.strip():
        return
    sid = anchor_raw.strip()
    if sid.isdigit():
        legacy_node = _legacy_short_id_index(roots).get(int(sid))
        if legacy_node is None:
            raise ValueError(f"stable_id not found: {sid}")
        sid = legacy_node.stable_id
    loc = idx_map.get(sid)
    if loc is None:
        raise ValueError(f"stable_id not found: {sid}")
    holder, idx = loc
    anchor_node = holder[idx]
    parent = _find_parent_node(roots, sid)
    if parent is None:
        raise ValueError("insert requires parent_json_pointer or parent_node_id")
    mop["parent_node_id"] = parent.stable_id
    if parent.type == "object":
        if not isinstance(anchor_node.key, str):
            raise ValueError(f"sibling anchor has no key: {sid}")
        mop["before_key" if side == "before" else "after_key"] = anchor_node.key
    else:
        mop["before_node_id" if side == "before" else "after_node_id"] = sid
    mop.pop("position", None)


def _apply_insert(
    roots: List[TreeNode],
    handler_id: str,
    mop: Dict[str, Any],
    idx_map: Dict[str, Tuple[List[TreeNode], int]],
) -> None:
    """Apply an insert operation to the tree.

    Supported positioning for arrays:
    - ``position: 'before:<json_pointer>'`` / ``'after:<json_pointer>'`` (preferred).
    - ``before_node_id`` / ``after_node_id``: sibling-relative by stable UUID.
    - ``before_json_pointer`` / ``after_json_pointer``: same as colon form.
    - ``index``: explicit integer index (0-based).
    - ``position: 'last'`` or no positioning fields: append to end.

    Supported positioning for objects:
    - ``position: 'before:<key>'`` / ``'after:<key>'`` (preferred).
    - ``before_key`` / ``after_key``: sibling-relative by key name.
    - ``position: 'last'`` or no positioning fields: append to end.

    ``target_node_id`` / ``node_id`` (preview node_ref addressing) combined
    with plain ``position: 'before'/'after'`` names a SIBLING to insert next
    to; ``_coalesce_legacy_insert_anchor`` resolves the parent and anchor
    from that sibling before parent resolution below (bug b215fbd3).

    RFC 6901 ``/-`` suffix in ``parent_json_pointer`` is resolved by
    ``_resolve_insert_parent``; this function always appends in that case
    (no ``index`` is set by the caller).

    Args:
        roots: List of root TreeNodes representing the document.
        handler_id: Format handler identifier ('json' or 'yaml').
        mop: Mutation operation dict with insert parameters.
        idx_map: Stable-id index mapping stable_id to (holder, index) tuples.
    """
    if "value" not in mop:
        raise ValueError("insert requires value")
    coalesce_tree_temp_insert_position(mop)
    _coalesce_legacy_insert_anchor(roots, mop, idx_map)
    parent = _resolve_insert_parent(roots, mop, idx_map)
    new_node = _value_to_single_node(handler_id, mop["value"])
    fresh = _regenerate_stable_ids(new_node)

    position = mop.get("position")

    if parent.type == "object":
        if parent.children is None:
            parent.children = []
        ch = parent.children
        key = mop.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("insert into object requires string key")
        fresh.key = key
        before_key = mop.get("before_key")
        after_key = mop.get("after_key")
        if before_key is not None or after_key is not None:
            if before_key is not None and after_key is not None:
                raise ValueError("before_key and after_key are mutually exclusive")
            anchor = before_key if isinstance(before_key, str) else after_key
            assert isinstance(anchor, str)
            insert_at = next((i for i, c in enumerate(ch) if c.key == anchor), None)
            if insert_at is None:
                raise ValueError(f"sibling key anchor not found: {anchor!r}")
            if isinstance(after_key, str):
                insert_at += 1
            ch.insert(insert_at, fresh)
            return
        # position: 'last' or no anchor → append
        ch.append(fresh)
        return

    if parent.type == "array":
        if parent.children is None:
            parent.children = []
        ch = parent.children
        _coalesce_insert_pointer_sibling_ids(roots, mop)
        before_nid = mop.get("before_node_id")
        after_nid = mop.get("after_node_id")
        idx_raw = mop.get("index")
        if before_nid is not None or after_nid is not None:
            if before_nid and after_nid:
                raise ValueError(
                    "before_node_id and after_node_id are mutually exclusive"
                )
            sid = str(before_nid or after_nid).strip()
            j = _find_child_index_by_stable(ch, sid)
            if j is None:
                raise ValueError(f"sibling stable_id not found: {sid}")
            insert_at = j if before_nid else j + 1
            ch.insert(insert_at, fresh)
            return
        # position: 'last' or no index → append
        if idx_raw is None or position == "last":
            ch.append(fresh)
            return
        if not isinstance(idx_raw, int):
            raise ValueError("insert into array requires integer index when set")
        ch.insert(idx_raw, fresh)
        return

    raise TypeError(
        f"insert parent must be object or array TreeNode, got {parent.type!r}"
    )


def _apply_one_mutation(
    roots: List[TreeNode],
    handler_id: str,
    mop: Dict[str, Any],
    idx_map: Dict[str, Tuple[List[TreeNode], int]],
) -> None:
    """Apply one normalized modify-tree operation to TreeNode roots (mutates in place).

    Args:
        roots: List of root TreeNodes representing the document.
        handler_id: Format handler identifier ('json' or 'yaml').
        mop: Mutation operation dict with 'action', target, and value fields.
        idx_map: Stable-id index mapping stable_id to (holder, index) tuples.
    """
    action = str(mop.get("action") or "").lower()
    if action == "replace":
        if "value" not in mop:
            raise ValueError("replace requires value")
        target = _resolve_target_node(roots, mop, idx_map)
        new_node = _value_to_single_node(handler_id, mop["value"])
        _merge_payload_keep_identity(target, new_node)
        return
    if action == "delete":
        sid_del = _extract_stable_target(mop)
        if sid_del is not None:
            loc = idx_map.get(sid_del)
            if loc is None:
                raise ValueError(f"stable_id not found: {sid_del}")
            holder, idx = loc
            del holder[idx]
            return
        if "json_pointer" not in mop:
            raise ValueError("delete requires json_pointer or stable target")
        holder, idx, _ = _parent_holder_and_last_seg(roots, str(mop["json_pointer"]))
        del holder[idx]
        return
    if action == "insert":
        _apply_insert(roots, handler_id, mop, idx_map)
        return
    raise ValueError(f"Unknown tree-temp action: {action!r}")


def apply_single_tree_temp_mutation(
    roots: List[TreeNode],
    handler_id: str,
    mop: Dict[str, Any],
) -> None:
    """Apply one normalized modify-tree operation to TreeNode roots (mutates in place)."""
    idx_map = _stable_index(roots)
    _apply_one_mutation(roots, handler_id, mop, idx_map)
