"""Runtime for universal_file_preview (C-016, C-011).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Union, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.preview_config_defaults import get_preview_config_defaults
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
)
from ai_editor.commands.universal_file_edit.session import (
    get_session,
    lookup_ca_session_id,
)
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    acquire_tree_temp_for_open,
)
from ai_editor.commands.universal_file_preview.budget import PreviewBudget
from ai_editor.commands.universal_file_preview.dispatcher import HandlerDispatcher
from ai_editor.commands.universal_file_preview.errors import PreviewError
from ai_editor.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from ai_editor.commands.universal_file_preview.handlers.yaml_handler import (
    YamlFileHandler,
)
from ai_editor.commands.universal_file_preview.navigation import navigate
from ai_editor.commands.universal_file_preview.preview_addressing import (
    check_preview_addressing,
    parse_error_from_focus,
    preview_source_is_parseable,
)
from ai_editor.commands.universal_file_preview.invalid_preview import (
    apply_invalid_line_pagination,
)
from ai_editor.commands.universal_file_preview.response import build_envelope
from ai_editor.commands.universal_file_preview.session import (
    merge_edit_session_into_preview_params,
)
from ai_editor.commands.universal_file_preview.tree_temp_preview_focus import (
    looks_like_sidecar_stable_id,
)
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)

logger = logging.getLogger(__name__)


def _run_preview_on_abs_path(
    command: Any,
    kwargs: dict[str, Any],
    abs_file_path: Path,
) -> Union[SuccessResult, ErrorResult]:
    """Run read-only preview pipeline on an absolute file path."""
    file_path = str(kwargs.get("file_path", "")).strip()
    project_root = Path(kwargs.get("project_root") or abs_file_path.parent).resolve()
    session_origin = str(kwargs.get("_preview_session_origin") or "none")
    edit_session = kwargs.get("_preview_edit_session")

    try:
        dispatcher = HandlerDispatcher()
        handler_result = dispatcher.dispatch(file_path)
        if isinstance(handler_result, PreviewError):
            return ErrorResult(
                message=handler_result.message,
                code=cast(Any, handler_result.code),
                details=handler_result.details or {},
            )
        handler = handler_result

        abs_path_str = str(abs_file_path)
        parseable = preview_source_is_parseable(abs_file_path)
        addressing_err = check_preview_addressing(
            parseable=parseable,
            params=kwargs,
            file_path=file_path,
        )
        if addressing_err is not None:
            return ErrorResult(
                message=addressing_err.message,
                code=cast(Any, addressing_err.code),
                details=addressing_err.details or {},
            )

        nav_kwargs = dict(kwargs)
        nr_probe = kwargs.get("node_ref")
        if isinstance(handler, (JsonFileHandler, YamlFileHandler)) and (
            looks_like_sidecar_stable_id(
                nr_probe if isinstance(nr_probe, str) else None
            )
        ):
            tt_roots_payload = None
            if edit_session is not None and not edit_session.is_invalid:
                tt_roots_payload = edit_session.tree_temp_roots
            if tt_roots_payload is None:
                source_abs_fp = abs_file_path.resolve()
                hid = "json" if isinstance(handler, JsonFileHandler) else "yaml"
                try:
                    tt_roots_payload = acquire_tree_temp_for_open(
                        project_root=abs_file_path.parent.resolve(),
                        source_abs=source_abs_fp,
                        handler_id=hid,
                        raw_source_bytes=source_abs_fp.read_bytes(),
                    ).roots
                except Exception:
                    tt_roots_payload = None
            if tt_roots_payload is not None:
                nav_kwargs["tree_temp_roots"] = tt_roots_payload

        defaults = get_preview_config_defaults()
        budget = PreviewBudget(
            preview_lines=int(
                kwargs.get("preview_lines") or defaults["preview_lines_default"]
            ),
            value_preview_len=int(
                kwargs.get("value_preview_len")
                or defaults["preview_value_preview_len_default"]
            ),
            full_text_max_lines=int(
                kwargs.get("full_text_max_lines")
                or defaults["preview_full_text_max_lines_default"]
            ),
            max_chars=int(
                kwargs.get("max_chars") or defaults["preview_max_chars_default"]
            ),
            preview_offset=int(kwargs.get("preview_offset") or 0),
        )
        nav_kwargs["file_path"] = abs_path_str
        nav_kwargs["project_root"] = project_root
        nav_kwargs["rel_file_path"] = file_path
        nav_kwargs["preview_budget"] = budget

        navigation_result = navigate(handler, nav_kwargs, budget)
        if isinstance(navigation_result, PreviewError):
            return ErrorResult(
                message=navigation_result.message,
                code=cast(Any, navigation_result.code),
                details=navigation_result.details or {},
            )

        envelope = build_envelope(
            navigation_result,
            kwargs.get("selector"),
            session_origin,
        )
        focus_attrs = navigation_result.focus_node.attributes or {}
        if navigation_result.focus_node.is_invalid:
            paginated = apply_invalid_line_pagination(envelope, focus_attrs)
            paginated["mode_notice"] = mode_notice_text(
                True,
                parse_error_from_focus(focus_attrs),
            )
            return SuccessResult(data=paginated)

        envelope["mode_notice"] = mode_notice_text(False)
        return SuccessResult(data=envelope)
    except Exception as exc:
        logger.error("universal_file_preview handler failed: %s", exc, exc_info=True)
        return ErrorResult(message=str(exc), code=cast(Any, "HANDLER_ERROR"))


def run_preview_execute(
    command: Any,
    **kwargs: Any,
) -> Union[SuccessResult, ErrorResult]:
    """Preview workspace copy orchestration (facade delegates here).

    Open-file mode (G-004/T-002): read Edit Subdirectory draft for an active
    edit session. One-shot upstream CA read (G-004/T-003): download_without_lock.
    """
    project_id = str(kwargs.get("project_id", "")).strip()
    file_path = str(kwargs.get("file_path", "")).strip()
    ca_session_id = str(kwargs.get("session_id", "")).strip()

    open_owner = lookup_ca_session_id(project_id, file_path)
    if open_owner is not None and not ca_session_id:
        return ErrorResult(
            message=(
                "File is open in editor workspace; pass session_id to preview "
                "the workspace draft"
            ),
            code=cast(Any, "OPEN_FILE_USE_WORKSPACE_PREVIEW"),
            details={
                "project_id": project_id,
                "file_path": file_path,
                "session_id": open_owner,
            },
        )

    if open_owner is None:
        if ca_session_id:
            guard = SessionGuard(get_code_analysis_client())
            decision = guard.check(OperationKind.PREVIEW, ca_session_id)
            if decision == GuardDecision.REJECT:
                return ErrorResult(
                    message=f"CA session not found or invalid: {ca_session_id}",
                    code=cast(Any, "SESSION_NOT_FOUND"),
                )

        client = get_code_analysis_client()
        try:
            raw_bytes = client.download_without_lock(
                project_id=project_id,
                file_path=file_path,
            )
        except RuntimeError as exc:
            return ErrorResult(
                message=str(exc),
                code=cast(Any, "UPSTREAM_ERROR"),
            )

        suffix = Path(file_path).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw_bytes)
            ephemeral_abs = Path(tmp.name)

        try:
            preview_kwargs = dict(kwargs)
            preview_kwargs["_preview_abs_path"] = str(ephemeral_abs)
            preview_kwargs["project_root"] = str(ephemeral_abs.parent.resolve())
            preview_kwargs["_preview_session_origin"] = "none"
            return _run_preview_on_abs_path(
                command,
                preview_kwargs,
                ephemeral_abs,
            )
        finally:
            ephemeral_abs.unlink(missing_ok=True)

    try:
        edit_session = get_session(ca_session_id, file_path=file_path or None)
    except ValueError as exc:
        msg = str(exc)
        if msg == "SESSION_FILE_PATH_REQUIRED":
            return error_result_from_make_error(
                make_error(
                    SESSION_NOT_FOUND,
                    "file_path is required when the session has multiple open files",
                )
            )
        return error_result_from_make_error(
            make_error(SESSION_NOT_FOUND, f"Unknown session: {ca_session_id}")
        )

    if str(edit_session.project_id) != project_id:
        return ErrorResult(
            message="session_id does not match project_id",
            code=cast(Any, "VALIDATION_ERROR"),
        )

    merged = merge_edit_session_into_preview_params(kwargs)
    if isinstance(merged, PreviewError):
        return ErrorResult(
            message=merged.message,
            code=cast(Any, merged.code),
            details=merged.details or {},
        )
    kwargs = merged

    abs_file_path = Path(
        str(kwargs.get("_preview_abs_path") or edit_session.draft_path)
    )
    workspace_edit_subdir = getattr(edit_session, "workspace_edit_subdir", None)
    if workspace_edit_subdir:
        workspace_edit_root = Path(str(workspace_edit_subdir)).resolve()
    else:
        workspace_edit_root = abs_file_path.parent.resolve()

    open_kwargs = dict(kwargs)
    open_kwargs["project_root"] = str(workspace_edit_root)
    open_kwargs["_preview_session_origin"] = "caller_owned"
    open_kwargs["_preview_edit_session"] = edit_session

    return _run_preview_on_abs_path(command, open_kwargs, abs_file_path)
