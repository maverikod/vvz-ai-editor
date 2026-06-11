"""
Tests for persisted CST UUID4 identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path

import libcst as cst

from ai_editor.core.cst_tree.models import TreeOperation, TreeOperationType
from ai_editor.core.cst_tree.node_id_markers import (
    MARKERS_BEGIN,
    MARKERS_END,
    append_persisted_node_ids,
    strip_persisted_node_ids,
)
from ai_editor.core.cst_tree.models import CSTTree
from ai_editor.core.cst_tree.node_stable_id import (
    set_stable_id,
    strip_inline_node_id_lines_from_source,
)
from ai_editor.core.cst_tree.tree_builder import (
    _build_tree_index,
    create_tree_from_code,
    load_file_to_tree,
)
from libcst.metadata import MetadataWrapper, PositionProvider
from ai_editor.core.cst_tree.tree_finder import find_nodes
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.cst_tree.tree_saver import save_tree_to_file
from ai_editor.tree.sibling_convention import sibling_tree_path


def test_marker_block_round_trip_keeps_clean_source() -> None:
    """Appending and stripping the marker block must preserve logical source."""
    source = '"""Doc."""\n\nx = 1\n'
    tree = create_tree_from_code("/tmp/example.py", source)

    persisted_source = append_persisted_node_ids(
        source,
        tree.metadata_map,
        tree.root_node_id,
    )
    clean_source, persisted_node_ids = strip_persisted_node_ids(persisted_source)

    assert MARKERS_BEGIN in persisted_source
    assert MARKERS_END in persisted_source
    assert clean_source == source
    assert len(persisted_node_ids) == len(tree.metadata_map)


def test_metadata_positions_after_text_strip_of_legacy_inline_marker(
    tmp_path: Path,
) -> None:
    """Legacy ``# @node-id:`` lines removed from source text before parse keep spans aligned."""
    sid = str(uuid.uuid4())
    module = cst.parse_module("class Foo:\n    pass\n")
    new_body: list[cst.CSTNode] = []
    for stmt in module.body:
        if isinstance(stmt, cst.ClassDef) and stmt.name.value == "Foo":
            stmt = set_stable_id(stmt, sid)
        new_body.append(stmt)
    dirty = module.with_changes(body=tuple(new_body)).code
    assert "# @node-id:" in dirty
    clean = strip_inline_node_id_lines_from_source(dirty)
    module = cst.parse_module(clean)

    tree = CSTTree.create(str(tmp_path / "virtual.py"), module)
    _build_tree_index(
        tree,
        node_types=["ClassDef"],
        max_depth=None,
        include_children=True,
    )
    class_ids = [
        nid
        for nid, m in tree.metadata_map.items()
        if m.type == "ClassDef" and m.name == "Foo"
    ]
    assert len(class_ids) == 1
    nid = class_ids[0]

    meta = tree.metadata_map[nid]
    node = tree.node_map[nid]
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    pos = wrapper.resolve(PositionProvider).get(node)
    assert pos is not None
    assert meta.start_line == pos.start.line
    assert meta.start_col == pos.start.column
    assert meta.end_line == pos.end.line
    assert meta.end_col == pos.end.column
    assert "# @node-id:" not in tree.module.code


def test_save_and_reload_preserve_node_ids(tmp_path: Path) -> None:
    """Saving with marker block and loading again must reproduce the same UUIDs."""
    file_path = tmp_path / "sample.py"
    tree = create_tree_from_code(
        str(file_path),
        '"""Doc."""\n\nimport os\n\n\ndef foo() -> int:\n    return 1\n',
    )
    result = save_tree_to_file(
        tree_id=tree.tree_id,
        file_path=str(file_path),
        root_dir=tmp_path,
        project_id=str(uuid.uuid4()),
        database=None,
        validate=True,
        backup=False,
    )

    assert result["success"] is True
    persisted_text = file_path.read_text(encoding="utf-8")
    assert MARKERS_BEGIN not in persisted_text
    assert MARKERS_END not in persisted_text
    assert sibling_tree_path(file_path.resolve()).is_file()

    reloaded = load_file_to_tree(str(file_path))
    assert reloaded.root_node_id == tree.root_node_id
    before_function = find_nodes(
        tree.tree_id,
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
    )[0]
    after_function = find_nodes(
        reloaded.tree_id,
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
    )[0]
    assert before_function.node_id == after_function.node_id


def test_modify_save_reload_preserves_replaced_function_id(tmp_path: Path) -> None:
    """A replaced function keeps its UUID after save and reload."""
    file_path = tmp_path / "sample.py"
    tree = create_tree_from_code(
        str(file_path),
        "def foo() -> int:\n    return 1\n",
    )
    function_meta = find_nodes(
        tree.tree_id,
        search_type="simple",
        node_type="FunctionDef",
    )[0]
    original_function_id = function_meta.node_id

    modify_tree(
        tree.tree_id,
        [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=original_function_id,
                code_lines=[
                    "def foo() -> int:",
                    '    """Updated."""',
                    "    return 2",
                ],
            )
        ],
    )

    save_result = save_tree_to_file(
        tree_id=tree.tree_id,
        file_path=str(file_path),
        root_dir=tmp_path,
        project_id=str(uuid.uuid4()),
        database=None,
        validate=True,
        backup=False,
    )
    assert save_result["success"] is True

    reloaded = load_file_to_tree(str(file_path))
    reloaded_function = find_nodes(
        reloaded.tree_id,
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
    )[0]
    assert "return 2" in file_path.read_text(encoding="utf-8")
    assert reloaded_function is not None
