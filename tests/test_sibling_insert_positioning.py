"""
FEAT-INSERT-SIBLING-POSITION: acceptance tests for sibling-relative insert.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from collections.abc import Generator
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.cst_modify_tree_ops_build import build_tree_operations
from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.sidecar_cst_apply import (
    _normalized_cst_modify_operation,
    _resolve_stable_to_span,
)
from ai_editor.commands.universal_file_edit.tree_temp_legacy_apply import (
    _modify_yaml_registered_one,
)
from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from ai_editor.core.cst_tree.tree_builder import (
    create_tree_from_code,
    get_tree,
    load_file_to_tree,
    remove_tree,
)
from ai_editor.core.cst_tree.tree_modifier import _find_parent_for_node, modify_tree
from ai_editor.core.json_tree.json_query import (
    normalize_key_path,
    resolve_node_id_from_pointer,
)
from ai_editor.core.json_tree.tree_builder import build_tree_from_data
from ai_editor.core.json_tree.tree_modifier import modify_tree as json_modify_tree
from ai_editor.core.yaml_tree.tree_builder import (
    load_file_to_tree as load_yaml_to_tree,
)
from tests.thin_editor_ca_mocks import (
    make_workspace,
    mock_upstream,
    reset_ca_session,
    upstream_context,
)

_CA_SESSION_ID = "test-ca-1"


@pytest.fixture(autouse=True)
def _reset_ca_session() -> Generator[None, None, None]:
    reset_ca_session(_CA_SESSION_ID)
    yield
    reset_ca_session(_CA_SESSION_ID)


THREE_FUNCS = """
def alpha() -> None:
    pass


def beta() -> None:
    pass


def gamma() -> None:
    pass
""".strip()


CONTAINER_CLASS = '''
class Container:
    """Holds values."""

    def __init__(self) -> None:
        pass

    def get(self) -> int:
        return 1

    def double(self, n: int) -> int:
        return n * 2
'''.strip()


NESTED_FUNCTIONS = """
def outer():
    def inner_a():
        pass

    def inner_b():
        pass
