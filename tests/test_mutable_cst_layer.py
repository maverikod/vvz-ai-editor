"""
Unit and integration tests for the mutable CST layer (batch replace/insert/delete).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

import libcst as cst

from ai_editor.core.cst_tree.models import (
    ROOT_NODE_ID_SENTINEL,
    TreeOperation,
    TreeOperationType,
)
from ai_editor.core.cst_tree.tree_builder import (
    create_tree_from_code,
    get_tree,
    remove_tree,
)
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.mutable_cst import (
    apply_operations,
    build_from_libcst,
    serialize_to_source,
)
from ai_editor.core.mutable_cst.models import MutableTree


CLASS_WITH_METHODS = """
class Foo:
    def a(self):
        return 1

    def b(self):
        return 2

    def c(self):
        return 3
"""


def _collect_function_def_node_ids(tree_id: str) -> list[str]:
    """Return node_ids of FunctionDef nodes in module (e.g. methods) in source order."""
    t = get_tree(tree_id)
    assert t is not None
    root_id = t.root_node_id
    if not root_id:
        return []
    by_line: list[tuple[int, str]] = []
    for nid, meta in t.metadata_map.items():
        if meta.type == "FunctionDef" and meta.parent_id != root_id:
            by_line.append((meta.start_line, nid))
    by_line.sort(key=lambda x: x[0])
    return [nid for (_, nid) in by_line]


@pytest.fixture
def tree_class_with_methods(tmp_path):
    """Tree with one class and three methods (for batch replace)."""
    path = str(tmp_path / "cls.py")
    tree = create_tree_from_code(path, CLASS_WITH_METHODS.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


class TestBuildAndSerialize:
    """Unit tests: build_from_libcst and serialize_to_source."""

    def test_build_from_libcst_returns_tree_with_node_map(
        self, tree_class_with_methods
    ):
        """build_from_libcst produces MutableTree; metadata_map keys appear in node_map when node_map is passed."""
        t = get_tree(tree_class_with_methods)
        assert t is not None
        mutable = build_from_libcst(t.module, t.metadata_map, t.node_map)
        assert isinstance(mutable, MutableTree)
        assert mutable.root is not None
        for nid in t.metadata_map:
            assert mutable.get_node(nid) is not None

    def test_serialize_to_source_roundtrip(self, tree_class_with_methods):
        """serialize_to_source(build(module)) parses and compiles."""
        t = get_tree(tree_class_with_methods)
        assert t is not None
        mutable = build_from_libcst(t.module, t.metadata_map, t.node_map)
        source = serialize_to_source(mutable)
        parsed = cst.parse_module(source)
        compile(parsed.code, "<string>", "exec")


class TestBatchReplaceIntegration:
    """Integration: modify_tree with multiple replace ops (LibCST sequential path)."""

    def test_batch_replace_two_methods_succeeds(self, tree_class_with_methods):
        """Two replace ops in one call (e.g. add docstrings to two methods) succeed."""
        node_ids = _collect_function_def_node_ids(tree_class_with_methods)
        assert len(node_ids) >= 2
        id_a, id_b = node_ids[0], node_ids[1]
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=id_a,
                code_lines=["def a(self):", '    """Doc for a."""', "    return 1"],
            ),
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=id_b,
                code_lines=["def b(self):", '    """Doc for b."""', "    return 2"],
            ),
        ]
        modified = modify_tree(tree_class_with_methods, ops)
        code = modified.module.code
        assert '"""Doc for a."""' in code
        assert '"""Doc for b."""' in code
        compile(code, "<string>", "exec")

    def test_batch_replace_three_methods_succeeds(self, tree_class_with_methods):
        """Three replace ops in one call; result compiles and all edits present."""
        node_ids = _collect_function_def_node_ids(tree_class_with_methods)
        assert len(node_ids) >= 3
        names = ("a", "b", "c")
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_ids[i],
                code_lines=[
                    f"def {names[i]}(self):",
                    f'    """Doc {names[i]}."""',
                    f"    return {i + 1}",
                ],
            )
            for i in range(3)
        ]
        modified = modify_tree(tree_class_with_methods, ops)
        code = modified.module.code
        for name in ("a", "b", "c"):
            assert f'"""Doc {name}."""' in code
        compile(code, "<string>", "exec")


class TestBatchInsertIntegration:
    """Integration: modify_tree with multiple insert ops."""

    def test_batch_insert_two_statements_succeeds(self, tmp_path):
        """Two insert ops at module level in one call."""
        source = "x = 1\n"
        path = str(tmp_path / "m.py")
        tree = create_tree_from_code(path, source)
        tree_id = tree.tree_id
        try:
            root_id = tree.root_node_id
            assert root_id is not None
            ops = [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="last",
                    code_lines=["y = 2"],
                ),
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="last",
                    code_lines=["z = 3"],
                ),
            ]
            modified = modify_tree(tree_id, ops)
            code = modified.module.code
            assert "x = 1" in code
            assert "y = 2" in code
            assert "z = 3" in code
            compile(code, "<string>", "exec")
        finally:
            remove_tree(tree_id)


class TestMutableEditsUnit:
    """Unit tests: apply_operations replace/insert/delete on MutableTree."""

    def test_apply_replace_updates_source(self, tree_class_with_methods):
        """After apply_operations with one replace, serialize reflects new source."""
        t = get_tree(tree_class_with_methods)
        assert t is not None
        mutable = build_from_libcst(t.module, t.metadata_map, t.node_map)
        node_ids = [
            nid
            for nid, m in t.metadata_map.items()
            if m.type == "FunctionDef" and m.parent_id != t.root_node_id
        ]
        assert node_ids
        op = TreeOperation(
            action=TreeOperationType.REPLACE,
            node_id=node_ids[0],
            code_lines=["def a(self):", "    return 42"],
        )
        apply_operations(mutable, [op], t.metadata_map)
        source = serialize_to_source(mutable)
        assert "return 42" in source
        assert "return 1" not in source
