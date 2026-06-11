"""
Batch insert + replace must preserve unrelated sibling stable_id (sidecar path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from ai_editor.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from ai_editor.core.cst_tree.tree_builder import get_tree, load_file_to_tree
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
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


_SOURCE = """import os

from typing import List


def foo() -> None:
    pass
"""

_NESTED_CLASS = '''
class Widget:
    """Widget class."""

    def alpha(self) -> None:
        return None

    def beta(self) -> int:
        return 0
'''.strip()

_NESTED_INNER = """
def outer() -> None:
    def inner_a() -> int:
        return 1

    def inner_b() -> str:
        return "x"
""".strip()


def _function_stable_id(
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
                return meta.stable_id
            continue
        if in_class is not None:
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
                cur = pm.parent_id if pm else None
            continue
        if in_function is not None:
            outer_meta = next(
                m
                for m in tree.metadata_map.values()
                if m.type == "FunctionDef"
                and m.name == in_function
                and m.parent_id == root_id
            )
            cur = meta.node_id
            while cur is not None:
                if cur == outer_meta.node_id:
                    return meta.stable_id
                pm = tree.metadata_map.get(cur)
                cur = pm.parent_id if pm else None
    pytest.fail(f"No FunctionDef {name!r} (class={in_class!r}, fn={in_function!r})")


def _import_stable_id(tree_id: str, snippet: str) -> str:
    tree = get_tree(tree_id)
    assert tree is not None
    for meta in tree.metadata_map.values():
        if meta.type != "SimpleStatementLine":
            continue
        lines = tree.module.code.splitlines()
        lo = meta.start_line - 1
        hi = meta.end_line
        text = "\n".join(lines[lo:hi])
        if snippet in text:
            return meta.stable_id
    pytest.fail(f"No SimpleStatementLine matching {snippet!r}")


@pytest.mark.asyncio
async def test_batch_insert_then_replace_unrelated_import_stable_id(
    tmp_path,
) -> None:
    """Insert after one import must not stale sibling import stable_id in same batch."""
    path = tmp_path / "imports_batch.py"
    path.write_text(_SOURCE, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    os_target = _import_stable_id(tree.tree_id, "import os")
    typing_target = _import_stable_id(tree.tree_id, "from typing import List")
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
            result = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "insert",
                        "position": "after",
                        "target_node_id": os_target,
                        "code_lines": ["import sys"],
                    },
                    {
                        "type": "replace",
                        "node_id": typing_target,
                        "code_lines": ["from typing import Any"],
                    },
                ],
            )
        assert isinstance(result, SuccessResult), getattr(result, "message", result)
        after = get_tree(session.tree_id or tree.tree_id)
        assert after is not None
        assert (
            _import_stable_id(after.tree_id, "from typing import Any") == typing_target
        )
        assert "import sys" in after.module.code
    finally:
        release_session(session.session_id)


@pytest.mark.asyncio
async def test_batch_insert_then_replace_nested_class_methods(tmp_path) -> None:
    """Insert after method in class + replace sibling method in same batch."""
    path = tmp_path / "nested_class_batch.py"
    path.write_text(_NESTED_CLASS + "\n", encoding="utf-8")
    tree = load_file_to_tree(str(path))
    alpha_sid = _function_stable_id(tree.tree_id, "alpha", in_class="Widget")
    beta_sid = _function_stable_id(tree.tree_id, "beta", in_class="Widget")
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
            result = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "insert",
                        "position": "after",
                        "target_node_id": alpha_sid,
                        "code_lines": [
                            "",
                            "def gamma(self) -> bool:",
                            "    return True",
                        ],
                    },
                    {
                        "type": "replace",
                        "node_id": beta_sid,
                        "code_lines": [
                            "def beta(self) -> int:",
                            "    return 42",
                        ],
                    },
                ],
            )
        assert isinstance(result, SuccessResult), getattr(result, "message", result)
        after = get_tree(session.tree_id or tree.tree_id)
        assert after is not None
        assert _function_stable_id(after.tree_id, "beta", in_class="Widget") == beta_sid
        assert "def gamma" in after.module.code
        assert "return 42" in after.module.code
    finally:
        release_session(session.session_id)


@pytest.mark.asyncio
async def test_batch_insert_then_replace_nested_inner_functions(tmp_path) -> None:
    """Insert after inner function + replace sibling inner in same batch."""
    path = tmp_path / "nested_inner_batch.py"
    path.write_text(_NESTED_INNER + "\n", encoding="utf-8")
    tree = load_file_to_tree(str(path))
    inner_a_sid = _function_stable_id(tree.tree_id, "inner_a", in_function="outer")
    inner_b_sid = _function_stable_id(tree.tree_id, "inner_b", in_function="outer")
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
            result = await cmd.execute(
                project_id="test-project",
                session_id=session.session_id,
                operations=[
                    {
                        "type": "insert",
                        "position": "after",
                        "target_node_id": inner_a_sid,
                        "code_lines": [
                            "",
                            "def inner_mid() -> None:",
                            "    pass",
                        ],
                    },
                    {
                        "type": "replace",
                        "node_id": inner_b_sid,
                        "code_lines": [
                            "def inner_b() -> str:",
                            '    return "updated"',
                        ],
                    },
                ],
            )
        assert isinstance(result, SuccessResult), getattr(result, "message", result)
        after = get_tree(session.tree_id or tree.tree_id)
        assert after is not None
        assert (
            _function_stable_id(after.tree_id, "inner_b", in_function="outer")
            == inner_b_sid
        )
        assert "inner_mid" in after.module.code
        assert '"updated"' in after.module.code
    finally:
        release_session(session.session_id)
