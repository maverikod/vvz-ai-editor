"""
RFC 6901 JSON Pointer helpers (minimal).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple, Union

KeyPathSegment = Union[str, int]


def pointer_to_segments(pointer: str) -> List[str]:
    """
    Parse JSON Pointer into decoded path segments.

    Root "" -> []. Each segment has ~1 -> / and ~0 -> ~.
    """
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(
            f"Invalid JSON Pointer (must be empty or start with /): {pointer!r}"
        )
    parts = pointer[1:].split("/")
    out: List[str] = []
    for p in parts:
        out.append(p.replace("~1", "/").replace("~0", "~"))
    return out


def segments_to_pointer(segments: List[str]) -> str:
    if not segments:
        return ""
    enc = []
    for s in segments:
        esc = s.replace("~", "~0").replace("/", "~1")
        enc.append(esc)
    return "/" + "/".join(enc)


def join_pointer(parent_pointer: str, segment: str) -> str:
    """Append one JSON Pointer segment to a parent pointer."""
    segs = pointer_to_segments(parent_pointer)
    segs.append(segment)
    return segments_to_pointer(segs)


def key_path_to_segments(path: List[KeyPathSegment]) -> List[str]:
    """Turn key_path (str keys, int indices) into JSON Pointer segments (indices as decimal str)."""
    out: List[str] = []
    for p in path:
        if isinstance(p, int):
            out.append(str(p))
        else:
            out.append(str(p))
    return out


def key_path_to_pointer(path: List[KeyPathSegment]) -> str:
    return segments_to_pointer(key_path_to_segments(path))


def get_value_at(data: Any, pointer: str) -> Any:
    """Return value at pointer or raise KeyError/IndexError/TypeError."""
    segs = pointer_to_segments(pointer)
    cur: Any = data
    for seg in segs:
        if isinstance(cur, list):
            cur = cur[int(seg)]
        elif isinstance(cur, dict):
            cur = cur[seg]
        else:
            raise TypeError(f"Cannot traverse into non-container at {pointer!r}")
    return cur


def _parent_and_key(root: Any, pointer: str) -> Tuple[Any, Union[str, int, None]]:
    """
    Return (parent_container, last_segment_or_None_for_root).

    For root "", parent is sentinel None and key None — caller handles.
    """
    segs = pointer_to_segments(pointer)
    if not segs:
        return root, None
    cur = root
    for seg in segs[:-1]:
        if isinstance(cur, list):
            cur = cur[int(seg)]
        elif isinstance(cur, dict):
            cur = cur[seg]
        else:
            raise TypeError(f"Cannot traverse at {pointer!r}")
    last = segs[-1]
    if isinstance(cur, list):
        return cur, int(last)
    if isinstance(cur, dict):
        return cur, last
    raise TypeError(f"Parent is not a container at {pointer!r}")


def set_value_at(root: Any, pointer: str, value: Any) -> None:
    """Set value at pointer (replace existing). Non-empty pointers only; root replace is in modifier."""
    if pointer == "":
        raise ValueError("set_value_at: use explicit root assignment for empty pointer")

    parent, lk = _parent_and_key(root, pointer)
    if isinstance(parent, list) and isinstance(lk, int):
        parent[lk] = value
    elif isinstance(parent, dict) and isinstance(lk, str):
        parent[lk] = value
    else:
        raise TypeError("set_value_at: invalid parent")


def delete_at(root: Any, pointer: str) -> None:
    """Remove key from object or element from array. Cannot delete root."""
    if pointer == "":
        raise ValueError("Cannot delete root document")

    parent, lk = _parent_and_key(root, pointer)
    if isinstance(parent, list) and isinstance(lk, int):
        del parent[lk]
    elif isinstance(parent, dict) and isinstance(lk, str):
        del parent[lk]
    else:
        raise TypeError("delete_at: invalid parent")


def insert_into_object(root: Any, parent_pointer: str, key: str, value: Any) -> None:
    parent = get_value_at(root, parent_pointer)
    if not isinstance(parent, dict):
        raise TypeError("insert_into_object: parent is not an object")
    if key in parent:
        raise KeyError(f"Key already exists: {key!r}")
    parent[key] = value


def insert_into_object_relative(
    root: Any,
    parent_pointer: str,
    key: str,
    value: Any,
    *,
    before_key: Optional[str] = None,
    after_key: Optional[str] = None,
) -> None:
    """Insert key into object at a position relative to an existing sibling key."""
    parent = get_value_at(root, parent_pointer)
    if not isinstance(parent, dict):
        raise TypeError("insert_into_object_relative: parent is not an object")
    if key in parent:
        raise KeyError(f"Key already exists: {key!r}")
    anchor = before_key if before_key is not None else after_key
    if anchor is None:
        raise ValueError("insert_into_object_relative requires before_key or after_key")
    if anchor not in parent:
        raise KeyError(f"Sibling key not found: {anchor!r}")
    new_dict: dict[str, Any] = {}
    for k, v in parent.items():
        if after_key is not None and k == anchor:
            new_dict[k] = v
            new_dict[key] = value
        elif before_key is not None and k == anchor:
            new_dict[key] = value
            new_dict[k] = v
        else:
            new_dict[k] = v
    parent.clear()
    parent.update(new_dict)


def insert_into_array(
    root: Any, parent_pointer: str, value: Any, index: Optional[int] = None
) -> None:
    parent = get_value_at(root, parent_pointer)
    if not isinstance(parent, list):
        raise TypeError("insert_into_array: parent is not an array")
    if index is None:
        parent.append(value)
    else:
        parent.insert(index, value)


# Simple key path lookup (dot-free): list of str keys and int indices
def resolve_key_path(root: Any, path: List[KeyPathSegment]) -> Any:
    cur: Any = root
    for p in path:
        if isinstance(cur, list):
            if not isinstance(p, int):
                raise TypeError(f"Expected int index in path, got {p!r}")
            cur = cur[p]
        elif isinstance(cur, dict):
            if not isinstance(p, str):
                raise TypeError(f"Expected str key in path, got {p!r}")
            cur = cur[p]
        else:
            raise TypeError("Cannot traverse key_path past non-container")
    return cur


def parse_simple_key_path(query: str) -> List[KeyPathSegment]:
    """
    Parse 'a.b.0.c' style path: dot-separated, numeric segments = array indices.

    For keys containing dots or special chars, use json_pointer instead.
    """
    if not query.strip():
        return []
    parts = query.split(".")
    out: List[KeyPathSegment] = []
    for p in parts:
        if p.isdigit():
            out.append(int(p))
        else:
            out.append(p)
    return out
