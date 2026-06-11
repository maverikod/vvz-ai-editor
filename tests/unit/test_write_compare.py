"""Unit tests for write_compare canonical export comparison (C-012)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    compare_session_to_origin,
)


def _mock_session(
    *,
    format_group: str = FORMAT_TEXT,
    tree_id: str | None = None,
    abs_path: Path | None = None,
    draft_path: Path | None = None,
) -> EditSession:
    core = MagicMock()
    return EditSession(
        session_id="sess-1",
        project_id="proj-1",
        file_path="src/foo.py",
        abs_path=abs_path or Path("/tmp/foo.py"),
        draft_path=draft_path or Path("/tmp/foo.py.draft"),
        lockfile_path=Path("/tmp/foo.py.write"),
        format_group=format_group,
        handler_id=format_group,
        tree_id=tree_id,
        core=core,
    )


def test_compare_text_format_equal(tmp_path: Path) -> None:
    origin = tmp_path / "foo.py"
    draft = tmp_path / "foo.py.draft"
    origin.write_bytes(b"x = 1\n")
    draft.write_text("x = 1\n", encoding="utf-8")
    session = _mock_session(
        format_group=FORMAT_TEXT,
        abs_path=origin,
        draft_path=draft,
    )

    comparison = compare_session_to_origin(session)

    assert comparison.result == CompareResult.EQUAL
    assert comparison.origin_bytes == b"x = 1\n"
    assert comparison.exported_bytes == b"x = 1\n"


def test_compare_text_format_diff(tmp_path: Path) -> None:
    origin = tmp_path / "foo.py"
    draft = tmp_path / "foo.py.draft"
    origin.write_bytes(b"x = 1\n")
    draft.write_text("x = 2\n", encoding="utf-8")
    session = _mock_session(
        format_group=FORMAT_TEXT,
        abs_path=origin,
        draft_path=draft,
    )

    comparison = compare_session_to_origin(session)

    assert comparison.result == CompareResult.DIFF
    assert comparison.origin_bytes == b"x = 1\n"
    assert comparison.exported_bytes == b"x = 2\n"


def test_compare_text_format_empty_draft(tmp_path: Path) -> None:
    origin = tmp_path / "foo.py"
    draft = tmp_path / "foo.py.draft"
    origin.write_bytes(b"")
    draft.write_text("", encoding="utf-8")
    session = _mock_session(
        format_group=FORMAT_TEXT,
        abs_path=origin,
        draft_path=draft,
    )

    comparison = compare_session_to_origin(session)

    assert comparison.result == CompareResult.EQUAL
    assert comparison.origin_bytes == b""
    assert comparison.exported_bytes == b""


def test_compare_sidecar_uses_cst_not_draft(tmp_path: Path) -> None:
    origin = tmp_path / "foo.py"
    canonical = "def foo():\n    return 1\n"
    origin.write_text(canonical, encoding="utf-8")

    mock_draft = MagicMock()
    mock_tree = MagicMock()
    mock_tree.module.code = canonical
    session = _mock_session(
        format_group=FORMAT_SIDECAR,
        tree_id="tree-abc",
        abs_path=origin,
        draft_path=mock_draft,
    )

    with patch(
        "ai_editor.core.cst_tree.tree_builder.get_tree",
        return_value=mock_tree,
    ) as mock_get_tree:
        with patch(
            "ai_editor.core.cst_tree.node_stable_id.strip_inline_node_id_lines_from_source",
            side_effect=lambda code: code,
        ) as mock_strip:
            comparison = compare_session_to_origin(session)

    assert comparison.result == CompareResult.EQUAL
    assert comparison.exported_bytes == canonical.encode("utf-8")
    mock_get_tree.assert_called_once_with("tree-abc")
    mock_strip.assert_called_once_with(canonical)
    mock_draft.read_text.assert_not_called()


def test_compare_sidecar_missing_tree_id_raises() -> None:
    session = _mock_session(format_group=FORMAT_SIDECAR, tree_id=None)
    session.abs_path = MagicMock()
    session.abs_path.read_bytes.return_value = b"x = 1\n"

    with pytest.raises(ValueError, match="Session has no tree_id for sidecar export"):
        compare_session_to_origin(session)


def test_compare_sidecar_missing_tree_raises() -> None:
    session = _mock_session(format_group=FORMAT_SIDECAR, tree_id="missing-tree")
    session.abs_path = MagicMock()
    session.abs_path.read_bytes.return_value = b"x = 1\n"

    with patch(
        "ai_editor.core.cst_tree.tree_builder.get_tree",
        return_value=None,
    ):
        with pytest.raises(
            ValueError,
            match="CST tree 'missing-tree' not found",
        ):
            compare_session_to_origin(session)


def test_compare_tree_temp_uses_serializer(tmp_path: Path) -> None:
    origin = tmp_path / "data.json"
    draft = tmp_path / "data.json.draft"
    serialized = '{"key": "value"}\n'
    origin.write_text(serialized, encoding="utf-8")
    draft.write_text("# draft differs\n", encoding="utf-8")
    session = _mock_session(
        format_group=FORMAT_TREE_TEMP,
        abs_path=origin,
        draft_path=draft,
    )

    with patch(
        "ai_editor.commands.universal_file_edit.tree_temp_write_commit.serialize_tree_temp_session_source",
        return_value=serialized,
    ) as mock_serialize:
        comparison = compare_session_to_origin(session)

    assert comparison.result == CompareResult.EQUAL
    assert comparison.exported_bytes == serialized.encode("utf-8")
    mock_serialize.assert_called_once_with(session)


def test_compare_origin_read_error_propagates() -> None:
    session = _mock_session(format_group=FORMAT_TEXT)
    session.abs_path = MagicMock()
    session.abs_path.read_bytes.side_effect = OSError("origin unreadable")
    session.draft_path = MagicMock()
    session.draft_path.read_text.return_value = "draft"

    with pytest.raises(OSError, match="origin unreadable"):
        compare_session_to_origin(session)
