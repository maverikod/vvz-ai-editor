# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_redo MCP command: classic one-step redo in an active edit session."""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    NOTHING_TO_REDO,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.commands.universal_file_edit.session_history_sync import (
    sync_command_session_after_history,
)


class SessionRedoCommand(BaseMCPCommand):
    """MCP command: redo the last undone edit in an active edit session."""

    name = "session_redo"

    version = "1.0.0"

    descr = "Redo the last undone edit in an active edit session."

    category = "file_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        return "session_redo"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["SessionRedoCommand"]) -> Dict[str, Any]:
        return {
            "name": "session_redo",
            "description": (
                "Move one step forward on the edit-session redo stack after "
                "session_undo. Requires an active session_id from universal_file_open."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "session_id": {"type": "string", "required": True},
            },
            "examples": [{"command": {"project_id": "<uuid>", "session_id": "<uuid>"}}],
        }

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = project_id, kwargs
        try:
            session = get_session(session_id)
        except ValueError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )
        try:
            state = session.core.redo()
        except RuntimeError as exc:
            if "nothing to redo" in str(exc):
                return error_result_from_make_error(
                    make_error(NOTHING_TO_REDO, "Nothing to redo in this session.")
                )
            raise
        sync_command_session_after_history(session)
        payload: Dict[str, Any] = {"success": True, "action": "redo", **state}
        return SuccessResult(data=cast(Dict[str, Any], payload))
