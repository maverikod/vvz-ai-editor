"""
YAML document tree builder — load file, index nodes, session registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
import io
from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple

import yaml
from yaml.loader import SafeLoader
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from ..json_tree.models import stable_node_id_for_pointer
from .models import ROOT_POINTER, YamlNodeMetadata, YamlTree
from .yaml_pointer import join_pointer

_trees: Dict[str, YamlTree] = {}

PointerSpans = Dict[str, Tuple[int, int]]


def _parent_pointer(pointer: str) -> Optional[str]:
    """Return parent JSON Pointer for a non-root pointer."""
    if pointer == ROOT_POINTER:
        return None
    head, sep, _tail = pointer.rpartition("/")
    return head if sep else ROOT_POINTER


def _apply_compose_only_spans(tree: YamlTree, spans: PointerSpans) -> None:
    """Add metadata rows for compose nodes absent from constructed Python data."""
    known = {meta.yaml_pointer for meta in tree.metadata_map.values()}
    for pointer, (start, end) in spans.items():
        if pointer in known:
            continue
        parent_ptr = _parent_pointer(pointer)
        parent_id: Optional[str] = None
        if parent_ptr is not None:
            for meta in tree.metadata_map.values():
                if meta.yaml_pointer == parent_ptr:
                    parent_id = meta.node_id
                    break
        segment = pointer.rsplit("/", 1)[-1] if pointer else None
        node_id = stable_node_id_for_pointer(pointer)
        tree.pointer_by_id[node_id] = pointer
        tree.parent_map[node_id] = parent_id
        tree.metadata_map[node_id] = YamlNodeMetadata(
            node_id=node_id,
            yaml_pointer=pointer,
            kind="unknown",
            parent_id=parent_id,
            key=segment,
            index=int(segment) if segment and segment.isdigit() else None,
            children_ids=[],
            start_line=start,
            end_line=end,
        )


def _yaml_kind(value: Any) -> str:
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


def _mark_lines(node: Node) -> Tuple[int, int]:
    """Return 1-based inclusive (start_line, end_line) from a compose node."""
    return (node.start_mark.line + 1, node.end_mark.line + 1)


def _apply_mapping_entry_span(
    key_node: Node,
    value_node: Node,
    child_pointer: str,
    spans: PointerSpans,
) -> None:
    """Pin mapping-entry span to the key token line (alias-safe)."""
    key_line = key_node.start_mark.line + 1
    val_end = value_node.end_mark.line + 1
    _, existing_end = spans.get(child_pointer, (key_line, val_end))
    spans[child_pointer] = (key_line, max(key_line, existing_end, val_end))


def _mapping_key_segment(key_node: Node) -> str:
    """Return JSON Pointer segment for a compose mapping key (no construction)."""
    if isinstance(key_node, ScalarNode):
        return key_node.value
    raise ValueError(f"Unsupported YAML mapping key node: {type(key_node).__name__}")


def _collect_pointer_spans(
    node: Node,
    pointer: str,
    spans: PointerSpans,
) -> None:
    """Walk compose graph and record 1-based line spans per JSON Pointer."""
    spans[pointer] = _mark_lines(node)

    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            key = _mapping_key_segment(key_node)
            child_pointer = join_pointer(pointer, key)
            _collect_pointer_spans(value_node, child_pointer, spans)
            _apply_mapping_entry_span(key_node, value_node, child_pointer, spans)
    elif isinstance(node, SequenceNode):
        for index, item_node in enumerate(node.value):
            child_pointer = join_pointer(pointer, str(index))
            _collect_pointer_spans(item_node, child_pointer, spans)


def _parse_yaml_text(source: str) -> Tuple[Any, PointerSpans]:
    """Parse YAML text via compose graph; return data and pointer line spans."""
    loaded = yaml.safe_load(source)
    if loaded is None:
        loaded = {}

    loader = SafeLoader(io.StringIO(source))
    try:
        root_node = loader.get_single_node()
        if root_node is None:
            return loaded, {}
        spans: PointerSpans = {}
        _collect_pointer_spans(root_node, ROOT_POINTER, spans)
    finally:
        loader.dispose()
    return loaded, spans


def _build_index(tree: YamlTree, *, line_spans: Optional[PointerSpans] = None) -> None:
    tree.metadata_map.clear()
    tree.parent_map.clear()
    tree.pointer_by_id.clear()
    tree.root_node_id = None
    spans = line_spans or {}

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
        kind = _yaml_kind(value)

        if isinstance(value, dict):
            for k in value.keys():
                child_pointer = join_pointer(pointer, str(k))
                cid = visit(value[k], child_pointer, node_id, str(k), None)
                children_ids.append(cid)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                child_pointer = join_pointer(pointer, str(i))
                cid = visit(item, child_pointer, node_id, None, i)
                children_ids.append(cid)

        start_line: Optional[int] = None
        end_line: Optional[int] = None
        if pointer in spans:
            start_line, end_line = spans[pointer]

        meta = YamlNodeMetadata(
            node_id=node_id,
            yaml_pointer=pointer,
            kind=kind,
            parent_id=parent_id,
            key=key,
            index=index,
            children_ids=children_ids,
            start_line=start_line,
            end_line=end_line,
        )
        tree.metadata_map[node_id] = meta
        if pointer == ROOT_POINTER:
            tree.root_node_id = node_id
        return node_id

    visit(tree.root_data, ROOT_POINTER, None, None, None)
    if line_spans:
        _apply_compose_only_spans(tree, line_spans)


def load_file_to_tree(file_path: str) -> YamlTree:
    """Load a .yaml/.yml file, parse, index, register session."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    suf = path.suffix.lower()
    if suf not in (".yaml", ".yml"):
        raise ValueError(f"File must be .yaml or .yml: {file_path}")

    raw = path.read_text(encoding="utf-8")
    try:
        return build_yaml_tree_from_text(str(path.resolve()), raw, register=True)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e


def build_yaml_tree_from_text(
    file_path: str,
    source: str,
    *,
    register: bool = False,
) -> YamlTree:
    """
    Parse YAML source with compose line marks, index, optionally register session.

    When ``register`` is False (e.g. preview one-shot), tree_id is still unique
    but the session is not stored in ``_trees``.
    """
    loaded, spans = _parse_yaml_text(source)
    tree = YamlTree.create(file_path, copy.deepcopy(loaded))
    _build_index(tree, line_spans=spans)
    if register:
        _trees[tree.tree_id] = tree
    return tree


def build_yaml_tree_from_data(
    file_path: str, data: Any, *, register: bool = False
) -> YamlTree:
    """
    Index YAML value; optionally register session.

    Line spans are not available without source text; use
    :func:`build_yaml_tree_from_text` when parse-time line numbers are required.

    When register is False (e.g. list_yaml_blocks one-shot), tree_id is still unique
    but the session is not stored in ``_trees``.
    """
    tree = YamlTree.create(file_path, copy.deepcopy(data))
    _build_index(tree)
    if register:
        _trees[tree.tree_id] = tree
    return tree


def get_tree(tree_id: str) -> Optional[YamlTree]:
    return _trees.get(tree_id)


def remove_tree(tree_id: str) -> bool:
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False
