"""Parse-time start_line metadata on YamlNodeMetadata."""

from __future__ import annotations

import pytest

from ai_editor.core.yaml_tree.models import ROOT_POINTER
from ai_editor.core.yaml_tree.tree_builder import build_yaml_tree_from_text


def _meta_by_pointer(tree, pointer: str):
    for meta in tree.metadata_map.values():
        if meta.yaml_pointer == pointer:
            return meta
    raise KeyError(pointer)


def test_build_yaml_tree_populates_start_line_for_mapping_keys() -> None:
    pytest.importorskip("yaml")
    source = """root:
  alpha: 1
  beta: 2
other: 9
"""
    tree = build_yaml_tree_from_text("/tmp/t.yaml", source)
    root = _meta_by_pointer(tree, ROOT_POINTER)
    assert root.start_line == 1
    assert _meta_by_pointer(tree, "/root").start_line == 1
    assert _meta_by_pointer(tree, "/root/alpha").start_line == 2
    assert _meta_by_pointer(tree, "/root/beta").start_line == 3
    assert _meta_by_pointer(tree, "/other").start_line == 4


def test_build_yaml_tree_populates_start_line_for_sequence_elements() -> None:
    pytest.importorskip("yaml")
    lines = ["concepts:"]
    for i in range(12):
        lines.extend(
            [
                f"  - concept_id: C-{i:03d}",
                f"    name: concept-{i}",
            ]
        )
    source = "\n".join(lines) + "\n"
    tree = build_yaml_tree_from_text("/tmp/concepts.yaml", source)

    first = _meta_by_pointer(tree, "/concepts/0")
    ninth = _meta_by_pointer(tree, "/concepts/9")
    assert first.start_line == 2
    assert ninth.start_line == 20
    assert first.start_line != ninth.start_line
    assert _meta_by_pointer(tree, "/concepts/0/concept_id").start_line == 2
    assert _meta_by_pointer(tree, "/concepts/9/concept_id").start_line == 20
    assert _meta_by_pointer(tree, "/concepts/9/name").start_line == 21


def test_alias_node_uses_alias_occurrence_line() -> None:
    pytest.importorskip("yaml")
    source = """defaults: &def
  name: x
item:
  <<: *def
  extra: y
"""
    tree = build_yaml_tree_from_text("/tmp/alias.yaml", source)
    merge = _meta_by_pointer(tree, "/item/<<")
    assert merge.start_line == 4
    assert merge.start_line != _meta_by_pointer(tree, "/defaults").start_line
