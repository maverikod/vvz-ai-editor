"""
Tree loader for PreviewNavigation via TreeLifecycle (G-004 {f001}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from ai_editor.core.tree_lifecycle.lifecycle import TreeLifecycle
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.contracts import NodeId, validate_short_id
from ai_editor.tree.format_handler import FormatHandler
from ai_editor.tree.handler_registry import HandlerNotFoundError, HandlerRegistry
from ai_editor.tree.tree_node import TreeNode


@dataclass
class NodeListTree:
    """Minimal tree wrapper exposing ``all_nodes()`` for PreviewNavigation."""

    nodes: List[TreeNode]

    def all_nodes(self) -> List[TreeNode]:
        return self.nodes


def resolve_format_handler(source_path: Path) -> FormatHandler:
    """Return unified FormatHandler for *source_path*, including .pyi/.pyw."""
    ext = source_path.suffix.lower()
    registry = HandlerRegistry.default_registry()
    if ext in registry:
        return registry.resolve(source_path)
    if ext in (".pyi", ".pyw"):
        return registry.resolve(source_path.with_suffix(".py"))
    raise HandlerNotFoundError(ext)


def _read_source_text(*, preview_abs_path: Path) -> str:
    """Read UTF-8 source; fall back from empty ``*.draft`` to the original file."""
    if not preview_abs_path.is_file():
        return ""
    try:
        source = preview_abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        source = ""
    path_str = str(preview_abs_path)
    if source or not path_str.endswith(".draft"):
        return source
    original_path = Path(path_str[: -len(".draft")])
    if not original_path.is_file():
        return source
    try:
        return original_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return source


def _load_python_nodes_from_valid_session(
    core: object,
    edit_sess: object,
) -> List[TreeNode] | None:
    """Load preview nodes for a valid Python edit session MAP sidecar."""
    from ai_editor.commands.universal_file_edit.session import EditSession
    from ai_editor.tree.handlers.python_handler import PythonHandler

    assert isinstance(edit_sess, EditSession)
    handler = resolve_format_handler(core.session_source_path)
    if not isinstance(handler, PythonHandler):
        return None
    sections = parse_tree_file(core.session_tree_path.read_text(encoding="utf-8"))
    unmarked = handler.unmark(sections.tree)
    map_uuids = {entry.short_id: entry.uuid for entry in sections.map.entries}
    nodes = handler.preview_nodes_from_marked(
        sections.tree,
        unmarked,
        map_uuids=map_uuids,
    )
    return nodes if nodes else None


def _load_nodes_from_valid_edit_session(session_id: str) -> List[TreeNode] | None:
    """Load MAP/TREE short_ids from an open valid universal_file_edit session."""
    from ai_editor.commands.universal_file_edit.session import get_session
    from ai_editor.core.edit_session.edit_operations_adapter import (
        _parse_marked_tree_root,
    )
    from ai_editor.core.edit_session.edit_session import SessionTreeValidity
    from ai_editor.tree.handlers.json_handler import _collect_nodes

    try:
        edit_sess = get_session(session_id)
    except ValueError:
        return None
    core = edit_sess.core
    if (
        core.tree_validity != SessionTreeValidity.VALID
        or not core.session_tree_path.is_file()
    ):
        return None
    if edit_sess.handler_id == "python":
        try:
            return _load_python_nodes_from_valid_session(core, edit_sess)
        except Exception:
            return None
    try:
        sections = parse_tree_file(core.session_tree_path.read_text(encoding="utf-8"))
        marked_root = _parse_marked_tree_root(sections, edit_sess.handler_id)
    except Exception:
        return None
    nodes: List[TreeNode] = []
    _collect_nodes(marked_root, "", nodes)
    return nodes if nodes else None


def make_preview_tree_loader(
    *,
    project_root: Path,
    rel_file_path: str,
    preview_abs_path: Path,
    bound_session_id: Optional[str],
) -> Callable[[Path, Optional[str]], NodeListTree]:
    """Build PreviewNavigation ``tree_loader`` callback."""

    def loader(source_path: Path, session_id: Optional[str]) -> NodeListTree:
        effective_session = session_id if session_id is not None else bound_session_id
        if effective_session is not None:
            session_nodes = _load_nodes_from_valid_edit_session(str(effective_session))
            if session_nodes is not None:
                return NodeListTree(session_nodes)
        content = _read_source_text(preview_abs_path=preview_abs_path)
        parse_path = preview_abs_path
        if effective_session is None:
            TreeLifecycle.from_path(
                project_root=project_root,
                file_path=rel_file_path,
            )
        handler = resolve_format_handler(parse_path)
        try:
            nodes = handler.parse_content(parse_path, content)
        except Exception:
            raise
        return NodeListTree(nodes)

    return loader


def parse_focus_short_id(
    node_ref: str | int | None,
    nodes: List[TreeNode],
) -> NodeId:
    """Resolve API ``node_ref`` to focus ``NodeId``; root when omitted."""
    if node_ref is None:
        roots = [n for n in nodes if n.parent_short_id is None]
        if not roots:
            raise ValueError("tree has no root node")
        root = min(roots, key=lambda n: int(n.short_id))
        return NodeId(root.short_id)
    if isinstance(node_ref, int):
        return validate_short_id(node_ref)
    raw = str(node_ref).strip()
    if not raw.isdigit():
        raise ValueError(f"node_ref must be integer short_id, got {node_ref!r}")
    return validate_short_id(int(raw))
