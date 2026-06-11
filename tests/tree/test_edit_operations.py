"""Unit tests for ai_editor.tree.edit_operations (G-004)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_editor.tree.contracts import NodeId, validate_short_id
from ai_editor.tree.edit_operations import (
    EditOperation,
    EditOperationError,
    EditOperationKind,
    apply_edit_operation,
)
from ai_editor.tree.handler_registry import HandlerRegistry

_REGISTRY = HandlerRegistry.default_registry()

_FORMAT_SAMPLES: tuple[tuple[str, str, str], ...] = (
    (".txt", "hello\n", "updated"),
    (".md", "# Title\n\nbody\n", "updated"),
    (".yaml", "key: value\n", "key: updated\n"),
    (".json", '{"a": 1}\n', "2"),
    (".py", "x = 1\n", "x = 2"),
)


def test_apply_edit_operation_rejects_invalid_tree() -> None:
    with pytest.raises(EditOperationError, match="tree is invalid"):
        apply_edit_operation(
            registry=_REGISTRY,
            source_path=Path("sample.txt"),
            marked_text="1:hello\n",
            operation=EditOperation(kind=EditOperationKind.DELETE, short_id=NodeId(1)),
            tree_is_valid=False,
        )


def test_insert_returns_incremented_next_free() -> None:
    handler = _REGISTRY.resolve(Path("sample.txt"))
    marked = handler.mark("hello\n")
    _, new_next_free = apply_edit_operation(
        registry=_REGISTRY,
        source_path=Path("sample.txt"),
        marked_text=marked,
        operation=EditOperation(
            kind=EditOperationKind.INSERT,
            anchor_short_id=NodeId(1),
            position="after",
            new_content="world",
            next_free=2,
        ),
        tree_is_valid=True,
    )
    assert new_next_free == 3


def test_validate_short_id_rejects_zero() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        validate_short_id(0)


def test_validate_short_id_rejects_bool() -> None:
    with pytest.raises(ValueError, match="must be int"):
        validate_short_id(True)


def test_apply_edit_operation_rejects_zero_short_id() -> None:
    with pytest.raises(EditOperationError, match="short_id"):
        apply_edit_operation(
            registry=_REGISTRY,
            source_path=Path("sample.txt"),
            marked_text="1:hello\n",
            operation=EditOperation(kind=EditOperationKind.DELETE, short_id=NodeId(0)),
            tree_is_valid=True,
        )


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


@pytest.mark.parametrize(("extension", "content", "new_content"), _FORMAT_SAMPLES)
def test_handler_smoke_replace_via_registry(
    extension: str, content: str, new_content: str
) -> None:
    source_path = Path(f"sample{extension}")
    handler = _REGISTRY.resolve(source_path)
    marked = handler.mark(content)
    target_sid = _target_short_id(handler, source_path, content, marked)
    new_marked, _ = apply_edit_operation(
        registry=_REGISTRY,
        source_path=source_path,
        marked_text=marked,
        operation=EditOperation(
            kind=EditOperationKind.REPLACE,
            short_id=target_sid,
            new_content=new_content,
        ),
        tree_is_valid=True,
    )
    assert new_marked != marked
    assert handler.unmark(new_marked)
