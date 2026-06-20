"""
Canonical-export comparison for Write Stage (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import EditSession


class CompareResult(str, Enum):
    EQUAL = "equal"
    DIFF = "diff"


@dataclass(frozen=True)
class WriteComparison:
    result: CompareResult
    origin_bytes: bytes
    exported_bytes: bytes


def _is_python_session(session: EditSession) -> bool:
    from ai_editor.core.code_quality.formatter import is_python_source_path

    return is_python_source_path(session.file_path)


def _maybe_format_python_bytes(session: EditSession, exported: bytes) -> bytes:
    from ai_editor.core.code_quality.formatter import format_python_source_text

    if not _is_python_session(session):
        return exported
    text = exported.decode("utf-8")
    formatted, err = format_python_source_text(text)
    if err:
        raise ValueError(f"format_python failed: {err}")
    return formatted.encode("utf-8")


def export_canonical_bytes(
    session: EditSession,
    *,
    format_python: bool = False,
) -> bytes:
    """Format-specific canonical export; optional black pass for Python paths."""
    exported = _export_canonical_bytes(session)
    if format_python:
        return _maybe_format_python_bytes(session, exported)
    return exported


def _export_canonical_bytes(session: EditSession) -> bytes:
    """Format-specific canonical export of Edit Subdirectory state."""
    fg = session.format_group
    if fg == FORMAT_SIDECAR:
        from ai_editor.core.cst_tree.tree_builder import get_tree as get_cst_tree
        from ai_editor.core.cst_tree.node_stable_id import (
            strip_inline_node_id_lines_from_source,
        )

        if not session.tree_id:
            raise ValueError("Session has no tree_id for sidecar export")
        tree = get_cst_tree(session.tree_id)
        if tree is None:
            raise ValueError(f"CST tree {session.tree_id!r} not found")
        code = strip_inline_node_id_lines_from_source(str(tree.module.code))
        return code.encode("utf-8")
    if fg == FORMAT_TREE_TEMP:
        from ai_editor.commands.universal_file_edit.tree_temp_write_commit import (
            serialize_tree_temp_session_source,
        )

        return serialize_tree_temp_session_source(session).encode("utf-8")
    return session.draft_path.read_text(encoding="utf-8").encode("utf-8")


def compare_session_to_origin(
    session: EditSession,
    *,
    format_python: bool = False,
) -> WriteComparison:
    """Byte-compare canonical export vs Origin Snapshot."""
    origin_bytes = session.abs_path.read_bytes()
    exported_bytes = export_canonical_bytes(session, format_python=format_python)
    result = (
        CompareResult.EQUAL if exported_bytes == origin_bytes else CompareResult.DIFF
    )
    return WriteComparison(
        result=result,
        origin_bytes=origin_bytes,
        exported_bytes=exported_bytes,
    )
