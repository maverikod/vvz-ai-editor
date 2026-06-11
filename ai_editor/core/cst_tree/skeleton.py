"""
Build declarative overview for a CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


from __future__ import annotations



import ast



from typing import Any, Dict, List, Optional



from .models import CSTTree, TreeNodeMetadata



BODY_PLACEHOLDER_COMMENT = (
    "# Implementation hidden; request node by node_id for full code"
)



VISIBLE_KINDS = {"module", "import", "class", "function", "method"}



def build_declarative_overview(tree: CSTTree) -> tuple[str, List[Dict[str, Any]]]:
    """Return declarative overview text and compact outline nodes."""
    root_node_id = tree.root_node_id or ""
    root_meta = tree.metadata_map.get(root_node_id)
    if root_meta is None:
        return ("", [])

    lines: List[str] = []
    outline_nodes: List[Dict[str, Any]] = []

    # Delegate to _append_node_overview which handles module header,
    # docstring, module-level attributes (Assign/AnnAssign), and children.
    _append_node_overview(
        tree=tree,
        node_id=root_node_id,
        depth=0,
        lines=lines,
        outline_nodes=outline_nodes,
    )
    return ("\n".join(lines) + ("\n" if lines else ""), outline_nodes)



def skeleton_from_tree(tree: CSTTree) -> str:
    """Backward-compatible alias for the new declarative overview."""
    overview, _outline_nodes = build_declarative_overview(tree)
    return overview


def build_node_declarative_overview(
    tree: CSTTree,
    node_id: str,
) -> tuple[str, List[Dict[str, Any]]]:
    """Return declarative overview text and outline nodes for a single node.

    Applies the same rules as :func:`build_declarative_overview` but scoped
    to one node.  Used for search results where each matched node should be
    presented as a compact skeleton instead of its full source.

    Args:
        tree: CST tree containing the node.
        node_id: UUID of the node to render.

    Returns:
        Tuple of (overview_text, outline_nodes) same shape as
        :func:`build_declarative_overview`.
    """
    lines: List[str] = []
    outline_nodes: List[Dict[str, Any]] = []
    _append_node_overview(
        tree=tree,
        node_id=node_id,
        depth=0,
        lines=lines,
        outline_nodes=outline_nodes,
    )
    return ("\n".join(lines) + ("\n" if lines else ""), outline_nodes)

def _append_node_overview(
    tree: CSTTree,
    node_id: str,
    depth: int,
    lines: List[str],
    outline_nodes: List[Dict[str, Any]],
) -> None:
    """Append visible node overview in file order: signature, docstring, children."""
    metadata = tree.metadata_map.get(node_id)
    node = tree.node_map.get(node_id)
    if metadata is None or node is None:
        return
    if metadata.kind not in VISIBLE_KINDS:
        return

    node_code = tree.module.code_for_node(node)

    if metadata.kind == "module":
        signature = f"module [{metadata.stable_id}] {tree.file_path}"
    else:
        signature = _build_signature(metadata, node_code)

    lines.append(f"{'    ' * depth}{signature}")
    outline_nodes.append(_outline_entry(metadata, depth=depth, signature=signature))

    docstring = _extract_docstring(node_code)
    if docstring:
        lines.extend(_indent_block(_format_docstring(docstring), depth=depth + 1))

    if metadata.kind in {"class", "module"}:
        child_ids_to_scan: List[str] = []
        for child_id in metadata.children_ids:
            child_meta = tree.metadata_map.get(child_id)
            if child_meta is None:
                continue
            if child_meta.type == "IndentedBlock":
                child_ids_to_scan.extend(child_meta.children_ids)
            else:
                child_ids_to_scan.append(child_id)

        child_ids_to_scan.sort(
            key=lambda cid: (
                tree.metadata_map[cid].start_line if cid in tree.metadata_map else 0
            ),
        )

        for child_id in child_ids_to_scan:
            child_meta = tree.metadata_map.get(child_id)
            child_node = tree.node_map.get(child_id)
            if child_meta is None or child_node is None:
                continue

            if child_meta.kind in VISIBLE_KINDS:
                _append_node_overview(
                    tree=tree,
                    node_id=child_id,
                    depth=depth + 1,
                    lines=lines,
                    outline_nodes=outline_nodes,
                )
            elif child_meta.type == "SimpleStatementLine":
                for inner_id in child_meta.children_ids:
                    inner_meta = tree.metadata_map.get(inner_id)
                    inner_node = tree.node_map.get(inner_id)
                    if inner_meta is None or inner_node is None:
                        continue
                    if inner_meta.kind in VISIBLE_KINDS:
                        _append_node_overview(
                            tree=tree,
                            node_id=inner_id,
                            depth=depth + 1,
                            lines=lines,
                            outline_nodes=outline_nodes,
                        )
                    elif inner_meta.type in {"Assign", "AnnAssign"}:
                        icode = tree.module.code_for_node(inner_node)
                        first_line = (
                            icode.strip().splitlines()[0] if icode.strip() else ""
                        )
                        if first_line.startswith(('"""', "'''")):
                            continue
                        attr_sig = f"[{inner_meta.stable_id}] {first_line}"
                        lines.append(f"{'    ' * (depth + 1)}{attr_sig}")
            else:
                _append_visible_descendants(
                    tree=tree,
                    node_id=child_id,
                    depth=depth + 1,
                    lines=lines,
                    outline_nodes=outline_nodes,
                )
    elif metadata.kind in {"function", "method"}:
        lines.append(f"{'    ' * (depth + 1)}{BODY_PLACEHOLDER_COMMENT}")



