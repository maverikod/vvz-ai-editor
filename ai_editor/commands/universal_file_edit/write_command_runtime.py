"""Runtime orchestration for universal_file_write (preview + CA commit).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    resolve_session_for_command,
)
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    compare_session_to_origin,
)
from ai_editor.core.file_handlers.diff_support import unified_diff_text

from . import write_command_phases as phases

logger = logging.getLogger(__name__)


def _run_write_preview(
    session: EditSession,
    *,
    write_mode_explicit: bool,
) -> SuccessResult | ErrorResult:
    if session.format_group == FORMAT_TREE_TEMP:
        return phases.tree_temp_preview(session)
    if session.format_group == FORMAT_TEXT:
        return phases.text_preview(session)

    if write_mode_explicit:
        return phases.sidecar_preview(session)
    return phases.sidecar_first_call_preview(session, os.getpid())


def _run_write_commit_ca(
    session: EditSession,
    *,
    project_id: str,
    ca_session_id: str,
    client: Any,
) -> SuccessResult | ErrorResult:
    comparison = compare_session_to_origin(session)
    if comparison.result == CompareResult.EQUAL:
        return SuccessResult(
            data={
                "success": True,
                "phase": "committed",
                "write_mode": "commit",
                "unchanged": True,
                "uploaded": False,
                "has_changes": False,
                "diff": "",
                "session_id": ca_session_id,
                "project_id": project_id,
                "file_path": session.file_path,
            }
        )

    try:
        accepted = client.upload_session_file_content(
            session_id=ca_session_id,
            project_id=project_id,
            file_path=session.file_path,
            content=comparison.exported_bytes,
        )
    except RuntimeError as exc:
        logger.error("universal_file_write upload failed: %s", exc)
        return ErrorResult(
            message=str(exc),
            code=cast(Any, "UPSTREAM_UPLOAD_FAILED"),
            details={"upstream_error": str(exc)},
        )
    except Exception as exc:
        logger.error("universal_file_write upload failed: %s", exc, exc_info=True)
        return ErrorResult(
            message=str(exc),
            code=cast(Any, "UPSTREAM_UPLOAD_FAILED"),
            details={"upstream_error": str(exc)},
        )

    session.abs_path.write_bytes(accepted)
    diff = unified_diff_text(
        comparison.origin_bytes.decode("utf-8"),
        comparison.exported_bytes.decode("utf-8"),
        before_label=str(session.abs_path),
        after_label=str(session.abs_path),
    )
    return SuccessResult(
        data={
            "success": True,
            "phase": "committed",
            "write_mode": "commit",
            "unchanged": False,
            "uploaded": True,
            "has_changes": True,
            "diff": diff,
            "session_id": ca_session_id,
            "project_id": project_id,
            "file_path": session.file_path,
        }
    )


def _sidecar_is_second_call(session: EditSession) -> bool:
    current_pid = os.getpid()
    lock = phases._read_session_lockfile(session)
    return (
        lock is not None
        and lock[0] == current_pid
        and lock[1] == session.session_id
        and phases.lockfile_write_preview_ready(session)
    )


async def run_write_execute(
    *,
    project_id: str,
    session_id: str,
    write_mode: str = "preview",
    write_mode_explicit: bool = False,
    file_path: str = "",
    client: Any,
    **kwargs: Any,
) -> SuccessResult | ErrorResult:
    _ = kwargs
    try:
        session = resolve_session_for_command(
            session_id,
            file_path or None,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "SESSION_FILE_PATH_REQUIRED":
            return error_result_from_make_error(
                make_error(
                    SESSION_FILE_PATH_REQUIRED,
                    "file_path is required when the session has multiple open files",
                    details={"session_id": session_id},
                )
            )
        return error_result_from_make_error(
            make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
        )

    if write_mode == "commit":
        return _run_write_commit_ca(
            session,
            project_id=project_id,
            ca_session_id=session_id,
            client=client,
        )

    if write_mode != "preview":
        return ErrorResult(
            message="write_mode must be 'preview' or 'commit'",
            code=cast(Any, "VALIDATION_ERROR"),
        )

    if (
        session.format_group == FORMAT_SIDECAR
        and not write_mode_explicit
        and _sidecar_is_second_call(session)
    ):
        return _run_write_commit_ca(
            session,
            project_id=project_id,
            ca_session_id=session_id,
            client=client,
        )

    return _run_write_preview(
        session,
        write_mode_explicit=write_mode_explicit,
    )