""".strip()


def _top_level_function_names(source: str) -> list[str]:
    mod = ast.parse(source)
    return [n.name for n in mod.body if isinstance(n, ast.FunctionDef)]


def _class_method_names(source: str, class_name: str) -> list[str]:
    mod = ast.parse(source)
    for node in mod.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
    raise AssertionError(f"class {class_name!r} not found")


def _blank_lines_before_def(source: str, def_name: str) -> int:
    lines = source.splitlines()
    def_idx = next(
        i for i, ln in enumerate(lines) if ln.lstrip().startswith(f"def {def_name}")
    )
    n = 0
    for i in range(def_idx - 1, -1, -1):
        if lines[i].strip() == "":
            n += 1
        else:
            break
    return n


def _function_node_id(
    tree_id: str,
    name: str,
    *,
    in_class: str | None = None,
    in_function: str | None = None,
) -> str:
    tree = get_tree(tree_id)
    assert tree is not None
    root_id = tree.root_node_id
    for meta in tree.metadata_map.values():
        if meta.type != "FunctionDef" or meta.name != name:
            continue
        if in_class is None and in_function is None:
            if meta.parent_id == root_id:
                return meta.node_id
        elif in_function is not None:
            fn_meta = next(
                m
                for m in tree.metadata_map.values()
                if m.type == "FunctionDef" and m.name == in_function
            )
            cur = meta.parent_id
            while cur is not None:
                if cur == fn_meta.node_id:
                    return meta.node_id
                pm = tree.metadata_map.get(cur)
                if pm is None:
                    break
                cur = pm.parent_id
        elif in_class is not None:
            class_meta = next(
                m
                for m in tree.metadata_map.values()
                if m.type == "ClassDef" and m.name == in_class
            )
            cur = meta.parent_id
            while cur is not None:
                if cur == class_meta.node_id:
                    return meta.node_id
                pm = tree.metadata_map.get(cur)
                if pm is None:
                    break
                cur = pm.parent_id
    raise AssertionError(f"FunctionDef {name!r} not found")


def _function_stable_id(tree_id: str, name: str, *, in_class: str | None = None) -> str:
    tree = get_tree(tree_id)
    assert tree is not None
    root_id = tree.root_node_id
    for meta in tree.metadata_map.values():
        if meta.type != "FunctionDef" or meta.name != name:
            continue
        if in_class is None:
            if meta.parent_id == root_id:
                return meta.stable_id
        else:
            class_meta = next(
                m
                for m in tree.metadata_map.values()
                if m.type == "ClassDef" and m.name == in_class
            )
            cur: str | None = meta.node_id
            while cur is not None:
                if cur == class_meta.node_id:
                    return meta.stable_id
                pm = tree.metadata_map.get(cur)
                if pm is None:
                    break
                if pm.type == "ClassDef":
                    break
                cur = pm.parent_id
    raise AssertionError(f"FunctionDef {name!r} not found")


@pytest.fixture
def three_func_tree_id(tmp_path: Path) -> str:
    path = str(tmp_path / "mod.py")
    tree = create_tree_from_code(path, THREE_FUNCS)
    yield tree.tree_id
    remove_tree(tree.tree_id)


@pytest.fixture
def container_tree_id(tmp_path: Path) -> str:
    path = str(tmp_path / "container.py")
    tree = create_tree_from_code(path, CONTAINER_CLASS)
    yield tree.tree_id
    remove_tree(tree.tree_id)


@pytest.fixture
def nested_func_tree_id(tmp_path: Path) -> str:
    path = str(tmp_path / "nested.py")
    tree = create_tree_from_code(path, NESTED_FUNCTIONS)
    yield tree.tree_id
    remove_tree(tree.tree_id)


class TestSidecarSiblingInsert:
    """AT-SC-01 .. AT-SC-05 (FORMAT_SIDECAR)."""

    def test_insert_after_alpha(self, three_func_tree_id: str) -> None:
        alpha_sid = _function_stable_id(three_func_tree_id, "alpha")
        built, err = build_tree_operations(
            get_tree(three_func_tree_id),
            [
                {
                    "action": "insert",
                    "target_node_id": alpha_sid,
                    "position": "after",
                    "code_lines": ["", "", "def inserted() -> None:", "    pass"],
                }
            ],
        )
        assert err is None and built
        modified = modify_tree(three_func_tree_id, built)
        code = modified.module.code
        assert _top_level_function_names(code) == ["alpha", "inserted", "beta", "gamma"]
        assert _blank_lines_before_def(code, "inserted") == 2

    def test_insert_before_beta(self, three_func_tree_id: str) -> None:
        beta_sid = _function_stable_id(three_func_tree_id, "beta")
        built, _ = build_tree_operations(
            get_tree(three_func_tree_id),
            [
                {
                    "action": "insert",
                    "target_node_id": beta_sid,
                    "position": "before",
                    "code_lines": ["", "", "def pre_beta() -> None:", "    pass"],
                }
            ],
        )
        modified = modify_tree(three_func_tree_id, built)
        code = modified.module.code
        assert _top_level_function_names(code) == ["alpha", "pre_beta", "beta", "gamma"]
        assert _blank_lines_before_def(code, "pre_beta") == 2

    def test_find_parent_for_method_returns_class_not_indented_block(
        self, container_tree_id: str
    ) -> None:
        """AT-SC-03: parent resolution must skip IndentedBlock."""
        tree = get_tree(container_tree_id)
        assert tree is not None
        get_nid = _function_node_id(container_tree_id, "get", in_class="Container")
        parent_id = _find_parent_for_node(tree, get_nid)
        assert parent_id is not None
        parent_meta = tree.metadata_map[parent_id]
        assert parent_meta.type == "ClassDef"
        assert parent_meta.name == "Container"

    def test_insert_after_method_in_class(self, container_tree_id: str) -> None:
        get_nid = _function_node_id(container_tree_id, "get", in_class="Container")
        built, _ = build_tree_operations(
            get_tree(container_tree_id),
            [
                {
                    "action": "insert",
                    "target_node_id": get_nid,
                    "position": "after",
                    "code_lines": [
                        "",
                        "def extra(self) -> None:",
                        '    """AT-SC-03."""',
                        "    pass",
                    ],
                }
            ],
        )
        modified = modify_tree(container_tree_id, built)
        code = modified.module.code
        assert _class_method_names(code, "Container") == [
            "__init__",
            "get",
            "extra",
            "double",
        ]
        assert _blank_lines_before_def(code, "extra") == 1

    def test_insert_before_method_in_class(self, container_tree_id: str) -> None:
        double_nid = _function_node_id(
            container_tree_id, "double", in_class="Container"
        )
        built, _ = build_tree_operations(
            get_tree(container_tree_id),
            [
                {
                    "action": "insert",
                    "target_node_id": double_nid,
                    "position": "before",
                    "code_lines": ["", "def before_double(self) -> None:", "    pass"],
                }
            ],
        )
        modified = modify_tree(container_tree_id, built)
        code = modified.module.code
        assert _class_method_names(code, "Container") == [
            "__init__",
            "get",
            "before_double",
            "double",
        ]
        assert _blank_lines_before_def(code, "before_double") == 1

    def test_insert_after_nested_inner_function(self, nested_func_tree_id: str) -> None:
        tree = get_tree(nested_func_tree_id)
        assert tree is not None
        inner_a_nid = _function_node_id(
            nested_func_tree_id, "inner_a", in_function="outer"
        )
        built, _ = build_tree_operations(
            tree,
            [
                {
                    "action": "insert",
                    "target_node_id": inner_a_nid,
                    "position": "after",
                    "code_lines": ["def inner_between(): pass"],
                }
            ],
        )
        modified = modify_tree(nested_func_tree_id, built)
        code = modified.module.code
        outer_body = ast.parse(code).body[0]
        assert isinstance(outer_body, ast.FunctionDef)
        inner_names = [
            n.name for n in outer_body.body if isinstance(n, ast.FunctionDef)
        ]
        assert inner_names == ["inner_a", "inner_between", "inner_b"]

    def test_position_after_index_shorthand(self, three_func_tree_id: str) -> None:
        built, _ = build_tree_operations(
            get_tree(three_func_tree_id),
            [
                {
                    "action": "insert",
                    "parent_node_id": "__root__",
                    "position": {"after": 1},
                    "code_lines": ["", "", "def mid() -> None:", "    pass"],
                }
            ],
        )
        modified = modify_tree(three_func_tree_id, built)
        code = modified.module.code
        assert _top_level_function_names(code) == ["alpha", "beta", "mid", "gamma"]

    @pytest.mark.asyncio
    async def test_stale_target_node_id(self, tmp_path: Path) -> None:
        path = tmp_path / "stale.py"
        path.write_text(THREE_FUNCS, encoding="utf-8")
        tree = load_file_to_tree(str(path))
        beta_sid = _function_stable_id(tree.tree_id, "beta")
        descriptor = resolve_format_group(path)
        session = create_session(
            path,
            descriptor,
            file_path=path.name,
            tree_id=tree.tree_id,
            ca_session_id=_CA_SESSION_ID,
        )
        try:
            cmd = UniversalFileEditCommand()
            workspace = make_workspace(tmp_path)
            upstream = mock_upstream()
            with upstream_context(workspace=workspace, upstream=upstream):
                delete_res = await cmd.execute(
                    project_id="test-project",
                    session_id=session.session_id,
                    operations=[{"type": "delete", "node_id": beta_sid}],
                )
                assert isinstance(delete_res, SuccessResult)
                after_tree = get_tree(session.tree_id or tree.tree_id)
                assert after_tree is not None
                assert after_tree.find_by_stable_id(beta_sid) is None
                # Recycled node_id must not alias deleted stable_id (sidecar lookup).
                after_tree.metadata_map.pop(beta_sid, None)
                insert_res = await cmd.execute(
                    project_id="test-project",
                    session_id=session.session_id,
                    operations=[
                        {
                            "type": "insert",
                            "target_node_id": beta_sid,
                            "position": "after",
                            "code_lines": ["def x() -> None:", "    pass"],
                        }
                    ],
                )
            assert isinstance(insert_res, ErrorResult)
            assert insert_res.code == "STALE_NODE_ID"
        finally:
            release_session(session.session_id)
            remove_tree(tree.tree_id)


class TestJsonArraySiblingInsert:
    """AT-JA-01 .. AT-JA-03."""

    @pytest.fixture(autouse=True)
    def _clear_json_sessions(self):
        import ai_editor.core.json_tree.tree_builder as tb

        tb._trees.clear()
        yield
        tb._trees.clear()

    def _items_tree(self, tmp_path: Path):
        data = {"items": ["a", "b", "c"]}
        tree = build_tree_from_data(str(tmp_path / "doc.json"), data, register=True)
        items_ptr = normalize_key_path("items")
        items_id = resolve_node_id_from_pointer(tree, items_ptr)
        assert items_id is not None
        b_id = resolve_node_id_from_pointer(tree, normalize_key_path("items.1"))
        assert b_id is not None
        return tree, items_id, b_id

    def test_insert_before_element_by_node_id(self, tmp_path: Path) -> None:
        tree, items_id, b_id = self._items_tree(tmp_path)
        json_modify_tree(
            tree.tree_id,
            [
                {
                    "action": "insert",
                    "parent_node_id": items_id,
                    "value": "x",
                    "before_node_id": b_id,
                }
            ],
        )
        from ai_editor.core.json_tree.tree_builder import get_tree

        updated = get_tree(tree.tree_id)
        assert updated is not None
        assert updated.root_data == {"items": ["a", "x", "b", "c"]}

    def test_insert_after_element_by_node_id(self, tmp_path: Path) -> None:
        tree, items_id, b_id = self._items_tree(tmp_path)
        json_modify_tree(
            tree.tree_id,
            [
                {
                    "action": "insert",
                    "parent_node_id": items_id,
                    "value": "x",
                    "after_node_id": b_id,
                }
            ],
        )
        from ai_editor.core.json_tree.tree_builder import get_tree

        updated = get_tree(tree.tree_id)
        assert updated is not None
        assert updated.root_data == {"items": ["a", "b", "x", "c"]}

    def test_before_node_id_and_index_mutually_exclusive(self, tmp_path: Path) -> None:
        tree, items_id, b_id = self._items_tree(tmp_path)
        with pytest.raises(ValueError, match="mutually exclusive"):
            json_modify_tree(
                tree.tree_id,
                [
                    {
                        "action": "insert",
                        "parent_node_id": items_id,
                        "value": "x",
                        "before_node_id": b_id,
                        "index": 1,
                    }
                ],
            )


class TestJsonObjectSiblingInsert:
    """AT-JO-01 .. AT-JO-04."""

    @pytest.fixture(autouse=True)
    def _clear_json_sessions(self):
        import ai_editor.core.json_tree.tree_builder as tb

        tb._trees.clear()
        yield
        tb._trees.clear()

    def test_insert_before_key_preserves_order(self, tmp_path: Path) -> None:
        data = {"a": 1, "b": 2, "c": 3}
        tree = build_tree_from_data(str(tmp_path / "o.json"), data, register=True)
        json_modify_tree(
            tree.tree_id,
            [
                {
                    "action": "insert",
                    "parent_json_pointer": "",
                    "key": "x",
                    "value": 99,
                    "before_key": "b",
                }
            ],
        )
        from ai_editor.core.json_tree.tree_builder import get_tree

        updated = get_tree(tree.tree_id)
        assert updated is not None
        assert list(updated.root_data.keys()) == ["a", "x", "b", "c"]
        assert updated.root_data == {"a": 1, "x": 99, "b": 2, "c": 3}

    def test_insert_after_key_preserves_order(self, tmp_path: Path) -> None:
        data = {"a": 1, "b": 2, "c": 3}
        tree = build_tree_from_data(str(tmp_path / "o2.json"), data, register=True)
        json_modify_tree(
            tree.tree_id,
            [
                {
                    "action": "insert",
                    "parent_json_pointer": "",
                    "key": "x",
                    "value": 99,
                    "after_key": "b",
                }
            ],
        )
        from ai_editor.core.json_tree.tree_builder import get_tree

        updated = get_tree(tree.tree_id)
        assert updated is not None
        assert list(updated.root_data.keys()) == ["a", "b", "x", "c"]

    def test_before_key_missing_raises(self, tmp_path: Path) -> None:
        data = {"a": 1}
        tree = build_tree_from_data(str(tmp_path / "o3.json"), data, register=True)
        with pytest.raises(KeyError, match="Sibling key not found"):
            json_modify_tree(
                tree.tree_id,
                [
                    {
                        "action": "insert",
                        "parent_json_pointer": "",
                        "key": "x",
                        "value": 99,
                        "before_key": "no_such_key",
                    }
                ],
            )

    def test_before_and_after_key_mutually_exclusive(self, tmp_path: Path) -> None:
        data = {"a": 1, "b": 2}
        tree = build_tree_from_data(str(tmp_path / "o4.json"), data, register=True)
        with pytest.raises(ValueError, match="mutually exclusive"):
            json_modify_tree(
                tree.tree_id,
                [
                    {
                        "action": "insert",
                        "parent_json_pointer": "",
                        "key": "x",
                        "value": 99,
                        "before_key": "a",
                        "after_key": "b",
                    }
                ],
            )


class TestYamlSiblingInsert:
    """AT-YA-01 .. AT-YA-02."""

    @pytest.fixture(autouse=True)
    def _clear_yaml_sessions(self):
        import ai_editor.core.yaml_tree.tree_builder as yb

        yb._trees.clear()
        yield
        yb._trees.clear()

    def test_insert_before_key_preserves_yaml_order(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.yaml"
        path.write_text("a: 1\nb: 2\nc: 3\n", encoding="utf-8")
        tree = load_yaml_to_tree(str(path))
        _modify_yaml_registered_one(
            tree.tree_id,
            {
                "action": "insert",
                "parent_json_pointer": "",
                "key": "x",
                "value": 99,
                "before_key": "b",
            },
        )
        from ai_editor.core.yaml_tree.tree_builder import get_tree as yaml_get

        updated = yaml_get(tree.tree_id)
        assert updated is not None
        assert list(updated.root_data.keys()) == ["a", "x", "b", "c"]

    def test_insert_after_sequence_element(self, tmp_path: Path) -> None:
        path = tmp_path / "seq.yaml"
        path.write_text("items:\n  - a\n  - b\n  - c\n", encoding="utf-8")
        tree = load_yaml_to_tree(str(path))
        items_ptr = normalize_key_path("items")
        items_id = resolve_node_id_from_pointer(tree, items_ptr)
        b_id = resolve_node_id_from_pointer(tree, normalize_key_path("items.1"))
        assert items_id and b_id
        _modify_yaml_registered_one(
            tree.tree_id,
            {
                "action": "insert",
                "parent_node_id": items_id,
                "value": "x",
                "after_node_id": b_id,
            },
        )
        from ai_editor.core.yaml_tree.tree_builder import get_tree as yaml_get

        updated = yaml_get(tree.tree_id)
        assert updated is not None
        assert updated.root_data["items"] == ["a", "b", "x", "c"]


def test_universal_edit_normalization_strips_parent_for_sibling_insert(
    three_func_tree_id: str,
) -> None:
    tree = get_tree(three_func_tree_id)
    assert tree is not None
    beta_sid = _function_stable_id(three_func_tree_id, "beta")
    op = {
        "type": "insert",
        "target_node_id": beta_sid,
        "position": "after",
        "parent_node_id": "__root__",
        "code_lines": ["def z() -> None:", "    pass"],
    }
    resolved = _resolve_stable_to_span(op, tree)
    norm = _normalized_cst_modify_operation(resolved)
    assert "parent_node_id" not in norm
    assert norm.get("target_node_id")
