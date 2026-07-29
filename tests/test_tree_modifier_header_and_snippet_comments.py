"""Regression tests for header-only replace gating and snippet leading comments.

Bugs 831a82be (implicit header-only replace silently keeps the old body) and
5495f4be (leading comments of a replacement snippet are dropped).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import libcst as cst
import pytest

from ai_editor.core.cst_tree.models import TreeOperation, TreeOperationType
from ai_editor.core.cst_tree.tree_builder import create_tree_from_code, get_tree
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.cst_tree.tree_modifier_ops_parse import parse_code_snippet

SOURCE = (
    '"""Module."""\n'
    "\n"
    "CONST = 1\n"
    "\n"
    "\n"
    "def target() -> int:\n"
    '    """Return one."""\n'
    "    x = 1\n"
    "    return x\n"
)


def _function_node_id(tree) -> str:
    for node_id, meta in tree.metadata_map.items():
        if meta.type == "FunctionDef":
            return node_id
    raise AssertionError("FunctionDef not found")


def test_bare_signature_replace_without_flag_is_explicit_error() -> None:
    """Bug 831a82be: no silent body retention for a bare signature snippet."""
    tree = create_tree_from_code("/tmp/831a82be_a.py", SOURCE, persist_sidecar=False)
    node_id = _function_node_id(tree)
    operation = TreeOperation(
        action=TreeOperationType.REPLACE,
        node_id=node_id,
        code="def target() -> int:",
    )
    with pytest.raises(ValueError):
        modify_tree(tree.tree_id, [operation])
    unchanged = get_tree(tree.tree_id)
    assert unchanged is not None
    assert "x = 1" in unchanged.module.code


def test_header_only_replace_requires_explicit_flag() -> None:
    """Bug 831a82be: header patching still works when explicitly requested."""
    tree = create_tree_from_code("/tmp/831a82be_b.py", SOURCE, persist_sidecar=False)
    node_id = _function_node_id(tree)
    operation = TreeOperation(
        action=TreeOperationType.REPLACE,
        node_id=node_id,
        code="def renamed_target() -> int:",
        header_only=True,
    )
    modify_tree(tree.tree_id, [operation])
    updated = get_tree(tree.tree_id)
    assert updated is not None
    assert "def renamed_target() -> int:" in updated.module.code
    assert "return x" in updated.module.code


def test_parse_code_snippet_keeps_leading_comments() -> None:
    """Bug 5495f4be: comment lines before the first snippet statement survive."""
    statements = parse_code_snippet(
        code_lines=["# directive one", "# directive two", "CONST = 2"]
    )
    module = cst.Module(body=statements)
    rendered = module.code
    assert "# directive one" in rendered
    assert "# directive two" in rendered
    assert "CONST = 2" in rendered
