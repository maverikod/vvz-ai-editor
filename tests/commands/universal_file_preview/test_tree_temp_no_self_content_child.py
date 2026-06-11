"""JSON/YAML preview must not duplicate node body as a synthetic child block."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from ai_editor.commands.universal_file_preview.handlers.yaml_handler import (
    YamlFileHandler,
)
from ai_editor.commands.universal_file_preview.models import NodeKind
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview.response import build_envelope


def _structural_budget() -> PreviewBudget:
    return PreviewBudget(
        preview_lines=20,
        value_preview_len=120,
        full_text_max_lines=0,
    )


def _assert_no_content_child(envelope: dict) -> None:
    blocks = envelope["blocks"]
    refs = [b.get("node_ref", "") for b in blocks]
    assert not any(str(ref).endswith("/__content") for ref in refs)
    assert not any(str(ref) == "__content" for ref in refs)


def test_json_mapping_no_synthetic_content_child(tmp_path: Path) -> None:
    """AC-5: JSON mapping blocks are keys only; scalar value stays inline."""
    path = tmp_path / "doc.json"
    path.write_text(
        '{"title": "Hello", "body": "long body text here", "nested": {"a": 1}}\n',
        encoding="utf-8",
    )
    handler = JsonFileHandler()
    budget = _structural_budget()
    params = {
        "file_path": str(path),
        "project_id": "test-proj",
        "node_ref": None,
        "selector": None,
        "preview_budget": budget,
    }
    nav = navigate(handler, params, budget)
    assert not isinstance(nav, PreviewError)
    envelope = build_envelope(nav, None, "none")
    _assert_no_content_child(envelope)
    assert envelope["total_blocks"] == 3
    assert {b["node_ref"] for b in envelope["blocks"]} == {"/title", "/body", "/nested"}

    scalar_nav = navigate(
        handler,
        {**params, "node_ref": "/body"},
        budget,
    )
    assert not isinstance(scalar_nav, PreviewError)
    assert scalar_nav.focus_node.node_kind == NodeKind.SCALAR
    assert scalar_nav.total_blocks == 0
    scalar_env = build_envelope(scalar_nav, None, "none")
    assert scalar_env["blocks"] == []
    assert scalar_env["focus"]["attributes"].get("value") == "long body text here"


def test_yaml_mapping_no_synthetic_content_child(tmp_path: Path) -> None:
    """AC-5: YAML mapping blocks are keys only; scalar value stays inline."""
    pytest.importorskip("yaml")
    path = tmp_path / "doc.yaml"
    path.write_text(
        "title: Hello\nbody: long body text here\nnested:\n  a: 1\n",
        encoding="utf-8",
    )
    handler = YamlFileHandler()
    budget = _structural_budget()
    params = {
        "file_path": str(path),
        "project_id": "test-proj",
        "node_ref": None,
        "selector": None,
        "preview_budget": budget,
    }
    nav = navigate(handler, params, budget)
    assert not isinstance(nav, PreviewError)
    envelope = build_envelope(nav, None, "none")
    _assert_no_content_child(envelope)
    assert envelope["total_blocks"] == 3
    assert {b["node_ref"] for b in envelope["blocks"]} == {"/title", "/body", "/nested"}

    scalar_nav = navigate(
        handler,
        {**params, "node_ref": "/body"},
        budget,
    )
    assert not isinstance(scalar_nav, PreviewError)
    assert scalar_nav.focus_node.node_kind == NodeKind.SCALAR
    assert scalar_nav.total_blocks == 0
    scalar_env = build_envelope(scalar_nav, None, "none")
    assert scalar_env["blocks"] == []
    assert scalar_env["focus"]["attributes"].get("value") == "long body text here"
