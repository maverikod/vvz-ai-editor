"""Decorator indexing, preview, and replace preservation for CST / universal file edit."""

from __future__ import annotations

from ai_editor.commands.cst_modify_tree_ops_build import build_tree_operations
from ai_editor.core.cst_tree.models import TreeOperation, TreeOperationType
from ai_editor.core.cst_tree.tree_builder import create_tree_from_code, remove_tree
from ai_editor.core.cst_tree.tree_modifier import modify_tree


def test_preview_lists_decorators_under_function(tmp_path) -> None:
    from ai_editor.tree.handlers.python_handler import PythonHandler

    src = (
        "class C:\n"
        "    @classmethod\n"
        "    def foo(cls) -> int:\n"
        "        return 1\n"
    )
    path = tmp_path / "c.py"
    path.write_text(src, encoding="utf-8")
    nodes = PythonHandler().parse_content(path, src)
    foo_sid = next(
        int(n.short_id)
        for n in nodes
        if n.kind == "function" and "def foo" in n.content
    )
    dec_nodes = [
        n
        for n in nodes
        if n.parent_short_id == foo_sid and n.kind.lower() == "decorator"
    ]
    assert len(dec_nodes) == 1
    assert "@classmethod" in dec_nodes[0].content


def test_replace_functiondef_preserves_decorators_without_at_in_code() -> None:
    src = (
        "class C:\n"
        "    @classmethod\n"
        "    def foo(cls) -> int:\n"
        "        return 1\n"
    )
    tree = create_tree_from_code("/tmp/_decor_replace.py", src)
    try:
        fn_id = next(
            nid
            for nid, m in tree.metadata_map.items()
            if m.type == "FunctionDef" and m.name == "foo"
        )
        modify_tree(
            tree.tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.REPLACE,
                    node_id=fn_id,
                    code_lines=[
                        "def foo(cls) -> int:",
                        "    return 2",
                    ],
                    replace_all_child_nodes=True,
                )
            ],
        )
        code = tree.module.code
        assert "@classmethod" in code
        assert "return 2" in code
        assert "return 1" not in code
    finally:
        remove_tree(tree.tree_id)


def test_replace_functiondef_preserves_decorator_stable_id_after_rebuild() -> None:
    """Marker round-trip: decorator stable_id after full FunctionDef replace (no @ in code)."""
    src = (
        "class Dog:\n"
        "    @classmethod\n"
        "    def from_dict(cls, data: dict) -> 'Dog':\n"
        "        return cls(data['name'])\n"
    )
    tree = create_tree_from_code("/tmp/_decor_id.py", src)
    try:
        dec_stable_before = None
        fn_id = None
        for nid, m in tree.metadata_map.items():
            if m.type == "Decorator":
                dec_stable_before = m.stable_id
            if m.type == "FunctionDef" and m.name == "from_dict":
                fn_id = nid
        assert dec_stable_before is not None and fn_id is not None

        modify_tree(
            tree.tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.REPLACE,
                    node_id=fn_id,
                    code_lines=[
                        "def from_dict(cls, data: dict) -> 'Dog':",
                        "    return cls(**data)",
                    ],
                )
            ],
        )
        dec_stable_after = None
        for m in tree.metadata_map.values():
            if m.type == "Decorator":
                dec_stable_after = m.stable_id
                break
        assert dec_stable_after == dec_stable_before
    finally:
        remove_tree(tree.tree_id)


def test_replace_functiondef_preserves_decorator_stable_id() -> None:
    src = (
        "class Dog:\n"
        "    @classmethod\n"
        "    def from_dict(cls, data: dict) -> 'Dog':\n"
        "        return cls(data['name'])\n"
    )
    tree = create_tree_from_code("/tmp/_decor_stable.py", src)
    try:
        dec_stable_before = None
        fn_id = None
        fn_stable_before = None
        for nid, m in tree.metadata_map.items():
            if m.type == "Decorator":
                dec_stable_before = m.stable_id
            if m.type == "FunctionDef" and m.name == "from_dict":
                fn_id = nid
                fn_stable_before = m.stable_id
        assert dec_stable_before and fn_id and fn_stable_before

        modify_tree(
            tree.tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.REPLACE,
                    node_id=fn_id,
                    code_lines=[
                        "def from_dict(cls, data: dict) -> 'Dog':",
                        '    """Create from dict."""',
                        "    return cls(**data)",
                    ],
                )
            ],
        )
        dec_stable_after = None
        fn_stable_after = None
        for m in tree.metadata_map.values():
            if m.type == "Decorator":
                dec_stable_after = m.stable_id
            if m.type == "FunctionDef" and m.name == "from_dict":
                fn_stable_after = m.stable_id
        assert dec_stable_after == dec_stable_before
        assert fn_stable_after == fn_stable_before
        assert "@classmethod" in tree.module.code
    finally:
        remove_tree(tree.tree_id)


def test_build_tree_operations_replace_defaults_replace_all_child_nodes_false() -> None:
    src = "def x():\n    pass\n"
    tree = create_tree_from_code("/tmp/_decor_ops_build.py", src)
    try:
        fn_id = next(
            nid for nid, m in tree.metadata_map.items() if m.type == "FunctionDef"
        )
        built, err = build_tree_operations(
            tree,
            [{"action": "replace", "node_id": fn_id, "code": "def x() -> None:"}],
        )
        assert err is None
        assert built is not None
        assert len(built) == 1
        assert built[0].action == TreeOperationType.REPLACE
        assert built[0].replace_all_child_nodes is False
    finally:
        remove_tree(tree.tree_id)
