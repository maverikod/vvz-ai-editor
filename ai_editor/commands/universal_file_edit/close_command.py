"""
UniversalFileCloseCommand: ends an editing session with group-specific cleanup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
from typing import Any, Dict, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.close_command_cleanup import (
    close_sidecar,
    close_tree_temp_or_text,
)
from ai_editor.commands.universal_file_edit.errors import (
    MODIFIED_NOT_WRITTEN,
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    VALIDATION_ERROR,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import FORMAT_SIDECAR
from ai_editor.commands.universal_file_edit.project_scope import project_scope_error
from ai_editor.commands.universal_file_edit.session import (
    list_bundle_file_paths,
    release_session,
    resolve_session_for_command,
)
from ai_editor.commands.universal_file_edit.close_command_metadata import (
    get_universal_file_close_metadata,
)
from ai_editor.commands.universal_file_edit.write_command_runtime import (
    run_write_execute,
)
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    compare_session_to_origin,
)
from ai_editor.core.edit_session.workspace_layout import remove_file_subtree
from ai_editor.core.editor_workspace_paths import (
    file_workspace_layout,
    resolve_workspace_root,
)
from ai_editor.core.host_filesystem import (
    HostFileOperationError,
    handle_host_file_error,
)
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)

logger = logging.getLogger(__name__)


class UniversalFileCloseCommand(BaseMCPCommand):
    """MCP command that ends a session with Close Stage workspace cleanup.

    Sidecar: verify checksum; rebuild on mismatch; never delete sidecar.
    Tree-temp: sha256 compare draft vs original; delete or rebuild draft; free tree.
    Text: delete draft unconditionally.
    Multi-file: requires file_path when N>1; response includes remaining_open_files.
    """

    name = "universal_file_close"

    version = "1.0.0"

    descr = "End a universal file edit session with format-group-specific cleanup."

    category = "file_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name.

        Returns:
            MCP command name string.
        """
        return "universal_file_close"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and session_id.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Required for CA unlock (C-023) and "
                        "workspace path resolution."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "CA session id (required; same id as session_create on "
                        "Code Analysis Server)."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path. Required when the CA session has "
                        "more than one open file (see multi_file_bundle from open). "
                        "Optional when exactly one file is open."
                    ),
                },
                "write_before_close": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Controls close when the file has unsaved edits (modified "
                        "but not committed). true: run the full write/commit "
                        "sequence (lock-then-transfer for a new file) before "
                        "closing. false (default): reject the close with "
                        "MODIFIED_NOT_WRITTEN so edits are never silently "
                        "discarded. Ignored when the file is unmodified."
                    ),
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileCloseCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_close.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_close_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        file_path: Optional[str] = None,
        write_before_close: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the close command.

        Args:
            project_id: Required by schema; used for CA unlock and workspace paths.
                An empty value is rejected with VALIDATION_ERROR, exactly as
                universal_file_open rejects it — a declared-required parameter is
                validated, not silently defaulted.
            session_id: CA session identifier.
            file_path: Project-relative path when the session holds multiple files.
                Omit it when exactly one file is open; an explicitly EMPTY string
                is a malformed path and is rejected with VALIDATION_ERROR rather
                than silently treated as omitted.
            write_before_close: How to close a file that still holds unsaved edits.
                ``True`` runs the full write/commit sequence first; ``False``
                (default) refuses the close with MODIFIED_NOT_WRITTEN so edits are
                never silently discarded. Ignored when the file is unmodified.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with cleanup details, or ErrorResult on invalid
            parameters, session not found, or a modified-but-unwritten file when
            ``write_before_close`` is ``False``.
        """
        _ = kwargs
        ca_session_id = str(session_id or "").strip()
        pid = str(project_id or "").strip()
        if not ca_session_id:
            return ErrorResult(
                message="session_id is required for universal_file_close",
                code=cast(Any, "SESSION_REJECTED"),
            )
        invalid = self._validate_declared_params(project_id, ca_session_id, file_path)
        if invalid is not None:
            return invalid
        guard = SessionGuard(get_code_analysis_client())
        try:
            decision = guard.check(OperationKind.CLOSE, ca_session_id)
        except HostFileOperationError as exc:
            return ErrorResult(
                message=str(exc),
                code=cast(Any, exc.code or "HOST_FILE_OPERATION_ERROR"),
                details=exc.details,
            )
        if decision == GuardDecision.REJECT:
            return ErrorResult(
                message="session_id is required for universal_file_close",
                code=cast(Any, "SESSION_REJECTED"),
            )
        try:
            session = resolve_session_for_command(
                ca_session_id,
                file_path if file_path is not None else None,
            )
        except ValueError as exc:
            msg = str(exc)
            if msg == "SESSION_FILE_PATH_REQUIRED":
                return error_result_from_make_error(
                    make_error(
                        SESSION_FILE_PATH_REQUIRED,
                        "file_path is required when the session has multiple open files",
                        details={"session_id": ca_session_id},
                    )
                )
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {ca_session_id}")
            )
        client = get_code_analysis_client()

        # R5: handle unsaved edits before cleanup. The guard applies to EVERY
        # session that holds edits, with no format-group or persistence carve-out.
        # It previously skipped tree-temp sessions and every create=true draft
        # that had not been committed yet (persisted_on_ca=False), which is
        # exactly the combination the documented promise rules out: a real edit,
        # confirmed by universal_file_write as has_changes=true, was discarded by
        # a default close that reported success. MODIFIED_NOT_WRITTEN exists so
        # "edits are never silently discarded"; the only escape is the declared
        # write_before_close=true, which commits first and then closes.
        if session.modified:
            try:
                comparison = compare_session_to_origin(session)
            except ValueError:
                comparison = None
            if comparison is not None and comparison.result == CompareResult.EQUAL:
                session.modified = False
            elif not write_before_close:
                return error_result_from_make_error(
                    make_error(
                        MODIFIED_NOT_WRITTEN,
                        (
                            "File has unsaved changes; commit with "
                            "universal_file_write or pass write_before_close=true "
                            "to write on close"
                        ),
                        details={
                            "session_id": ca_session_id,
                            "file_path": session.file_path,
                        },
                    )
                )
            else:
                write_result = await run_write_execute(
                    project_id=pid,
                    session_id=ca_session_id,
                    write_mode="commit",
                    write_mode_explicit=True,
                    file_path=session.file_path,
                    client=client,
                )
                if isinstance(write_result, ErrorResult):
                    # Do not close on write failure: the caller keeps the session to
                    # retry or to discard explicitly.
                    return write_result
        is_last_file = len(list_bundle_file_paths(ca_session_id)) == 1
        # R4: release the CA lock only when the file exists on CA. A new file that
        # was opened locally (R1) and never committed holds no CA lock, so there
        # is nothing to release — closing just discards the local draft.
        if session.persisted_on_ca:
            unlock_ok = client.unlock_session_file(
                session_id=ca_session_id,
                project_id=pid,
                file_path=session.file_path,
            )
            if not unlock_ok:
                logger.info(
                    "close unlock best-effort failed for %s/%s",
                    ca_session_id,
                    session.file_path,
                )
        else:
            unlock_ok = False
        fg = session.format_group
        payload: Dict[str, Any] = {"success": True, "draft_rebuilt": False}
        try:
            if fg == FORMAT_SIDECAR:
                payload = close_sidecar(session)
            else:
                payload = close_tree_temp_or_text(session)
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "close format cleanup skipped for %s/%s: %s",
                ca_session_id,
                session.file_path,
                exc,
            )
        try:
            session.core.close()
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "close core cleanup skipped for %s/%s: %s",
                ca_session_id,
                session.file_path,
                exc,
            )
        finally:
            release_session(ca_session_id, session.file_path)
        remaining = list_bundle_file_paths(ca_session_id)
        payload["closed_file_path"] = session.file_path
        payload["remaining_open_files"] = remaining
        payload["session_retained"] = len(remaining) > 0
        workspace_root = resolve_workspace_root()
        layout = file_workspace_layout(
            workspace_root,
            ca_session_id,
            pid,
            session.file_path,
        )
        workspace_subtree_removed = False
        try:
            if layout.file_subtree_dir.is_dir():
                remove_file_subtree(file_subtree_dir=layout.file_subtree_dir)
                workspace_subtree_removed = True
        except (FileNotFoundError, OSError) as exc:
            host_exc = handle_host_file_error(
                file_name=str(layout.file_subtree_dir),
                caller_file=__file__,
                method_name="UniversalFileCloseCommand:remove_file_subtree",
                exc=exc,
                logger=logger,
            )
            payload["workspace_subtree_cleanup_error"] = host_exc.details
        session_dir_removed = False
        try:
            if is_last_file and layout.session_dir.is_dir():
                shutil.rmtree(layout.session_dir)
                session_dir_removed = True
        except (FileNotFoundError, OSError) as exc:
            host_exc = handle_host_file_error(
                file_name=str(layout.session_dir),
                caller_file=__file__,
                method_name="UniversalFileCloseCommand:rmtree_session_dir",
                exc=exc,
                logger=logger,
            )
            payload["session_dir_cleanup_error"] = host_exc.details
        payload["session_id"] = ca_session_id
        payload["project_id"] = pid
        payload["file_path"] = session.file_path
        payload["unlock_ok"] = unlock_ok
        payload["workspace_subtree_removed"] = workspace_subtree_removed
        payload["session_dir_removed"] = session_dir_removed
        return SuccessResult(data=payload)

    def _validate_declared_params(
        self,
        project_id: Any,
        session_id: str,
        file_path: Optional[str],
    ) -> Optional[ErrorResult]:
        """Reject declared parameters whose value is present but unusable.

        ``project_id`` is delegated to the shared ``project_scope`` guard, the
        one mechanism the session-scoped commands use, so close answers an empty
        or foreign project id with the same VALIDATION_ERROR and the same
        messages as edit/write/search/node_at_line — close was tearing the
        session down regardless of what it was given. ``file_path`` is optional,
        so being absent is legal, but an explicitly EMPTY string is a malformed
        project-relative path, not a request to guess the only open file.

        Args:
            project_id: Raw project UUID from the request.
            session_id: Stripped CA session id the close was addressed to.
            file_path: Raw file_path from the request; ``None`` when omitted.

        Returns:
            An ErrorResult when a declared parameter is unusable, else ``None``.
        """
        if file_path is not None and not str(file_path).strip():
            return error_result_from_make_error(
                make_error(
                    VALIDATION_ERROR,
                    "file_path must be a non-empty project-relative path when given",
                    details={"field": "file_path"},
                )
            )
        return project_scope_error(project_id, session_id, file_path or "")
