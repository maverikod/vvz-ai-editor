"""TreeNode mutation helpers for tree-temp universal_file_edit (G-003).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple, cast

import yaml

from ai_editor.commands.universal_file_edit.insert_position import (
    coalesce_tree_temp_insert_position,
)
from ai_editor.core.tree_temp.identity import TreeTempIdentityMap
from ai_editor.core.tree_temp.tree_node import TreeNode

#: Where a mutation may carry the node it addresses, most specific first. Every
#: one of them now takes the SAME address language -- the integer short_id the
#: frozen surface hands out in ``node_ref``, the ``stable_id`` UUID4, or a JSON
#: Pointer in either declared form -- because all three resolve through one
#: identity map (``ai_editor/core/tree_temp/identity.py``).
_TARGET_ADDRESS_FIELDS = ("target_stable_id", "target_node_id", "node_id", "node_ref")

_MISSING_TARGET_MESSAGE = (
    "tree-temp operation requires a node address in target_stable_id, "
    "target_node_id/node_id/node_ref (integer short_id or stable_id UUID), "
    "or json_pointer"
)


def _identity_for(
    roots: List[TreeNode], identity: Optional[TreeTempIdentityMap]
) -> TreeTempIdentityMap:
    """The caller's session-scoped identity map, levelled with ``roots``.

    A caller that owns an open session passes its map, and the integers it
    issues therefore outlive every edit. A caller with no session (a direct
    single-shot mutation) gets a map derived from this document alone: the same
    three address forms resolve, but the integers only mean anything for the
    duration of the call, because there is no session to remember them.
    """
    return (identity or TreeTempIdentityMap()).sync(roots)


def _address_from(mop: Dict[str, Any]) -> Optional[Any]:
    """The node address this operation carries, or ``None`` when it carries none."""
    for field in _TARGET_ADDRESS_FIELDS:
        raw = mop.get(field)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if "json_pointer" in mop:
        return str(mop["json_pointer"])
    return None


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


def _resolve_target_node(
    mop: Dict[str, Any],
    identity: TreeTempIdentityMap,
) -> TreeNode:
    """The node this operation addresses, through the one identity map.

    Every accepted form goes down the same path, which is the whole point: the
    integer ``node_ref`` ``universal_file_preview`` reports, the ``stable_id``
    UUID4, and a JSON Pointer in either the editor's bracket form or the
    engine's RFC 6901 form all name one node.
    """
    address = _address_from(mop)
    if address is None:
        raise ValueError(_MISSING_TARGET_MESSAGE)
    return identity.node(address)


def _merge_payload_keep_identity(dst: TreeNode, src: TreeNode) -> None:
    """Replace ``dst``'s payload with ``src``'s, preserving ``dst``'s comments.

    Fix for bug 20b4ba84 residual, symptom 1: ``src`` is always a freshly
    built node from a raw replacement value (see ``_value_to_single_node``),
    which never carries ``comment_before``/``comment_inline`` (raw payload
    values have no comment metadata). Previously this function copied those
    always-``None`` fields onto ``dst`` unconditionally, which silently
    deleted any round-trip comment (e.g. an inline ``# ...`` on a mapping
    entry) that the *original* parsed node at this position carried, on
    every "replace" mutation regardless of format. A value replace should
    only change the value, not erase comments attached to that tree
    position.
    """
    dst.type = src.type
    dst.value = src.value
    dst.children = src.children


def _resolve_insert_parent(
    mop: Dict[str, Any],
    identity: TreeTempIdentityMap,
) -> TreeNode:
    """Resolve the parent TreeNode for an insert operation.

    Supports:
    - ``parent_json_pointer``: a JSON Pointer to the parent node, in the
      editor's bracket array form or in RFC 6901. The ``/-`` suffix (e.g.
      ``/concepts/-``) is accepted per RFC 6901 §4 and resolves to the array
      parent without an explicit ``index``; the caller (``_apply_insert``)
      then appends.
    - ``parent_node_id``: any node address the identity map accepts -- the
      integer short_id from preview as readily as the ``stable_id`` UUID4.
    """
    if "parent_json_pointer" in mop:
        ptr = str(mop["parent_json_pointer"])
        # RFC 6901 §4: "-" is the append sentinel for arrays.
        # Strip the trailing "/-" so we resolve the array itself.
        if ptr.endswith("/-"):
            ptr = ptr[:-2] or ""
        return identity.node(ptr)
    p_raw = mop.get("parent_node_id")
    if isinstance(p_raw, bool):
        raise ValueError(f"parent_node_id is not a node address: {p_raw!r}")
    if isinstance(p_raw, int):
        return identity.node(p_raw)
    if isinstance(p_raw, str) and p_raw.strip():
        return identity.node(p_raw.strip())
    raise ValueError("insert requires parent_json_pointer or parent_node_id")


def _find_child_index_by_stable(children: List[TreeNode], stable: str) -> Optional[int]:
    for i, ch in enumerate(children):
        if ch.stable_id == stable:
            return i
    return None


def _coalesce_insert_pointer_sibling_ids(
    mop: Dict[str, Any],
    identity: TreeTempIdentityMap,
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
        mop["before_node_id"] = identity.node(str(before_ptr)).stable_id
    if after_ptr is not None:
        if mop.get("after_node_id"):
            raise ValueError(
                "after_json_pointer and after_node_id are mutually exclusive"
            )
        mop["after_node_id"] = identity.node(str(after_ptr)).stable_id


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


def _coalesce_sibling_insert_anchor(
    roots: List[TreeNode],
    mop: Dict[str, Any],
    identity: TreeTempIdentityMap,
) -> None:
    """Translate a node address + plain ``position`` into parent + sibling anchor.

    A ``node_ref`` from ``universal_file_preview`` combined with
    ``position: 'before'``/``'after'`` names the SIBLING to insert next to, not
    the parent (bug b215fbd3). The address is resolved through the identity map
    like every other one, so the integer short_id, the ``stable_id`` UUID4 and a
    JSON Pointer are interchangeable here too. A no-op when a parent or a
    sibling anchor is already given explicitly.
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
    if isinstance(anchor_raw, bool) or not isinstance(anchor_raw, (int, str)):
        return
    if isinstance(anchor_raw, str) and not anchor_raw.strip():
        return
    anchor_node = identity.node(
        anchor_raw.strip() if isinstance(anchor_raw, str) else anchor_raw
    )
    sid = anchor_node.stable_id
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
    identity: Optional[TreeTempIdentityMap] = None,
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
    to; ``_coalesce_sibling_insert_anchor`` resolves the parent and anchor
    from that sibling before parent resolution below (bug b215fbd3).

    RFC 6901 ``/-`` suffix in ``parent_json_pointer`` is resolved by
    ``_resolve_insert_parent``; this function always appends in that case
    (no ``index`` is set by the caller).

    Args:
        roots: List of root TreeNodes representing the document.
        handler_id: Format handler identifier ('json' or 'yaml').
        mop: Mutation operation dict with insert parameters.
        identity: The session's identity map. Omitted only by a caller with no
            session, which then addresses within this document alone.
    """
    if "value" not in mop:
        raise ValueError("insert requires value")
    address_map = _identity_for(roots, identity)
    coalesce_tree_temp_insert_position(mop)
    _coalesce_sibling_insert_anchor(roots, mop, address_map)
    parent = _resolve_insert_parent(mop, address_map)
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
        _coalesce_insert_pointer_sibling_ids(mop, address_map)
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
    identity: Optional[TreeTempIdentityMap] = None,
) -> None:
    """Apply one normalized modify-tree operation to TreeNode roots (mutates in place).

    Args:
        roots: List of root TreeNodes representing the document.
        handler_id: Format handler identifier ('json' or 'yaml').
        mop: Mutation operation dict with 'action', target, and value fields.
        idx_map: Stable-id index mapping stable_id to (holder, index) tuples.
        identity: The session's identity map, or None for a document with no
            session behind it.
    """
    action = str(mop.get("action") or "").lower()
    if action == "insert":
        _apply_insert(roots, handler_id, mop, identity)
        return
    address_map = _identity_for(roots, identity)
    if action == "replace":
        if "value" not in mop:
            raise ValueError("replace requires value")
        target = _resolve_target_node(mop, address_map)
        new_node = _value_to_single_node(handler_id, mop["value"])
        _merge_payload_keep_identity(target, new_node)
        return
    if action == "delete":
        if _address_from(mop) is None:
            raise ValueError("delete requires json_pointer or stable target")
        doomed = _resolve_target_node(mop, address_map)
        location = idx_map.get(doomed.stable_id)
        if location is None or location[0] is roots:
            raise ValueError("cannot delete or relocate the document root")
        holder, index = location
        del holder[index]
        return
    raise ValueError(f"Unknown tree-temp action: {action!r}")


def apply_single_tree_temp_mutation(
    roots: List[TreeNode],
    handler_id: str,
    mop: Dict[str, Any],
    identity: Optional[TreeTempIdentityMap] = None,
) -> None:
    """Apply one normalized modify-tree operation to TreeNode roots (mutates in place).

    ``identity`` is the open session's node-identity map. Passing it is what
    keeps an integer ``node_ref`` meaning the same node across a whole editing
    session; omitting it (a caller with no session) still resolves every
    address form, but only against this document as it stands right now.
    """
    idx_map = _stable_index(roots)
    _apply_one_mutation(roots, handler_id, mop, idx_map, identity)
