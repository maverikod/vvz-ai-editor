"""UniversalFileWriteCommand facade (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import CommandResult, ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.session import resolve_session_for_command
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    compare_session_to_origin,
)
from ai_editor.commands.universal_file_edit.write_command_metadata import (
    get_universal_file_write_metadata,
)
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)

logger = logging.getLogger(__name__)


class UniversalFileWriteCommand(BaseMCPCommand):
    """Compare edit workspace to origin; upload when changed (C-012)."""

    name = "universal_file_write"
    version = "1.0.0"
    descr = "Compare edit workspace to origin and upload if changed"
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def get_name() -> str:
        return "universal_file_write"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path. Required when the CA session has "
                        "more than one open file (see multi_file_bundle from open). "
                        "Optional when exactly one file is open."
                    ),
                },
                "write_mode": {
                    "type": "string",
                    "enum": ["preview", "commit"],
                    "default": "commit",
                    "description": (
                        "commit: compare canonical export to origin and upload if "
                        "changed. preview: not implemented in this step."
                    ),
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        validated: Dict[str, Any] = super().validate_params(params)
        return validated

    @classmethod
    def metadata(cls: Type["UniversalFileWriteCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_universal_file_write_metadata(cls))

    async def execute(self, **kwargs: Any) -> CommandResult:  # type: ignore
        project_id = str(kwargs.get("project_id", ""))
        ca_session_id = str(kwargs.get("session_id", ""))
        file_path = str(kwargs.get("file_path", ""))
        write_mode = str(kwargs.get("write_mode", "commit"))

        guard = SessionGuard(get_code_analysis_client())
        decision = guard.check(OperationKind.WRITE, ca_session_id)
        if decision == GuardDecision.REJECT:
            return ErrorResult(
                message="invalid CA session",
                code=cast(Any, "SESSION_REJECTED"),
            )

        try:
            session = resolve_session_for_command(
                ca_session_id,
                file_path or None,
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

        if write_mode != "commit":
            return ErrorResult(
                message="write_mode=preview not implemented in this step",
                code=cast(Any, "NOT_IMPLEMENTED"),
            )

        comparison = compare_session_to_origin(session)
        if comparison.result == CompareResult.EQUAL:
            return SuccessResult(
                data={
                    "unchanged": True,
                    "uploaded": False,
                    "session_id": ca_session_id,
                    "project_id": project_id,
                    "file_path": session.file_path,
                }
            )

        client = get_code_analysis_client()
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
        return SuccessResult(
            data={
                "unchanged": False,
                "uploaded": True,
                "session_id": ca_session_id,
                "project_id": project_id,
                "file_path": session.file_path,
            }
        )
