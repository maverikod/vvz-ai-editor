"""
JSON document tree builder — load file, index nodes, session registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .json_pointer import join_pointer
from .models import ROOT_POINTER, JSONTree, JsonNodeMetadata, stable_node_id_for_pointer

logger = logging.getLogger(__name__)

_trees: Dict[str, JSONTree] = {}


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _build_index(tree: JSONTree) -> None:
    tree.metadata_map.clear()
    tree.parent_map.clear()
    tree.pointer_by_id.clear()
    tree.root_node_id = None

    def visit(
        value: Any,
        pointer: str,
        parent_id: Optional[str],
        key: Optional[str],
        index: Optional[int],
    ) -> str:
        node_id = stable_node_id_for_pointer(pointer)
        tree.pointer_by_id[node_id] = pointer
        tree.parent_map[node_id] = parent_id

        children_ids: List[str] = []
        kind = _json_kind(value)

        if isinstance(value, dict):
            for k in value.keys():
                child_pointer = join_pointer(pointer, str(k))
                cid = visit(value[k], child_pointer, node_id, k, None)
                children_ids.append(cid)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                child_pointer = join_pointer(pointer, str(i))
                cid = visit(item, child_pointer, node_id, None, i)
                children_ids.append(cid)

        meta = JsonNodeMetadata(
            node_id=node_id,
            json_pointer=pointer,
            kind=kind,
            parent_id=parent_id,
            key=key,
            index=index,
            children_ids=children_ids,
        )
        tree.metadata_map[node_id] = meta
        if pointer == ROOT_POINTER:
            tree.root_node_id = node_id
        return node_id

    visit(tree.root_data, ROOT_POINTER, None, None, None)


def load_file_to_tree(file_path: str) -> JSONTree:
    """Load a .json file, parse, index, register session."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != ".json":
        raise ValueError(f"File must be .json: {file_path}")

    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    return build_tree_from_data(str(path.resolve()), data, register=True)


def build_tree_from_data(
    file_path: str, data: Any, *, register: bool = False
) -> JSONTree:
    """
    Index JSON value; optionally register session.

    When register is False (e.g. list_json_blocks one-shot), tree_id is still unique
    but the session is not stored in _trees.
    """
    tree = JSONTree.create(file_path, copy.deepcopy(data))
    _build_index(tree)
    if register:
        _trees[tree.tree_id] = tree
    return tree


def get_tree(tree_id: str) -> Optional[JSONTree]:
    return _trees.get(tree_id)


def remove_tree(tree_id: str) -> bool:
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False


def reload_tree_from_file(tree_id: str) -> Optional[JSONTree]:
    """Reload same tree_id from disk."""
    tree = get_tree(tree_id)
    if not tree:
        return None
    path = Path(tree.file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {tree.file_path}")
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    tree.root_data = copy.deepcopy(data)
    tree.file_path = str(path.resolve())
    _build_index(tree)
    return tree
