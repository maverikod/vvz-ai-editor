"""Write phase helpers for universal_file_write (preview diffs vs origin).

Restored from pre-thin-server write_command; commit uses CA upload in runtime.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
    LOCKFILE_WRITE_PREVIEW_READY,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.tree_temp_write_commit import (
    build_tree_temp_preview_text,
    serialize_tree_temp_session_source,
)
from ai_editor.core.cst_tree.node_stable_id import (
    strip_inline_node_id_lines_from_source,
)
from ai_editor.core.cst_tree.tree_builder import get_tree as get_cst_tree
from ai_editor.core.file_handlers.diff_support import unified_diff_text


def _origin_text(session: EditSession) -> str:
    if session.abs_path.is_file():
        return session.abs_path.read_text(encoding="utf-8")
    return ""


def _preview_success(diff: str) -> SuccessResult:
    has_changes = bool(diff.strip())
    return SuccessResult(
        data={
            "success": True,
            "phase": "preview",
            "write_mode": "preview",
            "has_changes": has_changes,
            "unchanged": not has_changes,
            "diff": diff,
        }
    )


def _read_session_lockfile(session: EditSession) -> Optional[Tuple[int, str]]:
    lf = session.lockfile_path
    try:
        parts = lf.read_text(encoding="utf-8").strip().splitlines()
        if len(parts) < 2:
            return None
        return int(parts[0]), parts[1].strip()
    except (OSError, ValueError):
        return None


def lockfile_write_preview_ready(session: EditSession) -> bool:
    lf = session.lockfile_path
    try:
        parts = lf.read_text(encoding="utf-8").strip().splitlines()
        return len(parts) >= 3 and parts[2].strip() == LOCKFILE_WRITE_PREVIEW_READY
    except OSError:
        return False


def write_session_lockfile(
    session: EditSession,
    pid: int,
    *,
    write_preview_ready: bool = False,
) -> None:
    lf = session.lockfile_path
    tmp = Path(f"{lf}.tmp")
    body = f"{pid}\n{session.session_id}"
    if write_preview_ready:
        body = f"{body}\n{LOCKFILE_WRITE_PREVIEW_READY}"
    lf.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(lf)


def generate_code(session: EditSession) -> str:
    fg = session.format_group
    if fg == FORMAT_SIDECAR:
        tid = session.tree_id
        if not tid:
            raise ValueError("Session has no registered tree id for sidecar format.")
        tree = get_cst_tree(tid)
        if tree is None:
            raise ValueError(f"CST tree {tid!r} not found in memory.")
        return cast(
            str,
            strip_inline_node_id_lines_from_source(str(tree.module.code)),
        )
    if fg == FORMAT_TREE_TEMP:
        return serialize_tree_temp_session_source(session)
    return str(session.draft_path.read_text(encoding="utf-8"))


def preview_export_vs_origin(session: EditSession) -> SuccessResult | ErrorResult:
    """Unified diff: origin snapshot (last write) vs canonical session export."""
    try:
        code = generate_code(session)
    except Exception as exc:
        return error_result_from_make_error(
            make_error(WRITE_FAILED, f"Preview generation failed: {exc}")
        )
    original = _origin_text(session)
    diff = unified_diff_text(
        original,
        code,
        before_label=str(session.abs_path),
        after_label=str(session.abs_path),
    )
    return _preview_success(diff)


def tree_temp_preview(session: EditSession) -> SuccessResult | ErrorResult:
    try:
        code = build_tree_temp_preview_text(
            abs_path=session.abs_path,
            session=session,
        )
    except Exception as exc:
        return error_result_from_make_error(
            make_error(WRITE_FAILED, f"Preview generation failed: {exc}")
        )
    original = _origin_text(session)
    diff = unified_diff_text(
        original,
        code,
        before_label=str(session.abs_path),
        after_label=str(session.abs_path),
    )
    return _preview_success(diff)


def text_preview(session: EditSession) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session)


def sidecar_preview(session: EditSession) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session)


def sidecar_first_call_preview(
    session: EditSession,
    current_pid: int,
) -> SuccessResult | ErrorResult:
    """Sidecar legacy two-phase: preview diff + session lockfile (no disk write)."""
    try:
        code = generate_code(session)
    except Exception as exc:
        return error_result_from_make_error(
            make_error(WRITE_FAILED, f"Preview generation failed: {exc}")
        )
    original = _origin_text(session)
    diff = unified_diff_text(
        original,
        code,
        before_label=str(session.abs_path),
        after_label=str(session.abs_path),
    )
    write_session_lockfile(
        session,
        current_pid,
        write_preview_ready=True,
    )
    return _preview_success(diff)
