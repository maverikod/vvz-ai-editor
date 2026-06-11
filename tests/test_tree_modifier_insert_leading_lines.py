"""
BUG-INSERT-LEADING-LINES: insert must preserve leading blank lines from code_lines.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

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

CONTAINER_SOURCE = '''"""Sandbox module."""


class Container:
    """Holds values."""

    def double(self, n: int) -> int:
        """Double n."""
        return n * 2
'''


def _blank_lines_before_def(source: str, def_name: str) -> int:
    lines = source.splitlines()
    def_idx = next(
        i
        for i, ln in enumerate(lines)
        if ln.lstrip().startswith(f"def {def_name}")
    )
    n = 0
    for i in range(def_idx - 1, -1, -1):
        if lines[i].strip() == "":
            n += 1
        else:
            break
    return n


def _find_class_node_id(tree_id: str, class_name: str) -> str:
    t = get_tree(tree_id)
    assert t is not None
    for nid, meta in t.metadata_map.items():
        if meta.type == "ClassDef" and meta.name == class_name:
            return nid
    pytest.fail(f"No class {class_name!r}")


@pytest.fixture
def container_tree_id(tmp_path):
    path = str(tmp_path / "container.py")
    tree = create_tree_from_code(path, CONTAINER_SOURCE.strip())
    yield tree.tree_id
    remove_tree(tree.tree_id)


class TestInsertLeadingBlankLines:
    """AT-INSERT-01 .. AT-INSERT-05 from BUG-INSERT-LEADING-LINES."""

    def test_two_blank_lines_before_top_level_function_last(
        self, container_tree_id: str
    ) -> None:
        modified = modify_tree(
            container_tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="last",
                    code_lines=[
                        "",
                        "",
                        "def delta(n: int) -> int:",
                        '    """Inserted."""',
                        "    return n * 2",
                    ],
                )
            ],
        )
        code = modified.module.code
        assert _blank_lines_before_def(code, "delta") == 2
        assert '"""Inserted."""' in code

    def test_one_blank_line_before_top_level_function_last(
        self, container_tree_id: str
    ) -> None:
        modified = modify_tree(
            container_tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="last",
                    code_lines=[
                        "",
                        "def eta() -> None:",
                        "    pass",
                    ],
                )
            ],
        )
        code = modified.module.code
        assert _blank_lines_before_def(code, "eta") == 1

    def test_no_blank_lines_when_code_lines_have_none(
        self, container_tree_id: str
    ) -> None:
        modified = modify_tree(
            container_tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="last",
                    code_lines=[
                        "def theta() -> None:",
                        "    pass",
                    ],
                )
            ],
        )
        code = modified.module.code
        assert _blank_lines_before_def(code, "theta") == 0

    def test_two_blank_lines_before_top_level_function_first(
        self, container_tree_id: str
    ) -> None:
        modified = modify_tree(
            container_tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=ROOT_NODE_ID_SENTINEL,
                    position="first",
                    code_lines=[
                        "",
                        "",
                        "def zeta() -> None:",
                        "    pass",
                    ],
                )
            ],
        )
        code = modified.module.code
        assert _blank_lines_before_def(code, "zeta") == 2
        assert code.index("def zeta") < code.index("class Container")

    def test_one_blank_line_before_method_in_class_body(
        self, container_tree_id: str
    ) -> None:
        container_id = _find_class_node_id(container_tree_id, "Container")
        modified = modify_tree(
            container_tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.INSERT,
                    parent_node_id=container_id,
                    position="last",
                    code_lines=[
                        "",
                        "def new_method(self) -> None:",
                        "    pass",
                    ],
                )
            ],
        )
        code = modified.module.code
        container_section = code.split("class Container:")[1]
        assert _blank_lines_before_def(container_section, "new_method") == 1
