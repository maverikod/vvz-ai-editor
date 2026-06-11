"""
YAML preview uses RFC 6901 JSON Pointer paths; reuse json_tree helpers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ..json_tree import json_pointer as _jp

# Re-export commonly used JSON Pointer helpers for YAML paths.
KeyPathSegment = _jp.KeyPathSegment
delete_at = _jp.delete_at
get_value_at = _jp.get_value_at
insert_into_array = _jp.insert_into_array
insert_into_object = _jp.insert_into_object
join_pointer = _jp.join_pointer
key_path_to_pointer = _jp.key_path_to_pointer
key_path_to_segments = _jp.key_path_to_segments
parse_simple_key_path = _jp.parse_simple_key_path
pointer_to_segments = _jp.pointer_to_segments
resolve_key_path = _jp.resolve_key_path
segments_to_pointer = _jp.segments_to_pointer
set_value_at = _jp.set_value_at

__all__ = [
    "KeyPathSegment",
    "delete_at",
    "get_value_at",
    "insert_into_array",
    "insert_into_object",
    "join_pointer",
    "key_path_to_pointer",
    "key_path_to_segments",
    "parse_simple_key_path",
    "pointer_to_segments",
    "resolve_key_path",
    "segments_to_pointer",
    "set_value_at",
]