def _append_visible_descendants(
    tree: CSTTree,
    node_id: str,
    depth: int,
    lines: List[str],
    outline_nodes: List[Dict[str, Any]],
) -> None:
    """Recurse into non-visible nodes to find visible descendants.

    Args:
        tree: CST tree.
        node_id: Node ID to recurse into.
        depth: Indentation depth.
        lines: Output lines list (mutated in place).
        outline_nodes: Outline nodes list (mutated in place).
    """
    metadata = tree.metadata_map.get(node_id)
    if metadata is None:
        return
    if metadata.kind in VISIBLE_KINDS:
        _append_node_overview(
            tree=tree,
            node_id=node_id,
            depth=depth,
            lines=lines,
            outline_nodes=outline_nodes,
        )
        return
    for child_id in metadata.children_ids:
        _append_visible_descendants(
            tree=tree,
            node_id=child_id,
            depth=depth,
            lines=lines,
            outline_nodes=outline_nodes,
        )

def _build_signature(metadata: TreeNodeMetadata, code: str) -> str:
    """Build a short signature line for a node including its stable_id prefix.

    Args:
        metadata: Node metadata.
        code: Source code of the node.

    Returns:
        Signature string prefixed with [stable_id].
    """
    prefix = f"[{metadata.stable_id}] "
    if metadata.kind == "module":
        return f"module {prefix}{metadata.type}"
    if metadata.kind == "import":
        first_line = code.strip().splitlines()[0] if code.strip() else metadata.type
        return f"{prefix}{first_line}"

    header_lines: List[str] = []
    for line in code.splitlines():
        stripped = line.rstrip()
        # Skip inline stable_id comments
        if stripped.strip().startswith("# @node-id:"):
            continue
        if not stripped and not header_lines:
            continue
        header_lines.append(stripped)
        if stripped.strip().endswith(":"):
            break
    if not header_lines:
        header_lines = [metadata.type]
    header = " ".join(part.strip() for part in header_lines)
    return f"{prefix}{header}"



def _format_docstring(docstring: str) -> List[str]:
    return ['"""', *docstring.splitlines(), '"""']



def _indent_block(lines: List[str], depth: int) -> List[str]:
    prefix = "    " * depth
    return [f"{prefix}{line}" for line in lines]



def _outline_entry(
    metadata: TreeNodeMetadata,
    depth: int,
    signature: str,
) -> Dict[str, Any]:
    data = metadata.to_dict()
    data["depth"] = depth
    data["signature"] = signature
    return data



def _extract_docstring(code: str) -> Optional[str]:
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None
    return ast.get_docstring(parsed)
