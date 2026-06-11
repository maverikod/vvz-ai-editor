"""YAML preview annotated full-text respects array index and local key lines."""

from __future__ import annotations

import pathlib

import pytest

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.handlers.yaml_handler import (
    YamlFileHandler,
)
from ai_editor.commands.universal_file_preview.errors import PreviewError


def _concepts_yaml() -> str:
    lines = ["concepts:"]
    for i in range(12):
        lines.extend(
            [
                f"  - concept_id: C-{i:03d}",
                "    name: shared-name",
                "    source_ranges:",
                "      - start: 1",
                "        end: 2",
            ]
        )
    return "\n".join(lines) + "\n"


def _write_concepts(path: pathlib.Path) -> None:
    path.write_text(_concepts_yaml(), encoding="utf-8")


@pytest.fixture
def budget() -> PreviewBudget:
    return PreviewBudget(
        preview_lines=50,
        value_preview_len=120,
        full_text_max_lines=200,
    )


def test_distinct_array_indices_return_distinct_elements(
    tmp_path: pathlib.Path,
    budget: PreviewBudget,
) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "concepts.yaml"
    _write_concepts(path)
    handler = YamlFileHandler()
    assert not isinstance(handler.open_root(str(path), None, budget=budget), PreviewError)

    zero = handler.resolve_node_ref("/concepts/0", None)
    nine = handler.resolve_node_ref("/concepts/9", None)
    assert not isinstance(zero, PreviewError)
    assert not isinstance(nine, PreviewError)
    assert zero.attributes.get("full_text") is True
    assert nine.attributes.get("full_text") is True
    zero_text = zero.attributes.get("text", "")
    nine_text = nine.attributes.get("text", "")
    assert zero_text != nine_text
    assert "C-000" in zero_text
    assert "C-009" in nine_text
    assert "C-000" not in nine_text


def test_array_index_annotations_use_correct_pointer(
    tmp_path: pathlib.Path,
    budget: PreviewBudget,
) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "concepts.yaml"
    _write_concepts(path)
    handler = YamlFileHandler()
    assert not isinstance(handler.open_root(str(path), None, budget=budget), PreviewError)

    resolved = handler.resolve_node_ref("/concepts/9", None)
    assert not isinstance(resolved, PreviewError)
    text = resolved.attributes.get("text", "")
    assert "[/concepts/9" in text
    assert "[/concepts/0" not in text
    assert "[/concepts/9/concept_id]" in text
    assert "[/concepts/9/name]" in text


def test_repeated_key_names_annotate_to_local_pointer(
    tmp_path: pathlib.Path,
    budget: PreviewBudget,
) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "concepts.yaml"
    _write_concepts(path)
    handler = YamlFileHandler()
    assert not isinstance(handler.open_root(str(path), None, budget=budget), PreviewError)

    resolved = handler.resolve_node_ref("/concepts/9", None)
    assert not isinstance(resolved, PreviewError)
    text = resolved.attributes.get("text", "")
    for line in text.splitlines():
        if "start:" in line:
            assert line.startswith("[/concepts/9/source_ranges/0/start]")
            break
    else:
        raise AssertionError("expected start: line in focus text")


def test_anchor_alias_preview_no_regression(
    tmp_path: pathlib.Path,
    budget: PreviewBudget,
) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "alias.yaml"
    path.write_text(
        """defaults: &def
  name: x
item:
  <<: *def
  extra: y
""",
        encoding="utf-8",
    )
    handler = YamlFileHandler()
    root = handler.open_root(str(path), None, budget=budget)
    assert not isinstance(root, PreviewError)

    item = handler.resolve_node_ref("/item", None)
    assert not isinstance(item, PreviewError)
    assert item.attributes.get("full_text") is True
    text = item.attributes.get("text", "")
    assert "[/item/<<]" in text or "[/item]" in text
    assert "extra: y" in text

    by_name = handler.resolve_node_ref("/item/extra", None)
    assert not isinstance(by_name, PreviewError)
    assert by_name.node_kind.name == "SCALAR"
    if by_name.attributes.get("full_text"):
        assert "extra: y" in by_name.attributes.get("text", "")
    else:
        assert by_name.attributes.get("value") == "y"
