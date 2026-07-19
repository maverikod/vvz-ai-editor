"""UniversalFileWriteCommand facade (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import CommandResult, ErrorResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.write_command_metadata import (
    get_universal_file_write_metadata,
)
from ai_editor.commands.universal_file_edit.write_command_runtime import (
    run_write_execute,
)
from ai_editor.core.exceptions import ValidationError
from ai_editor.core.host_filesystem import HostFileOperationError
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)


class UniversalFileWriteCommand(BaseMCPCommand):
    """Preview diff vs origin; commit uploads to CA when changed (C-012)."""

    name = "universal_file_write"
    version = "1.0.0"
    descr = (
        "Write universal file edit draft: preview/commit diff vs origin; "
        "two-phase PID lockfile for sidecar when write_mode is omitted."
    )
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
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Required for CA upload on commit. "
                        "Use list_projects to discover valid values."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "CA session id from session_create; same id on all "
                        "universal_file_* calls."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path. Required when the CA session has "
                        "more than one open file. Optional when one file is open."
                    ),
                },
                "write_mode": {
                    "type": "string",
                    "enum": ["preview", "commit"],
                    "default": "preview",
                    "description": (
                        "preview: unified diff vs origin (no CA upload, no validation). "
                        "commit: pre-write validation then upload when content differs. "
                        "Sidecar (.py): omitted write_mode uses two-phase lockfile "
                        "(first call preview+lock, second call commit)."
                    ),
                },
                "format_python": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true and file_path is .py/.pyi/.pyw, run black on "
                        "canonical export before preview diff or CA upload."
                    ),
                },
                "verify_after_upload": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "On commit upload success, download file from CA without "
                        "lock and include ca_verify in the response."
                    ),
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        validated: Dict[str, Any] = super().validate_params(params)
        wm_raw = validated.get("write_mode")
        wm = "preview" if wm_raw is None else wm_raw
        if wm not in ("preview", "commit"):
            raise ValidationError(
                "write_mode must be 'preview' or 'commit'",
                field="write_mode",
                details={"write_mode": wm},
            )
        validated["write_mode"] = wm
        validated["write_mode_explicit"] = wm_raw is not None
        validated["format_python"] = bool(validated.get("format_python", False))
        validated["verify_after_upload"] = bool(
            validated.get("verify_after_upload", False)
        )
        return validated

    @classmethod
    def metadata(cls: Type["UniversalFileWriteCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_universal_file_write_metadata(cls))

    async def execute(self, **kwargs: Any) -> CommandResult:  # type: ignore
        project_id = str(kwargs.get("project_id", ""))
        ca_session_id = str(kwargs.get("session_id", ""))
        file_path = str(kwargs.get("file_path", ""))
        write_mode = str(kwargs.get("write_mode", "preview"))
        write_mode_explicit = bool(kwargs.get("write_mode_explicit", False))
        format_python = bool(kwargs.get("format_python", False))
        verify_after_upload = bool(kwargs.get("verify_after_upload", False))

        guard = SessionGuard(get_code_analysis_client())
        try:
            decision = guard.check(OperationKind.WRITE, ca_session_id)
        except HostFileOperationError as exc:
            return ErrorResult(
                message=str(exc),
                code=cast(Any, exc.code or "HOST_FILE_OPERATION_ERROR"),
                details=exc.details,
            )
        if decision == GuardDecision.REJECT:
            return ErrorResult(
                message="invalid CA session",
                code=cast(Any, "SESSION_REJECTED"),
            )

        return await run_write_execute(
            project_id=project_id,
            session_id=ca_session_id,
            write_mode=write_mode,
            write_mode_explicit=write_mode_explicit,
            file_path=file_path,
            client=get_code_analysis_client(),
            format_python=format_python,
            verify_after_upload=verify_after_upload,
        )
