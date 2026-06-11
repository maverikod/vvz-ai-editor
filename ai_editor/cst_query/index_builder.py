"""
Index builder for CSTQuery execution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from ..core.cst_tree.node_id_markers import (
    PersistedNodeIds,
    build_marker_path,
    build_exact_node_key,
    strip_persisted_node_ids,
)
from ..core.cst_tree.node_type_utils import (
    get_node_kind,
    get_node_name,
    get_node_qualname,
)


@dataclass(frozen=True)
class Match:
    """A single selector match."""

    node_id: str
    kind: str
    node_type: str
    name: Optional[str]
    qualname: Optional[str]
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    code: Optional[str] = None


@dataclass(frozen=True)
class NodeInfo:
    """Indexed node metadata used by query execution."""

    node: cst.CSTNode
    parent: Optional[cst.CSTNode]
    depth: int
    kind: str
    name: Optional[str]
    qualname: Optional[str]
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    node_id: str
    extra_attrs: Optional[dict[str, str]] = None

    @property
    def node_type(self) -> str:
        return self.node.__class__.__name__


def parse_source_for_query(
    source: str,
) -> tuple[
    str,
    cst.Module,
    Mapping[cst.CSTNode, cst.CSTNode],
    Mapping[cst.CSTNode, Any],
    PersistedNodeIds,
]:
    """Parse source after removing the trailing CST node-id marker block."""
    logical_source, persisted_node_ids = strip_persisted_node_ids(source)
    module = cst.parse_module(logical_source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)
    return logical_source, module, parents, positions, persisted_node_ids


def build_index(
    module: cst.Module,
    *,
    parents: dict[cst.CSTNode, cst.CSTNode],
    positions: dict[cst.CSTNode, Any],
    persisted_node_ids: PersistedNodeIds,
    node_ids_by_exact_key: dict[tuple[int, int, int, int, str], str] | None = None,
) -> list[NodeInfo]:
    """Build traversal-ordered node metadata for selector execution."""
    infos: list[NodeInfo] = []
    class_stack: list[str] = []
    func_stack: list[str] = []

    def visit(node: cst.CSTNode, depth: int, path_indices: tuple[int, ...]) -> None:
        parent = parents.get(node)
        pos = positions.get(node)
        if pos is None:
            return
        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
            node_type = node.__class__.__name__
            extra_attrs: Optional[dict[str, str]] = None
            if isinstance(node, cst.ImportFrom):
                try:
                    module_str = (
                        module.code_for_node(node.module) if node.module else ""
                    )
                    extra_attrs = {"module": module_str}
                except (AttributeError, TypeError):
                    extra_attrs = {"module": ""}
            infos.append(
                NodeInfo(
                    node=node,
                    parent=parent,
                    depth=depth,
                    kind=get_node_kind(node, class_stack),
                    name=get_node_name(node),
                    qualname=get_node_qualname(node, class_stack, func_stack),
                    start_line=start_line,
                    start_col=start_col,
                    end_line=end_line,
                    end_col=end_col,
                    node_id=persisted_node_ids.get(build_marker_path(path_indices))
                    or (node_ids_by_exact_key or {}).get(
                        build_exact_node_key(
                            start_line,
                            start_col,
                            end_line,
                            end_col,
                            node_type,
                        ),
                        "",
                    ),
                    extra_attrs=extra_attrs,
                )
            )
        except (AttributeError, TypeError):
            return

        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        for child_index, child in enumerate(node.children):
            visit(child, depth + 1, path_indices + (child_index,))

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(module, 0, (0,))
    return infos
