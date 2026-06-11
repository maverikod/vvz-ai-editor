"""Tests for stable_id vs span node_id resolution in tree_metadata."""

from __future__ import annotations

from ai_editor.core.cst_tree.models import CSTTree, TreeNodeMetadata
from ai_editor.core.cst_tree.tree_builder import create_tree_from_code
from ai_editor.core.cst_tree.tree_metadata import _resolve_node_id


def test_resolve_node_id_maps_stable_id_when_aliases_present() -> None:
    """stable_id must resolve even when node_id_aliases dict is non-empty."""
    tree = create_tree_from_code(
        "/tmp/stable_resolve.py",
        "import os\n\ndef foo() -> None:\n    pass\n",
    )
    import_meta = next(
        m
        for m in tree.metadata_map.values()
        if m.type == "SimpleStatementLine"
        and "import os" in tree.module.code.splitlines()[m.start_line - 1]
    )
    stable = import_meta.stable_id
    span = import_meta.node_id
    tree.node_id_aliases = {span: span}  # non-empty aliases block (old bug)

    assert _resolve_node_id(tree, stable) == span
    assert _resolve_node_id(tree, span) == span


def test_resolve_node_id_follows_alias_chain_then_stable_id() -> None:
    """Retired span ids alias forward; unknown uuid falls back to stable_id lookup."""
    tree = create_tree_from_code("/tmp/alias_chain.py", "x = 1\n")
    meta = next(
        m for m in tree.metadata_map.values() if m.type == "SimpleStatementLine"
    )
    old_span = meta.node_id
    new_span = "00000000-0000-4000-8000-000000000099"
    stable = meta.stable_id
    tree.metadata_map[new_span] = TreeNodeMetadata(
        node_id=new_span,
        stable_id=stable,
        type=meta.type,
        kind=meta.kind,
        name=meta.name,
        qualname=meta.qualname,
        start_line=meta.start_line,
        start_col=meta.start_col,
        end_line=meta.end_line,
        end_col=meta.end_col,
        children_count=meta.children_count,
        children_ids=list(meta.children_ids),
        parent_id=meta.parent_id,
    )
    tree.node_id_aliases = {old_span: new_span}

    assert _resolve_node_id(tree, old_span) == new_span
    assert _resolve_node_id(tree, stable) == new_span
