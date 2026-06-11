"""
Resolve node ids and lookups (pointer / simple key path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from .json_pointer import (
    get_value_at,
    key_path_to_segments,
    parse_simple_key_path,
    segments_to_pointer,
)
from .models import JSONTree, stable_node_id_for_pointer

KeyPathInput = Union[str, List[Any]]


def pointer_exists(tree: JSONTree, pointer: str) -> bool:
    try:
        get_value_at(tree.root_data, pointer)
        return True
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def normalize_key_path(key_path: KeyPathInput) -> str:
    if isinstance(key_path, str):
        raw = parse_simple_key_path(key_path)
    else:
        raw = list(key_path)
    str_segs = key_path_to_segments(raw)
    return segments_to_pointer(str_segs)


def resolve_node_id_from_pointer(tree: JSONTree, pointer: str) -> Optional[str]:
    if not pointer_exists(tree, pointer):
        return None
    nid = stable_node_id_for_pointer(pointer)
    if nid not in tree.metadata_map:
        return None
    return nid
