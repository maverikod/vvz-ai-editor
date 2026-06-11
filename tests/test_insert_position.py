"""Unit tests for unified insert position colon syntax."""

from __future__ import annotations

import pytest

from ai_editor.commands.universal_file_edit.insert_position import (
    coalesce_tree_temp_insert_position,
    parse_colon_position,
    resolve_text_insert_side_and_node_ref,
)


def test_parse_colon_position_array_pointer() -> None:
    assert parse_colon_position("before:/items/1") == ("before", "/items/1")
    assert parse_colon_position("after:/items/0") == ("after", "/items/0")


def test_coalesce_tree_temp_maps_pointer() -> None:
    mop: dict = {"position": "before:/items/2", "parent_json_pointer": "/items"}
    coalesce_tree_temp_insert_position(mop)
    assert mop["before_json_pointer"] == "/items/2"
    assert "position" not in mop


def test_coalesce_tree_temp_maps_object_key() -> None:
    mop = {"position": "after:beta", "key": "gamma"}
    coalesce_tree_temp_insert_position(mop)
    assert mop["after_key"] == "beta"


def test_resolve_text_insert_embedded_node_ref() -> None:
    side, ref = resolve_text_insert_side_and_node_ref(
        {"position": "before:intro.setup", "node_ref": "intro.setup"}
    )
    assert side == "before"
    assert ref == "intro.setup"


def test_resolve_text_conflict_raises() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        resolve_text_insert_side_and_node_ref({"position": "after:a", "node_ref": "b"})
