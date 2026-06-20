"""Write phase helpers for universal_file_write (preview diffs vs origin).

Restored from pre-thin-server write_command; commit uses CA upload in runtime.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    LOCKFILE_WRITE_PREVIEW_READY,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.write_compare import export_canonical_bytes
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
    """Canonical export as text (no optional black pass)."""
    return export_canonical_bytes(session).decode("utf-8")


def preview_export_vs_origin(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    """Unified diff: origin snapshot (last write) vs canonical session export."""
    try:
        code = export_canonical_bytes(
            session,
            format_python=format_python,
        ).decode("utf-8")
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


def tree_temp_preview(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session, format_python=format_python)


def text_preview(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session, format_python=format_python)


def sidecar_preview(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session, format_python=format_python)


def sidecar_first_call_preview(
    session: EditSession,
    current_pid: int,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    """Sidecar legacy two-phase: preview diff + session lockfile (no disk write)."""
    result = preview_export_vs_origin(session, format_python=format_python)
    if isinstance(result, ErrorResult):
        return result
    write_session_lockfile(
        session,
        current_pid,
        write_preview_ready=True,
    )
    return result
