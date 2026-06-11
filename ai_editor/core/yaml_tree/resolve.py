"""
Resolve node identifiers against an in-memory YAML tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .models import YamlTree
from .yaml_pointer import get_value_at


def resolve_yaml_node(tree: YamlTree, node_ref: str) -> Any | None:
    """
    Resolve ``node_ref`` to a Python value in ``tree.root_data``.

    * ``node_ref == ''`` or starting with ``/`` — treated as a JSON Pointer string.
    * Otherwise — looked up as an opaque stable node id in ``tree.pointer_by_id``.
    """
    try:
        if node_ref == "" or node_ref.startswith("/"):
            return get_value_at(tree.root_data, node_ref)
        ptr = tree.pointer_by_id.get(node_ref)
        if ptr is None:
            return None
        return get_value_at(tree.root_data, ptr)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
