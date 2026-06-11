"""Marked-tree PreviewNavigation wiring for universal_file_preview (G-004)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.dispatcher import HandlerDispatcher
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.marked_tree_loader import (
    make_preview_tree_loader,
    parse_focus_short_id,
)
from ai_editor.commands.universal_file_preview.marked_tree_navigation import (
    navigate_marked_tree,
    should_use_marked_tree_navigation,
)
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview.response import build_envelope
from ai_editor.core.search_session.tree_representation import TreeValidityState


@pytest.fixture
def json_project(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path
    rel = "data/sample.json"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
    return root, path, rel


def test_make_preview_tree_loader_calls_tree_lifecycle(
    json_project: tuple[Path, Path, str],
) -> None:
    root, path, rel = json_project
    loader = make_preview_tree_loader(
        project_root=root,
        rel_file_path=rel,
        preview_abs_path=path,
        bound_session_id=None,
    )
    with patch(
        "ai_editor.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path"
    ) as from_path:
        from_path.return_value = (MagicMock(), TreeValidityState.reused)
        tree = loader(path, None)
    from_path.assert_called_once_with(project_root=root, file_path=rel)
    assert tree.nodes
    assert all(isinstance(n.short_id, int) for n in tree.nodes)


def test_parse_focus_short_id_root_and_explicit(
    json_project: tuple[Path, Path, str],
) -> None:
    root, path, rel = json_project
    loader = make_preview_tree_loader(
        project_root=root,
        rel_file_path=rel,
        preview_abs_path=path,
        bound_session_id=None,
    )
    with patch(
        "ai_editor.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        nodes = loader(path, None).nodes
    root_id = parse_focus_short_id(None, nodes)
    assert isinstance(root_id, int)
    assert root_id >= 1
    key_node = next(n for n in nodes if n.attributes.get("json_pointer") == "/a")
    assert parse_focus_short_id(str(key_node.short_id), nodes) == key_node.short_id


def test_navigate_marked_tree_returns_short_id_int_refs(
    json_project: tuple[Path, Path, str],
) -> None:
    root, path, rel = json_project
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=200
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    with patch(
        "ai_editor.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(params, budget)
    assert not isinstance(result, PreviewError)
    envelope = build_envelope(result, None, "none")
    assert isinstance(envelope["focus"]["node_ref"], int)
    assert envelope["focus"]["node_ref"] >= 1
    assert envelope["total_blocks"] == 2
    assert envelope["blocks"]
    for block in envelope["blocks"]:
        assert isinstance(block["node_ref"], int)


def test_navigation_branches_to_marked_tree_for_json(
    json_project: tuple[Path, Path, str],
) -> None:
    root, path, rel = json_project
    handler = HandlerDispatcher().dispatch(rel)
    assert handler is not None and not isinstance(handler, PreviewError)
    budget = PreviewBudget(
        preview_lines=5, value_preview_len=80, full_text_max_lines=200
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
        "project_id": "test-proj",
    }
    assert should_use_marked_tree_navigation(handler, params)
    with patch(
        "ai_editor.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.recreated),
    ):
        result = navigate(handler, params, budget)
    assert not isinstance(result, PreviewError)
    assert result.short_id_refs is True


def test_should_use_marked_tree_false_for_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "lines.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    handler = HandlerDispatcher().dispatch("lines.jsonl")
    assert handler is not None and not isinstance(handler, PreviewError)
    params = {
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
    }
    assert should_use_marked_tree_navigation(handler, params) is False


def test_navigate_marked_tree_python_root_lists_top_level_blocks(
    tmp_path: Path,
) -> None:
    """Root view on .py must list module-level nodes, not inner expr children."""
    root = tmp_path
    rel = "pkg/mod.py"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '"""Module doc."""\n\nimport os\n\n\nclass Widget:\n    pass\n',
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=80, full_text_max_lines=200
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    with patch(
        "ai_editor.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(params, budget)
    assert not isinstance(result, PreviewError)
    assert result.total_blocks >= 3
    texts = " ".join((b.text or "") for b in result.selected_blocks)
    assert "Module doc" in texts or "import os" in texts
    assert "class Widget" in texts
