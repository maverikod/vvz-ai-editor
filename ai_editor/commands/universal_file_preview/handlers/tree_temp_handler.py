"""Preview handler for structured tree-temp configuration formats."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ai_editor.core.tree_temp.tree_node import TreeNode

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import INPUT_ERROR_UNKNOWN_NODE_REF, PreviewError, input_error
from ..invalid_preview import invalid_preview_line_params, invalid_source_node
from ..models import Node, NodeKind


class TreeTempFileHandler(FileHandler):
    """Adapt an existing tree-temp source parser to preview's Node interface."""

    def __init__(self, handler_id: str, extensions: frozenset[str]) -> None:
        self.handler_id = handler_id
        self._extensions = extensions
        self._roots: list[TreeNode] = []
        self._nodes_by_id: dict[str, TreeNode] = {}

    @property
    def supported_extensions(self) -> frozenset[str]:
        return self._extensions

    def _parse(self, raw: str) -> list[TreeNode]:
        if self.handler_id == "ini":
            from ai_editor.core.tree_temp.ini_source_parser import parse_ini_source

            return parse_ini_source(raw)
        if self.handler_id == "toml":
            from ai_editor.core.tree_temp.toml_source_parser import parse_toml_source

            return parse_toml_source(raw)
        raise ValueError(f"unsupported tree-temp preview handler: {self.handler_id!r}")

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        del session, budget
        try:
            self._roots = self._parse(
                Path(file_path).read_text(encoding="utf-8", errors="replace")
            )
            self._nodes_by_id = {}

            def index(node: TreeNode) -> None:
                self._nodes_by_id[node.stable_id] = node
                for child in node.children or []:
                    index(child)

            for root in self._roots:
                index(root)
            if len(self._roots) == 1:
                return self._to_node(self._roots[0])
            return Node(
                node_kind=NodeKind.MAPPING,
                node_ref="",
                _children_loader=lambda: [self._to_node(root) for root in self._roots],
            )
        except Exception as exc:
            return invalid_source_node(
                file_path, exc, **invalid_preview_line_params(budget)
            )

    def _to_node(self, tree_node: TreeNode) -> Node:
        kind = {
            "object": NodeKind.MAPPING,
            "array": NodeKind.SEQUENCE,
            "string": NodeKind.SCALAR,
            "number": NodeKind.SCALAR,
            "boolean": NodeKind.SCALAR,
            "null": NodeKind.SCALAR,
        }[tree_node.type]
        attrs: dict[str, Any] = {}
        if tree_node.type == "string":
            attrs["value"] = str(tree_node.value)
        elif tree_node.type in {"number", "boolean"}:
            attrs["value"] = str(tree_node.value).lower()
        elif tree_node.type == "null":
            attrs["value"] = "null"
        if kind is NodeKind.MAPPING and tree_node.children is None:
            attrs["value_kind"] = tree_node.type
        loader: Callable[[], list[Node]] | None = None
        if tree_node.children is not None:
            loader = lambda: [
                self._to_node(child) for child in tree_node.children or []
            ]
        return Node(
            node_kind=kind,
            node_ref=tree_node.stable_id,
            name=tree_node.key,
            type_label=tree_node.type,
            attributes=attrs,
            _children_loader=loader,
        )

    def resolve_node_ref(
        self, node_ref: str, session: Any | None
    ) -> Node | PreviewError:
        del session
        tree_node = self._nodes_by_id.get(node_ref)
        if tree_node is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Unknown tree-temp node_ref {node_ref!r}.",
                details={"node_ref": node_ref},
            )
        return self._to_node(tree_node)
