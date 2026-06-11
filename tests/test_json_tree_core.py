"""
Tests for JSON tree sessions (load, index, modify, save helpers).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_editor.core.json_tree.json_query import (
    normalize_key_path,
    resolve_node_id_from_pointer,
)
from ai_editor.core.json_tree.json_saver import save_json_tree_to_file
from ai_editor.core.json_tree.models import ROOT_POINTER, stable_node_id_for_pointer
from ai_editor.core.json_tree.tree_builder import (
    build_tree_from_data,
    get_tree,
    load_file_to_tree,
    reload_tree_from_file,
    remove_tree,
)
from ai_editor.core.json_tree.tree_modifier import modify_tree


@pytest.fixture(autouse=True)
def _clear_json_sessions() -> Generator[None, None, None]:
    """Isolate in-memory JSON sessions between tests."""
    import ai_editor.core.json_tree.tree_builder as tb

    tb._trees.clear()
    yield
    tb._trees.clear()


def test_stable_node_id_deterministic_for_pointer() -> None:
    p = "/foo/bar"
    assert stable_node_id_for_pointer(p) == stable_node_id_for_pointer(p)
    assert stable_node_id_for_pointer(p) != stable_node_id_for_pointer("/foo/baz")


def test_build_tree_indexes_nested_structure(tmp_path: Path) -> None:
    data = {"a": {"b": [1, {"c": True}]}}
    tree = build_tree_from_data(str(tmp_path / "x.json"), data, register=True)
    assert tree.root_node_id == stable_node_id_for_pointer(ROOT_POINTER)
    root_id = tree.root_node_id
    assert root_id is not None
    assert tree.metadata_map[root_id].kind == "object"
    ptr_b0 = normalize_key_path("a.b.0")
    nid = resolve_node_id_from_pointer(tree, ptr_b0)
    assert nid is not None
    assert tree.metadata_map[nid].kind == "number"


def test_load_file_to_tree_registers_session(tmp_path: Path) -> None:
    f = tmp_path / "doc.json"
    f.write_text('{"x": 1}\n', encoding="utf-8")
    tree = load_file_to_tree(str(f))
    assert get_tree(tree.tree_id) is tree
    remove_tree(tree.tree_id)
    assert get_tree(tree.tree_id) is None


def test_modify_replace_delete_insert(tmp_path: Path) -> None:
    data = {"items": [1, 2], "extra": {}}
    tree = build_tree_from_data(str(tmp_path / "m.json"), data, register=True)
    tid = tree.tree_id

    root_ptr = ""
    root_id = tree.root_node_id
    assert root_id is not None
    items_ptr = normalize_key_path("items")
    items_id = resolve_node_id_from_pointer(tree, items_ptr)
    assert items_id is not None

    modify_tree(
        tid,
        [
            {"action": "replace", "json_pointer": items_ptr, "value": [10]},
        ],
    )
    t = get_tree(tid)
    assert t is not None
    assert t.root_data["items"] == [10]

    modify_tree(
        tid,
        [
            {
                "action": "insert",
                "parent_json_pointer": items_ptr,
                "value": 20,
            },
        ],
    )
    t = get_tree(tid)
    assert t is not None
    assert t.root_data["items"] == [10, 20]

    modify_tree(
        tid,
        [
            {"action": "delete", "json_pointer": normalize_key_path("items.0")},
        ],
    )
    t = get_tree(tid)
    assert t is not None
    assert t.root_data["items"] == [20]

    modify_tree(
        tid,
        [
            {
                "action": "insert",
                "parent_json_pointer": root_ptr,
                "key": "new_key",
                "value": "hello",
            },
        ],
    )
    t = get_tree(tid)
    assert t is not None
    assert t.root_data["new_key"] == "hello"


def test_reload_tree_from_file(tmp_path: Path) -> None:
    f = tmp_path / "r.json"
    f.write_text('{"v": 1}', encoding="utf-8")
    tree = load_file_to_tree(str(f))
    tid = tree.tree_id
    tree.root_data["v"] = 99
    f.write_text('{"v": 2}', encoding="utf-8")
    reloaded = reload_tree_from_file(tid)
    assert reloaded is not None
    assert reloaded.root_data["v"] == 2


def test_save_json_tree_to_file_atomic_write_skips_db(tmp_path: Path) -> None:
    """save_json_tree_to_file atomically writes JSON when database is omitted."""
    root_dir = tmp_path / "proj"
    root_dir.mkdir()
    target = root_dir / "data.json"
    target.write_text('{"a": 0}\n', encoding="utf-8")

    data = {"a": 1, "b": [2]}
    tree = build_tree_from_data(str(target.resolve()), data, register=True)
    tid = tree.tree_id

    result = save_json_tree_to_file(
        tree_id=tid,
        file_path=str(target),
        root_dir=root_dir,
        project_id="550e8400-e29b-41d4-a716-446655440000",
        database=None,
        backup=False,
    )

    assert result["success"] is True
    assert result.get("skipped_db") is True
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == data


def test_save_json_tree_to_file_rejects_target_outside_root(tmp_path: Path) -> None:
    root_dir = tmp_path / "proj"
    root_dir.mkdir()
    outside = tmp_path / "escape.json"

    tree = build_tree_from_data(str(root_dir / "in.json"), {"a": 1}, register=True)
    db = MagicMock()

    result = save_json_tree_to_file(
        tree_id=tree.tree_id,
        file_path=str(outside),
        root_dir=root_dir,
        project_id="550e8400-e29b-41d4-a716-446655440000",
        database=db,
        backup=False,
    )

    assert result["success"] is False
    assert result["error_code"] == "INVALID_FILE_PATH"
    assert outside.exists() is False


def test_key_path_normalization_matches_pointer() -> None:
    assert normalize_key_path("a.b.0") == "/a/b/0"
    assert normalize_key_path(["a", "b", 0]) == "/a/b/0"
