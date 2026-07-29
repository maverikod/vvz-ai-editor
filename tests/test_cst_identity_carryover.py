"""
Regression tests for bug 086a8f6c: node_id/stable_id identity carryover after a
structural edit shifts line numbers.

Before the fix, ``_build_tree_index`` reused a prior ``node_id`` from
``exact_key_to_id`` purely by (start_line, start_col, end_line, end_col, type)
coordinates, while ``stable_id`` was carried over by content (normalized
statement text / qualname). After deleting the first of several import
statements, the following statements shift up one line each and a *different*
statement's ``node_id`` (position-based) could collide with another
statement's ``stable_id`` (content-based), because the two carryover
mechanisms disagreed about which node the identifier described.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.cst_tree.models import TreeOperation, TreeOperationType
from ai_editor.core.cst_tree.tree_builder import create_tree_from_code, get_tree
from ai_editor.core.cst_tree.tree_modifier import modify_tree


def _assert_no_cross_node_id_stable_id_collision(tree) -> None:
    """No value may be node X's stable_id and, simultaneously, node Y's node_id
    for a *different* node Y.

    Such a collision means an identifier handed out as one node's durable
    handle (stable_id) is ambiguous with another node's ephemeral rebuild
    handle (node_id): a lookup by that value could silently resolve to the
    wrong node.
    """
    node_id_owner = {meta.node_id: nid for nid, meta in tree.metadata_map.items()}
    for nid, meta in tree.metadata_map.items():
        owner_of_value_as_node_id = node_id_owner.get(meta.stable_id)
        if owner_of_value_as_node_id is not None:
            assert owner_of_value_as_node_id == nid, (
                f"stable_id {meta.stable_id!r} of node {nid} ({meta.type} "
                f"{meta.qualname or meta.name}) is also the node_id of a "
                f"DIFFERENT node {owner_of_value_as_node_id} "
                f"({tree.metadata_map[owner_of_value_as_node_id].type})"
            )


def test_delete_first_import_does_not_swap_identity_across_statements(
    tmp_path: Path,
) -> None:
    """Deleting the first of three imports must not let a later import's
    content-based stable_id collide with an unrelated statement's
    position-carried-over node_id (bug 086a8f6c).

    Uses the real production rebuild entry point: ``modify_tree`` ->
    ``_apply_single_op`` -> ``restore_stable_data`` -> ``_build_tree_index``.
    """
    file_path = tmp_path / "sample.py"
    source = (
        "import zzz\n"
        "import aaa\n"
        "import bbb\n"
        "\n\n"
        "def foo():\n"
        "    return 1\n"
    )
    tree = create_tree_from_code(str(file_path), source)
    tree_id = tree.tree_id

    # Sanity: no collision at all before any mutation.
    _assert_no_cross_node_id_stable_id_collision(tree)

    zzz_id = None
    for nid, meta in tree.metadata_map.items():
        if meta.type == "SimpleStatementLine" and meta.start_line == 1:
            zzz_id = nid
            break
    assert zzz_id is not None, "could not locate 'import zzz' statement"

    modify_tree(
        tree_id,
        [TreeOperation(action=TreeOperationType.DELETE, node_id=zzz_id)],
    )

    tree = get_tree(tree_id)
    assert tree is not None
    assert "import zzz" not in tree.module.code
    assert "import aaa" in tree.module.code
    assert "import bbb" in tree.module.code

    _assert_no_cross_node_id_stable_id_collision(tree)


def test_delete_first_import_keeps_moved_statements_recognizable_by_stable_id(
    tmp_path: Path,
) -> None:
    """The surviving statements' stable_id must still resolve to a node whose
    source text matches what that stable_id originally named (content, not
    coordinates, is the durable identity)."""
    file_path = tmp_path / "sample.py"
    source = "import zzz\nimport aaa\nimport bbb\n"
    tree = create_tree_from_code(str(file_path), source)
    tree_id = tree.tree_id

    by_line = {
        meta.start_line: (nid, meta.stable_id)
        for nid, meta in tree.metadata_map.items()
        if meta.type == "SimpleStatementLine"
    }
    zzz_id, _zzz_stable = by_line[1]
    _aaa_id, aaa_stable = by_line[2]
    _bbb_id, bbb_stable = by_line[3]

    modify_tree(
        tree_id,
        [TreeOperation(action=TreeOperationType.DELETE, node_id=zzz_id)],
    )

    tree = get_tree(tree_id)
    assert tree is not None

    aaa_meta_after = tree.find_by_stable_id(aaa_stable)
    bbb_meta_after = tree.find_by_stable_id(bbb_stable)
    assert aaa_meta_after is not None
    assert bbb_meta_after is not None

    aaa_node_after = tree.node_map[aaa_meta_after.node_id]
    bbb_node_after = tree.node_map[bbb_meta_after.node_id]
    assert "aaa" in tree.module.code_for_node(aaa_node_after)
    assert "bbb" in tree.module.code_for_node(bbb_node_after)
