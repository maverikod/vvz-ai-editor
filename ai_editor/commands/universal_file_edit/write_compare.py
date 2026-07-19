"""
Canonical-export comparison for Write Stage (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.core.file_handlers.diff_support import unified_diff_text


class CompareResult(str, Enum):
    EQUAL = "equal"
    DIFF = "diff"


class PreviewDiffStatus(str, Enum):
    NO_OP = "no_op"
    CHANGED = "changed"
    VALIDATION_FAILURE = "validation_failure"
    EDIT_FAILURE = "edit_failure"


@dataclass(frozen=True)
class PreviewDiff:
    """Observable evidence for the edit operation represented by a comparison."""

    status: PreviewDiffStatus
    diff: str = ""
    content_changed: bool = False
    applied: bool = False
    diagnostics: tuple[str, ...] = ()
    operation: str = "universal_file_write"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "diff": self.diff,
            "content_changed": self.content_changed,
            "applied": self.applied,
            "diagnostics": list(self.diagnostics),
            "operation": self.operation,
        }


@dataclass(frozen=True)
class WriteComparison:
    result: CompareResult
    origin_bytes: bytes
    exported_bytes: bytes
    preview_diff: PreviewDiff | None = None

    def __post_init__(self) -> None:
        if self.preview_diff is not None:
            return
        changed = self.result == CompareResult.DIFF
        diff = build_preview_diff(self.origin_bytes, self.exported_bytes)
        object.__setattr__(
            self,
            "preview_diff",
            PreviewDiff(
                status=(
                    PreviewDiffStatus.CHANGED
                    if changed
                    else PreviewDiffStatus.NO_OP
                ),
                diff=diff,
                content_changed=changed,
            ),
        )


def build_preview_diff(origin_bytes: bytes, exported_bytes: bytes) -> str:
    """Return the public unified diff for a canonical comparison."""
    if origin_bytes == exported_bytes:
        return ""
    return unified_diff_text(
        origin_bytes.decode("utf-8"),
        exported_bytes.decode("utf-8"),
        before_label="origin",
        after_label="exported",
    )


def failure_preview_diff(
    status: PreviewDiffStatus,
    *,
    diagnostics: tuple[str, ...] | list[str] = (),
    comparison: WriteComparison | None = None,
    operation: str = "universal_file_write",
) -> PreviewDiff:
    """Build failure evidence without claiming that an edit was applied."""
    if status not in (
        PreviewDiffStatus.VALIDATION_FAILURE,
        PreviewDiffStatus.EDIT_FAILURE,
    ):
        raise ValueError(f"Unsupported failure status: {status}")
    return PreviewDiff(
        status=status,
        diff=comparison.preview_diff.diff if comparison else "",
        content_changed=(
            comparison.preview_diff.content_changed if comparison else False
        ),
        diagnostics=tuple(diagnostics),
        operation=operation,
    )


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
