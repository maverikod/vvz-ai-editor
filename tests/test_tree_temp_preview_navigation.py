"""
Tests for tree-temp Sidecar preview drill-down (G-004 T-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview.session import resolve_session
from ai_editor.commands.universal_file_preview.tree_temp_preview_focus import (
    TreeTempPreviewResolveError,
    resolve_tree_temp_preview_focus,
)
from ai_editor.core.json_tree.tree_builder import build_tree_from_data, remove_tree
from ai_editor.core.tree_temp.tree_node import TreeNode


_SID_OBJ = "11111111-1111-4111-a111-111111111111"
_SID_SCALAR = "22222222-2222-4222-a222-222222222222"


def test_resolve_tree_temp_container_drill_down() -> None:
    leaf = TreeNode(
        stable_id=_SID_SCALAR,
        type="string",
        key="k",
        value="v",
        children=None,
        comment_before=None,
        comment_inline=None,
    )
    root = TreeNode(
        stable_id=_SID_OBJ,
        type="object",
        key=None,
        value=None,
        children=[leaf],
        comment_before=None,
        comment_inline=None,
    )
    out = resolve_tree_temp_preview_focus(roots=[root], node_ref=_SID_OBJ)
    assert out.effective_mode == "container_drill_down"
    assert out.container.stable_id == _SID_OBJ
    assert len(out.container.children or []) == 1


def test_resolve_tree_temp_scalar_promotes_to_parent_container() -> None:
    leaf = TreeNode(
        stable_id=_SID_SCALAR,
        type="number",
        key="x",
        value=1,
        children=None,
        comment_before=None,
        comment_inline=None,
    )
    root = TreeNode(
        stable_id=_SID_OBJ,
        type="object",
        key=None,
        value=None,
        children=[leaf],
        comment_before=None,
        comment_inline=None,
    )
    out = resolve_tree_temp_preview_focus(roots=[root], node_ref=_SID_SCALAR)
    assert out.effective_mode == "scalar_node_ref_effective_focus"
    assert out.container.stable_id == _SID_OBJ
    assert len(out.container.children or []) == 1


def test_resolve_tree_temp_unknown_stable_id_raises() -> None:
    root = TreeNode(
        stable_id=_SID_OBJ,
        type="object",
        children=[],
        key=None,
        value=None,
        comment_before=None,
        comment_inline=None,
    )
    with pytest.raises(TreeTempPreviewResolveError) as ei:
        resolve_tree_temp_preview_focus(
            roots=[root],
            node_ref="ffffffff-ffff-4fff-afff-ffffffffffff",
        )
    assert str(ei.value).startswith("UNKNOWN_STABLE_ID")


def test_resolve_session_finds_json_tree_session(tmp_path: Path) -> None:
    """Caller-owned JSON ``tree_id`` resolves via json tree registry."""

    path = tmp_path / "sess.json"
    path.write_text("{}", encoding="utf-8")
    tree = build_tree_from_data(str(path.resolve()), {}, register=True)
    try:
        out = resolve_session(JsonFileHandler(), {"tree_id": tree.tree_id})
        assert not isinstance(out, PreviewError)
        session, origin, _ = out
        assert origin == "caller_owned"
        assert session is tree
    finally:
        remove_tree(tree.tree_id)


def test_navigate_tree_temp_sidecar_stable_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    leaf = TreeNode(
        stable_id=_SID_SCALAR,
        type="string",
        key="msg",
        value="hi",
        children=None,
        comment_before=None,
        comment_inline=None,
    )
    root = TreeNode(
        stable_id=_SID_OBJ,
        type="object",
        children=[leaf],
        key=None,
        value=None,
        comment_before=None,
        comment_inline=None,
    )

    pj = tmp_path / "nested.json"
    pj.write_text('{"msg":"hi"}', encoding="utf-8")

    def _fake_resolve(*_args, **_kw):
        return (None, "none", None)

    import ai_editor.commands.universal_file_preview.navigation as nav_mod

    monkeypatch.setattr(nav_mod, "resolve_session", _fake_resolve)

    handler = JsonFileHandler()
    res = navigate(
        handler,
        {
            "file_path": str(pj),
            "node_ref": _SID_SCALAR,
            "selector": None,
            "tree_temp_roots": [root],
        },
        PreviewBudget(preview_lines=20, value_preview_len=120, full_text_max_lines=200),
    )

    assert not isinstance(res, PreviewError)
    assert res.total_blocks >= 1
    assert res.selected_blocks[0].node_ref == _SID_SCALAR
