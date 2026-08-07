"""MCP command: universal_file_open — facade (C-016)."""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from mcp_proxy_adapter.commands.result import CommandResult, ErrorResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.open_command_metadata import (
    get_universal_file_open_metadata,
)
from ai_editor.commands.universal_file_edit.open_command_runtime import run_open_execute
from ai_editor.core.exceptions import ValidationError
from ai_editor.core.host_filesystem import HostFileOperationError
from ai_editor.core.upstream.code_analysis_client import (
    describe_exception,
    get_code_analysis_client,
)
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
                "format_group": {
                    "type": "string",
                    "enum": ["sidecar", "tree-temp", "text"],
                    "description": (
                        "Explicit format group override for files with unknown or "
                        "absent extensions. Ignored when the extension is already "
                        "recognized by the handler registry."
                    ),
                },
            },
            "required": ["project_id", "file_path", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["UniversalFileOpenCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_universal_file_open_metadata(cls))

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate open params; normalize (but do not reject) session_id.

        An empty ``session_id`` is deliberately NOT raised here: this hook
        runs before ``execute()``, and a raised ``ValidationError`` here
        would collapse into the generic ``VALIDATION_ERROR`` code, shadowing
        the more specific, already-implemented ``SESSION_INVALID`` branch at
        the top of ``execute()`` below. Leaving the emptiness check to
        ``execute()`` is what makes ``SESSION_INVALID`` reachable.
        """
        params = super().validate_params(params)
        params["session_id"] = str(params.get("session_id", "")).strip()
        return params

    async def execute(self, **kwargs: Any) -> CommandResult:  # type: ignore[override]
        ca_session_id = str(kwargs.get("session_id", "")).strip()
        if ca_session_id == "":
            return ErrorResult(
                message="session_id is required for universal_file_open",
                code=cast(Any, "SESSION_INVALID"),
            )
        # project_id identifies the project the session's file belongs to, and
        # every later universal_file_* call is checked against it (see
        # project_scope.py). The non-create path already rejects an empty value
        # inside the Code Analysis client with this exact message; create=true
        # issues zero CA calls (R1 below), so without this check it could
        # register a session owning no project at all and defeat that scope
        # check for the whole session.
        if str(kwargs.get("project_id", "") or "").strip() == "":
            return ErrorResult(
                message="session_id, project_id, and file_path are required",
                code=cast(Any, "VALIDATION_ERROR"),
                details={"project_id": kwargs.get("project_id")},
            )
        # R1: opening a NEW file is local-draft-only — it must issue zero CA calls.
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
            return ErrorResult(
                message=describe_exception(exc, context="universal_file_open"),
                code=cast(Any, "OPEN_ERROR"),
            )
