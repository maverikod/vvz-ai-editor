"""
CST tree modifier operations: replace, delete, insert helpers.

Extracted from tree_modifier for size limit. Used only by tree_modifier.
Facade re-exports from tree_modifier_ops_parse, _find, _replace, _insert.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


from .tree_modifier_ops_find import (
    delete_node,
    find_leaf_node_in_module_by_position,
    find_node_in_module_by_position,
    find_parent_in_module_by_position,
)

from .tree_modifier_ops_insert import (
    insert_node,
    insert_node_at_position,
    insert_node_relative,
)

from .tree_modifier_ops_parse import (
    FINE_GRAINED_REPLACE_NODE_TYPES,
    class_or_function_snippet_needs_full_replace,
    join_code_lines,
    parse_annotation_snippet,
    parse_code_snippet,
    parse_code_snippet_or_comment,
    parse_param_snippet,
)

from .tree_modifier_ops_replace import (
    replace_node,
    replace_node_header_only,
    replace_range,
)

__all__ = [
    "FINE_GRAINED_REPLACE_NODE_TYPES",
    "class_or_function_snippet_needs_full_replace",
    "join_code_lines",
    "parse_annotation_snippet",
    "parse_code_snippet",
    "parse_code_snippet_or_comment",
    "parse_param_snippet",
    "delete_node",
    "find_leaf_node_in_module_by_position",
    "find_node_in_module_by_position",
    "find_parent_in_module_by_position",
    "replace_node",
    "replace_node_header_only",
    "replace_range",
    "insert_node_at_position",
    "insert_node",
    "insert_node_relative",
]
