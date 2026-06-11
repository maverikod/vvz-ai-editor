"""
Unit tests for EditSession apply_tree_operation / edit_operations_adapter ({h008}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ai_editor.core.edit_session.edit_session import (
    EditSession,
    SessionTreeValidity,
)
from ai_editor.core.tree_lifecycle.builder import TreeBuilder
from ai_editor.core.tree_lifecycle.checksum import compute_content_checksum
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.contracts import NodeId
from ai_editor.tree.edit_operations import EditOperation, EditOperationKind
from ai_editor.tree.handler_registry import HandlerRegistry


def _setup_valid_json(tmp_path: Path) -> tuple[Path, Path, str]:
    rel_path = "nested/demo.json"
    source_abs = tmp_path / rel_path
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    content = '{"counter": 1, "tail": 9}\n'
    source_abs.write_text(content, encoding="utf-8")
    TreeBuilder.build(
        content=content,
        source_abs=source_abs,
        file_path=rel_path,
        content_checksum=compute_content_checksum(content),
    )
    return tmp_path, source_abs, rel_path


def _scalar_short_id(source_abs: Path, file_path: str, field: str) -> NodeId:
    handler = HandlerRegistry.default_registry().resolve(source_abs)
    nodes = handler.parse_content(
        Path(file_path), source_abs.read_text(encoding="utf-8")
    )
    target_ptr = f"/{field}"
    for node in nodes:
        if node.attributes.get("json_pointer") == target_ptr:
            return NodeId(int(node.short_id))
    raise AssertionError(f"short_id for field {field!r} not found among {nodes!r}")


def test_apply_tree_operation_replace_updates_source_and_commits(
    tmp_path: Path,
) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        assert session.tree_validity == SessionTreeValidity.VALID
        initial_commits = len(session.session_repo.log())
        counter_sid = _scalar_short_id(source_abs, rel, "counter")

        session.apply_tree_operation(
            EditOperation(
                kind=EditOperationKind.REPLACE,
                short_id=counter_sid,
                new_content="42",
            )
        )

        assert len(session.session_repo.log()) == initial_commits + 1
        payload = json.loads(session.session_source_path.read_text(encoding="utf-8"))
        assert payload["counter"] == 42
        tree_text = session.session_tree_path.read_text(encoding="utf-8")
        assert '"42"' in tree_text or "42" in tree_text
    finally:
        session.close()


def test_apply_tree_operation_insert_assigns_new_short_id(
    tmp_path: Path,
) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        sections_before = parse_tree_file(
            session.session_tree_path.read_text(encoding="utf-8")
        )
        next_free_before = sections_before.map.next_free
        tail_sid = _scalar_short_id(source_abs, rel, "tail")

        session.apply_tree_operation(
            EditOperation(
                kind=EditOperationKind.INSERT,
                anchor_short_id=tail_sid,
                position="after",
                new_content='{"extra": 100}',
            )
        )

        sections_after = parse_tree_file(
            session.session_tree_path.read_text(encoding="utf-8")
        )
        assert sections_after.map.next_free == next_free_before + 1
        new_ids = {entry.short_id for entry in sections_after.map.entries}
        assert next_free_before in new_ids
        payload = json.loads(session.session_source_path.read_text(encoding="utf-8"))
        assert payload["extra"] == 100
        marked = sections_after.tree
        assert re.search(rf'"___id___"\s*:\s*{next_free_before}', marked)
    finally:
        session.close()


def test_apply_tree_operation_delete_by_short_id(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        tail_sid = _scalar_short_id(source_abs, rel, "tail")
        session.apply_tree_operation(
            EditOperation(
                kind=EditOperationKind.DELETE,
                short_id=tail_sid,
            )
        )
        payload = json.loads(session.session_source_path.read_text(encoding="utf-8"))
        assert "tail" not in payload
        assert payload["counter"] == 1
    finally:
        session.close()


def test_apply_tree_operation_move_reorders_object_keys(tmp_path: Path) -> None:
    root, source_abs, rel = _setup_valid_json(tmp_path)
    session = EditSession.open(
        source_abs=source_abs,
        project_root=root,
        file_path=rel,
    )
    try:
        counter_sid = _scalar_short_id(source_abs, rel, "counter")
        tail_sid = _scalar_short_id(source_abs, rel, "tail")
        session.apply_tree_operation(
            EditOperation(
                kind=EditOperationKind.MOVE,
                short_id=tail_sid,
                anchor_short_id=counter_sid,
                position="before",
            )
        )
        payload = json.loads(session.session_source_path.read_text(encoding="utf-8"))
        assert list(payload.keys()) == ["tail", "counter"]
        assert payload["tail"] == 9
        assert payload["counter"] == 1
    finally:
        session.close()


def test_unresolvable_node_ref_raises_in_batch_mapper(tmp_path: Path) -> None:
    from ai_editor.core.edit_session.edit_operations_adapter import (
        resolve_node_ref_to_short_id,
    )

    _, source_abs, _rel_path = _setup_valid_json(tmp_path)
    sidecar = (
        HandlerRegistry.default_registry().resolve(source_abs).sidecar_path(source_abs)
    )
    sections = parse_tree_file(sidecar.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="not found"):
        resolve_node_ref_to_short_id("not-an-int", sections, handler_id="json")
