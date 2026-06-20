"""Runtime orchestration for universal_file_open (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Union, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    FILE_ALREADY_OPEN,
    PARSE_ERROR,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FormatDescriptor,
    write_lockfile_pid,
)
from ai_editor.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
    open_fallback_warning,
)
from ai_editor.commands.universal_file_edit.open_command_draft import (
    resolve_and_create_draft,
)
from ai_editor.commands.universal_file_edit.session import (
    apply_source_mutation,
    build_multi_file_bundle_payload,
    bundle_file_count,
    create_session,
    lookup_ca_session_id,
)
from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    serialize_tree_temp_roots,
)
from ai_editor.core.editor_workspace_paths import (
    ensure_file_subtree,
    ensure_session_directory,
    file_workspace_layout,
    resolve_workspace_root,
)
from ai_editor.core.edit_session.workspace_layout import allocate_edit_subdir
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client


def run_open_execute(
    command: Any,
    **kwargs: Any,
) -> Union[SuccessResult, ErrorResult]:
    """Execute Open Stage (C-010) for one file in workspace mode."""
    ca_session_id = str(kwargs.get("session_id", "")).strip()
    project_id = str(kwargs.get("project_id", "")).strip()
    file_path = str(kwargs.get("file_path", "")).strip()
    create = bool(kwargs.get("create", False))
    initial_content = str(kwargs.get("initial_content", "") or "")

    if project_id:
        existing_sid = lookup_ca_session_id(project_id, file_path)
    else:
        existing_sid = None
    if existing_sid is not None:
        return error_result_from_make_error(
            make_error(
                FILE_ALREADY_OPEN,
                f"File already open in session {existing_sid}: {file_path}",
            )
        )

    client = get_code_analysis_client()

    try:
        if create:
            raw_bytes = client.upload_create_and_lock(
                session_id=ca_session_id,
                project_id=project_id,
                file_path=file_path,
                content=initial_content.encode("utf-8"),
            )
        else:
            raw_bytes = client.lock_file_and_download(
                ca_session_id, project_id, file_path
            )
    except RuntimeError as exc:
        return ErrorResult(message=str(exc), code=cast(Any, "OPEN_ERROR"))

    workspace_root = resolve_workspace_root()
    is_repeat_open = bundle_file_count(ca_session_id) >= 1
    if not is_repeat_open:
        ensure_session_directory(workspace_root, ca_session_id)
    layout = file_workspace_layout(workspace_root, ca_session_id, project_id, file_path)
    ensure_file_subtree(layout)

    paths = allocate_edit_subdir(
        file_subtree_dir=layout.file_subtree_dir,
        origin_filename=layout.origin_path.name,
    )

    layout.origin_path.parent.mkdir(parents=True, exist_ok=True)
    layout.origin_path.write_bytes(raw_bytes)

    descriptor_result = resolve_and_create_draft(
        layout.origin_path, paths.edit_subdir, project_id
    )
    if isinstance(descriptor_result, dict):
        return error_result_from_make_error(descriptor_result)

    descriptor: FormatDescriptor = descriptor_result

    fallback_info = descriptor.__dict__.pop("_fallback_info", None)
    tree_temp_kwargs = descriptor.__dict__.pop("_tree_temp_session_kwargs", None)
    tree_id: Optional[str] = getattr(descriptor, "tree_id", None)

    session_extra: Dict[str, Any] = {}
    if fallback_info is not None:
        session_extra["is_invalid"] = True
        session_extra["fallback_reason"] = fallback_info["fallback_reason"]
        session_extra["original_format_group"] = fallback_info["original_format_group"]

    try:
        if tree_temp_kwargs is not None:
            session = create_session(
                abs_path=paths.origin_path,
                descriptor=descriptor,
                file_path=file_path,
                project_id=project_id,
                ca_session_id=ca_session_id,
                project_root=paths.edit_subdir,
                workspace_session_root=layout.session_dir,
                workspace_file_subtree_root=layout.file_subtree_dir,
                workspace_origin_path=paths.origin_path,
                workspace_edit_subdir=paths.edit_subdir,
                **tree_temp_kwargs,
                **session_extra,
            )
            if session.tree_temp_roots is not None:
                draft_text = serialize_tree_temp_roots(
                    session.handler_id, session.tree_temp_roots
                )
                apply_source_mutation(session, draft_text)
        else:
            session = create_session(
                abs_path=paths.origin_path,
                descriptor=descriptor,
                file_path=file_path,
                project_id=project_id,
                ca_session_id=ca_session_id,
                project_root=paths.edit_subdir,
                tree_id=tree_id,
                workspace_session_root=layout.session_dir,
                workspace_file_subtree_root=layout.file_subtree_dir,
                workspace_origin_path=paths.origin_path,
                workspace_edit_subdir=paths.edit_subdir,
                **session_extra,
            )
    except ValueError as exc:
        if str(exc) == "FILE_ALREADY_IN_SESSION":
            return error_result_from_make_error(
                make_error(
                    FILE_ALREADY_OPEN,
                    f"File already open in session {ca_session_id}: {file_path}",
                )
            )
        if str(exc) == "SESSION_NOT_FOUND":
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {ca_session_id}")
            )
        raise

    write_lockfile_pid(session.core.session_source_path, os.getpid(), ca_session_id)

    data: Dict[str, Any] = {
        "success": True,
        "session_id": ca_session_id,
        "file_path": file_path,
        "format_group": session.format_group,
        "session_dir": str(layout.session_dir),
        "draft_path": str(session.draft_path),
        "available_operations": list(descriptor.available_operations),
    }
    if create:
        data["created"] = True
    if fallback_info is not None:
        reason = fallback_info["fallback_reason"]
        data["is_invalid"] = True
        data["fallback_reason"] = reason
        data["warning"] = open_fallback_warning(reason)
        data["mode_notice"] = mode_notice_text(True, reason)
    else:
        data["mode_notice"] = mode_notice_text(False)

    data["multi_file_bundle"] = build_multi_file_bundle_payload(ca_session_id)
    data["repeat_open"] = is_repeat_open

    return SuccessResult(data=data)
