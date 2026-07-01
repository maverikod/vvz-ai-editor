"""Runtime orchestration for universal_file_write (preview + CA commit).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    WRITE_FAILED,
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
from ai_editor.core.file_validation.pre_write_pipeline import (
    validate_before_promote,
    validation_error_result,
)
from ai_editor.core.host_filesystem import (
    HostFileOperationError,
    guard_host_file_operation,
)
from ai_editor.commands.universal_file_edit.write_command_extras import (
    verify_ca_readback,
)
from ai_editor.core.file_handlers.diff_support import unified_diff_text

from . import write_command_phases as phases

logger = logging.getLogger(__name__)


def _run_write_preview(
    session: EditSession,
    *,
    write_mode_explicit: bool,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    if session.format_group == FORMAT_TREE_TEMP:
        return phases.tree_temp_preview(session, format_python=format_python)
    if session.format_group == FORMAT_TEXT:
        return phases.text_preview(session, format_python=format_python)

    if write_mode_explicit:
        return phases.sidecar_preview(session, format_python=format_python)
    return phases.sidecar_first_call_preview(
        session,
        os.getpid(),
        format_python=format_python,
    )


def _commit_response_data(
    *,
    session: EditSession,
    project_id: str,
    ca_session_id: str,
    comparison: Any,
    uploaded: bool,
    verify_after_upload: bool,
    format_python: bool,
    client: Any,
) -> Dict[str, Any]:
    diff = ""
    if comparison.result != CompareResult.EQUAL:
        diff = unified_diff_text(
            comparison.origin_bytes.decode("utf-8"),
            comparison.exported_bytes.decode("utf-8"),
            before_label=str(session.abs_path),
            after_label=str(session.abs_path),
        )
    data: Dict[str, Any] = {
        "success": True,
        "phase": "committed",
        "write_mode": "commit",
        "unchanged": comparison.result == CompareResult.EQUAL,
        "uploaded": uploaded,
        "has_changes": comparison.result != CompareResult.EQUAL,
        "diff": diff,
        "session_id": ca_session_id,
        "project_id": project_id,
        "file_path": session.file_path,
        "format_python": format_python,
    }
    if verify_after_upload and uploaded:
        data["ca_verify"] = verify_ca_readback(
            client,
            project_id=project_id,
            file_path=session.file_path,
            expected_bytes=comparison.exported_bytes,
        )
    return data


def _run_write_commit_ca(
    session: EditSession,
    *,
    project_id: str,
    ca_session_id: str,
    client: Any,
    format_python: bool = False,
    verify_after_upload: bool = False,
) -> SuccessResult | ErrorResult:
    try:
        comparison = compare_session_to_origin(session, format_python=format_python)
    except ValueError as exc:
        return error_result_from_make_error(make_error(WRITE_FAILED, str(exc)))
    # R3: a new file (create=true, never committed) is not yet on CA, so the
    # local origin snapshot is not a CA baseline. It must always be persisted on
    # commit even when no edit changed it since open. An already-persisted file
    # with no changes is a true no-op and skips the upload.
    is_new_file = not session.persisted_on_ca
    if comparison.result == CompareResult.EQUAL and not is_new_file:
        session.modified = False
        return SuccessResult(
            data=_commit_response_data(
                session=session,
                project_id=project_id,
                ca_session_id=ca_session_id,
                comparison=comparison,
                uploaded=False,
                verify_after_upload=False,
                format_python=format_python,
                client=client,
            )
        )

    source_text = comparison.exported_bytes.decode("utf-8")
    project_root = session.core.project_root
    if project_root is None:
        from ai_editor.commands.universal_file_edit.edit_draft_path_utils import (
            project_root_near,
        )

        try:
            project_root = project_root_near(session.abs_path)
        except ValueError:
            project_root = None
    validation = validate_before_promote(
        session.handler_id,
        source_code=source_text,
        target_path=session.abs_path,
        project_root=project_root,
    )
    if validation.temp_path is not None:
        validation.temp_path.unlink(missing_ok=True)
    if not validation.success:
        return validation_error_result(
            error_message=validation.error_message or "Validation failed",
            quality_results=validation.quality_results,
            handler_results=validation.handler_results,
        )

    try:
        if is_new_file:
            # R3 lock-then-transfer: the CA lock row is created before the file is
            # written. upload_create_and_lock saves under lock_mode="full" (lock
            # precedes the save) and registers the file, so a new file never
            # depends on the watcher having pre-indexed the row. The old failure
            # mode "file not found in project index" cannot occur here.
            accepted = client.upload_create_and_lock(
                session_id=ca_session_id,
                project_id=project_id,
                file_path=session.file_path,
                content=comparison.exported_bytes,
            )
        else:
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

    # The file now exists on CA under a session lock; subsequent commits use the
    # update-existing path and close (R4) will release the lock.
    session.persisted_on_ca = True
    try:
        guard_host_file_operation(
            file_name=session.abs_path,
            caller_file=__file__,
            method_name="_run_write_commit_ca:write_origin_snapshot",
            operation=lambda: session.abs_path.write_bytes(accepted),
            logger=logger,
        )
    except HostFileOperationError as exc:
        return ErrorResult(
            message=str(exc),
            code=cast(Any, exc.code or "HOST_FILE_OPERATION_ERROR"),
            details=exc.details,
        )
    session.modified = False
    return SuccessResult(
        data=_commit_response_data(
            session=session,
            project_id=project_id,
            ca_session_id=ca_session_id,
            comparison=comparison,
            uploaded=True,
            verify_after_upload=verify_after_upload,
            format_python=format_python,
            client=client,
        )
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
    format_python = bool(kwargs.get("format_python", False))
    verify_after_upload = bool(kwargs.get("verify_after_upload", False))
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
            format_python=format_python,
            verify_after_upload=verify_after_upload,
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
            format_python=format_python,
            verify_after_upload=verify_after_upload,
        )

    return _run_write_preview(
        session,
        write_mode_explicit=write_mode_explicit,
        format_python=format_python,
    )
