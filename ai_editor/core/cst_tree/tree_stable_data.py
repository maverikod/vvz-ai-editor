"""
Stable identity in metadata: carry ``stable_id`` across CST rebuilds after mutation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import libcst as cst

from .node_id_markers import build_exact_node_key
from .node_stable_id import get_stable_id

if TYPE_CHECKING:
    from .models import CSTTree, TreeNodeMetadata

StatementStableKey = Tuple[str, str, str, str]

_STATEMENT_STABLE_TYPES = frozenset(
    {
        "SimpleStatementLine",
        "Expr",
        "AnnAssign",
        "Assign",
        "AugAssign",
    }
)


def normalized_source_span(module: cst.Module, start_line: int, end_line: int) -> str:
    """Collapse a 1-based inclusive line span to a single normalized text key."""
    lines = module.code.splitlines()
    if not lines or start_line < 1 or end_line < start_line:
        return ""
    lo = start_line - 1
    hi = min(len(lines), end_line)
    if lo >= hi:
        return ""
    return " ".join("\n".join(lines[lo:hi]).split())


def build_statement_stable_key(
    node_type: str,
    qualname: Optional[str],
    normalized_text: str,
) -> StatementStableKey:
    """Position-independent lookup key for statement-level stable_id."""
    return ("stmt", node_type, qualname or "", normalized_text)


def statement_stable_key_from_meta(
    meta: "TreeNodeMetadata",
    module: cst.Module,
) -> Optional[StatementStableKey]:
    """Statement stable key from pre-mutation metadata and module snapshot."""
    if meta.type not in _STATEMENT_STABLE_TYPES:
        return None
    norm = normalized_source_span(module, meta.start_line, meta.end_line)
    if not norm:
        return None
    return build_statement_stable_key(meta.type, meta.qualname, norm)


def _obj_to_stable_from_metadata(
    metadata_map: Dict[str, "TreeNodeMetadata"],
    source_module: Optional[cst.Module] = None,
) -> Dict[Any, str]:
    """Build semantic lookup keys for stable_id preservation across index rebuild."""
    out: Dict[Any, str] = {}
    for meta in metadata_map.values():
        if not meta.stable_id:
            continue
        if meta.qualname and meta.type in (
            "FunctionDef",
            "AsyncFunctionDef",
            "ClassDef",
        ):
            out.setdefault(("qualname", meta.qualname), meta.stable_id)
        if source_module is not None:
            stmt_key = statement_stable_key_from_meta(meta, source_module)
            if stmt_key is not None:
                out.setdefault(stmt_key, meta.stable_id)
    return out


def extract_stable_data(tree: "CSTTree") -> dict[str, list]:
    """Before mutation: snapshot decorators by ``metadata_map`` stable_id."""
    decorator_map: dict[str, list] = {}
    for _nid, meta in tree.metadata_map.items():
        node = tree.node_map.get(_nid)
        if node and isinstance(node, (cst.FunctionDef, cst.ClassDef)):
            if meta.stable_id and node.decorators:
                decorator_map[meta.stable_id] = list(node.decorators)
    return decorator_map


def _restore_decorators_from_metadata(
    tree: "CSTTree", decorator_map: dict[str, list]
) -> None:
    """Re-attach decorators using ``metadata_map.stable_id`` (not source markers)."""
    if not decorator_map:
        return
    nid_to_stable = {
        nid: meta.stable_id
        for nid, meta in tree.metadata_map.items()
        if meta.stable_id and meta.type in ("FunctionDef", "ClassDef")
    }
    if not nid_to_stable:
        return

    targets: dict[int, list] = {}
    for nid, stable in nid_to_stable.items():
        node = tree.node_map.get(nid)
        if node is not None and isinstance(node, (cst.FunctionDef, cst.ClassDef)):
            decs = decorator_map.get(stable)
            if decs and not node.decorators:
                targets[id(node)] = decs

    if not targets:
        return

    class _DecRestore(cst.CSTTransformer):
        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.CSTNode:
            decs = targets.get(id(original_node))
            if decs:
                return updated_node.with_changes(decorators=decs)
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.CSTNode:
            decs = targets.get(id(original_node))
            if decs:
                return updated_node.with_changes(decorators=decs)
            return updated_node

    tree.module = tree.module.visit(_DecRestore())
    for nid, node in list(tree.node_map.items()):
        decs = targets.get(id(node))
        if decs and isinstance(node, (cst.FunctionDef, cst.ClassDef)):
            tree.node_map[nid] = node.with_changes(decorators=decs)


def restore_stable_data(
    tree: "CSTTree",
    decorator_map: dict[str, list],
    *,
    previous_metadata_map: Optional[Dict[str, "TreeNodeMetadata"]] = None,
    previous_module: Optional[cst.Module] = None,
    pinned_node_id: Optional[str] = None,
) -> "CSTTree":
    """After mutation: rebuild index; ``stable_id`` stays in ``metadata_map`` / sidecar.

    Identity transfer uses semantic keys (qualname, statement text) from the
    pre-mutation metadata snapshot — not line/column coordinates.
    """
    prev = dict(previous_metadata_map) if previous_metadata_map else None
    mod_for_keys = previous_module if previous_module is not None else tree.module

    from .tree_builder import _build_tree_index

    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    tree.node_id_aliases.clear()
    _build_tree_index(
        tree,
        node_types=None,
        max_depth=None,
        include_children=True,
        previous_metadata_map=prev,
        obj_to_stable=(
            _obj_to_stable_from_metadata(prev, mod_for_keys) if prev else None
        ),
        pinned_node_id=pinned_node_id,
    )
    _restore_decorators_from_metadata(tree, decorator_map)

    return tree


def embed_stable_ids_into_tree(tree: "CSTTree") -> None:
    """Legacy: write metadata stable_id into def/class source markers (migration only).

    Edit sessions do not call this: ``stable_id`` is persisted in ``.cst/*.tree``.
    """
    nid_to_stable: dict[str, str] = {
        nid: meta.stable_id
        for nid, meta in tree.metadata_map.items()
        if meta.stable_id and meta.type in ("FunctionDef", "ClassDef")
    }
    if not nid_to_stable:
        return

    node_to_stable: dict[int, str] = {}
    for nid, stable in nid_to_stable.items():
        node_obj = tree.node_map.get(nid)
        if node_obj is not None:
            node_to_stable[id(node_obj)] = stable

    from .node_stable_id import set_stable_id

    class _EmbedTransformer(cst.CSTTransformer):
        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.CSTNode:
            stable = node_to_stable.get(id(original_node))
            if stable:
                return set_stable_id(updated_node, stable)
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.CSTNode:
            stable = node_to_stable.get(id(original_node))
            if stable:
                return set_stable_id(updated_node, stable)
            return updated_node

    tree.module = tree.module.visit(_EmbedTransformer())
