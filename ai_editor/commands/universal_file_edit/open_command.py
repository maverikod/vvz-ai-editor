"""MCP command: universal_file_open — facade (C-016)."""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from mcp_proxy_adapter.commands.result import CommandResult, ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.open_command_metadata import (
    get_universal_file_open_metadata,
)
from ai_editor.commands.universal_file_edit.open_command_runtime import run_open_execute
from ai_editor.core.exceptions import ValidationError
from ai_editor.core.host_filesystem import HostFileOperationError
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)

logger = logging.getLogger(__name__)


class UniversalFileOpenCommand(BaseMCPCommand):
    name = "universal_file_open"
    version = "1.0.0"
    descr = "Open project file into editor workspace"
    category = "universal_file_edit"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Resolves the project root on disk. "
                        "Use list_projects to discover valid values."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path to the file. Literal path; no globs."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "CA session id (required; same id as session_create on "
                        "Code Analysis Server). Mandatory CA Session context "
                        "(C-004); not an optional editor group id."
                    ),
                },
                "create": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When True, open a NEW file from initial_content with zero "
                        "Code Analysis calls (CA-local-only). The file is registered "
                        "and locked on CA atomically on its first "
                        "universal_file_write commit, not at open."
                    ),
                },
                "initial_content": {
                    "type": "string",
                    "description": "Initial file content used only when create=True.",
                },
            },
            "required": ["project_id", "file_path", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["UniversalFileOpenCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_universal_file_open_metadata(cls))

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate open params; require non-empty CA session_id."""
        params = super().validate_params(params)
        sid = str(params.get("session_id", "")).strip()
        if sid == "":
            raise ValidationError(
                "session_id is required for universal_file_open",
                field="session_id",
            )
        params["session_id"] = sid
        return params

    async def execute(self, **kwargs: Any) -> CommandResult:  # type: ignore[override]
        ca_session_id = str(kwargs.get("session_id", "")).strip()
        if ca_session_id == "":
            return ErrorResult(
                message="session_id is required for universal_file_open",
                code=cast(Any, "SESSION_INVALID"),
            )
        # R1: opening a NEW file is CA-local-only — it must issue zero CA calls.
        # The Session Guard validates the session over CA (session_list_file_locks),
        # so it is skipped for create=true. The CA session is validated instead at
        # the first commit (the WRITE guard), which is when CA is first contacted.
        create = bool(kwargs.get("create", False))
        if not create:
            guard = SessionGuard(get_code_analysis_client())
            decision = guard.check(OperationKind.OPEN, ca_session_id)
            if decision == GuardDecision.REJECT:
                return ErrorResult(
                    message=f"CA session not found or invalid: {ca_session_id}",
                    code=cast(Any, "SESSION_NOT_FOUND"),
                )
            if decision == GuardDecision.ALLOW_TERMINATING:
                return ErrorResult(
                    message="internal guard misclassification for open",
                    code=cast(Any, "OPEN_ERROR"),
                )
        try:
            return run_open_execute(self, **kwargs)
        except ValidationError as exc:
            return ErrorResult(message=str(exc), code=cast(Any, "VALIDATION_ERROR"))
        except HostFileOperationError as exc:
            return ErrorResult(
                message=str(exc),
                code=cast(Any, exc.code or "HOST_FILE_OPERATION_ERROR"),
                details=exc.details,
            )
        except Exception as exc:
            logger.error("universal_file_open failed: %s", exc, exc_info=True)
            return ErrorResult(message=str(exc), code=cast(Any, "OPEN_ERROR"))
