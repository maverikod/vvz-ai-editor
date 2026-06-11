"""Tests for C-015 op_edit_attributes across format handlers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import yaml

from ai_editor.tree.contracts import NodeId
from ai_editor.tree.edit_operations import (
    EditOperation,
    EditOperationKind,
    apply_edit_operation,
)
from ai_editor.tree.handler_registry import HandlerRegistry
from ai_editor.tree.handlers.python_handler import _collect_sid_extra_meta

_REGISTRY = HandlerRegistry.default_registry()
_ID_KEY = "___id___"
_META_KEY = "___meta___"


def _find_wrapped_node(obj: Any, sid: int) -> Optional[dict[str, Any]]:
    if isinstance(obj, dict) and _ID_KEY in obj and int(obj[_ID_KEY]) == sid:
        return obj
    if isinstance(obj, dict):
        val = obj.get("v")
        if isinstance(val, dict):
            for item in val.values():
                found = _find_wrapped_node(item, sid)
                if found is not None:
                    return found
        elif isinstance(val, list):
            for item in val:
                found = _find_wrapped_node(item, sid)
                if found is not None:
                    return found
        for key, item in obj.items():
            if key in (_ID_KEY, _META_KEY, "v"):
                continue
            found = _find_wrapped_node(item, sid)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_wrapped_node(item, sid)
            if found is not None:
                return found
    return None


def _target_short_id(
    handler: object, source_path: Path, content: str, marked: str
) -> NodeId:
    if source_path.suffix == ".py":
        match = re.search(r"___id___:(\d+)", marked)
        assert match is not None, "expected Python marker in marked text"
        return NodeId(int(match.group(1)))
    body = content.rstrip("\n")
    nodes = handler.parse_content(source_path, body)
    assert nodes, f"expected nodes for {source_path}"
    return nodes[0].short_id


def _apply_edit_attributes(
    *,
    extension: str,
    content: str,
    attributes: Dict[str, Any],
) -> tuple[str, str, NodeId, object]:
    source_path = Path(f"sample{extension}")
    handler = _REGISTRY.resolve(source_path)
    marked = handler.mark(content)
    target_sid = _target_short_id(handler, source_path, content, marked)
    new_marked, _ = apply_edit_operation(
        registry=_REGISTRY,
        source_path=source_path,
        marked_text=marked,
        operation=EditOperation(
            kind=EditOperationKind.EDIT_ATTRIBUTES,
            short_id=target_sid,
            attributes=attributes,
        ),
        tree_is_valid=True,
    )
    return marked, new_marked, target_sid, handler


@pytest.mark.parametrize(
    ("extension", "content", "attributes"),
    (
        (".json", '{"a": 1}\n', {"tag": "json-test"}),
        (".yaml", "key: value\n", {"tag": "yaml-test"}),
        (".py", "x = 1\n", {"tag": "py-test"}),
    ),
)
def test_edit_attributes_changes_metadata_not_content(
    extension: str,
    content: str,
    attributes: Dict[str, Any],
) -> None:
    marked, new_marked, target_sid, handler = _apply_edit_attributes(
        extension=extension,
        content=content,
        attributes=attributes,
    )

    assert handler.unmark(new_marked) == handler.unmark(marked)
    assert new_marked != marked

    if extension == ".py":
        sid_meta = _collect_sid_extra_meta(new_marked)
        assert sid_meta[int(target_sid)] == attributes
        assert re.search(rf"___id___:{int(target_sid)}\b", new_marked) is not None
        return

    parsed = (
        json.loads(new_marked) if extension == ".json" else yaml.safe_load(new_marked)
    )
    node = _find_wrapped_node(parsed, int(target_sid))
    assert node is not None
    assert node[_META_KEY] == attributes
    assert int(node[_ID_KEY]) == int(target_sid)


@pytest.mark.parametrize(
    ("extension", "content"),
    (
        (".json", '{"a": 1, "b": 2}\n'),
        (".yaml", "alpha: 1\nbeta: 2\n"),
        (".py", "a = 1\nb = 2\n"),
    ),
)
def test_edit_attributes_preserves_position(extension: str, content: str) -> None:
    source_path = Path(f"sample{extension}")
    handler = _REGISTRY.resolve(source_path)
    marked = handler.mark(content)
    nodes_before = handler.parse_content(source_path, handler.unmark(marked))
    assert len(nodes_before) >= +2
    second_sid = nodes_before[1].short_id

    new_marked, _ = apply_edit_operation(
        registry=_REGISTRY,
        source_path=source_path,
        marked_text=marked,
        operation=EditOperation(
            kind=EditOperationKind.EDIT_ATTRIBUTES,
            short_id=second_sid,
            attributes={"marker": "keep-position"},
        ),
        tree_is_valid=True,
    )

    nodes_after = handler.parse_content(source_path, handler.unmark(new_marked))
    before = next(n for n in nodes_before if n.short_id == second_sid)
    after = next(n for n in nodes_after if n.short_id == second_sid)
    assert after.short_id == before.short_id
    assert after.content == before.content

    if extension == ".json":
        assert before.attributes["json_pointer"] == after.attributes["json_pointer"]
    elif extension == ".yaml":
        assert before.attributes["key_path"] == after.attributes["key_path"]
    else:
        assert before.attributes["start_line"] == after.attributes["start_line"]
        assert before.attributes["end_line"] == after.attributes["end_line"]
