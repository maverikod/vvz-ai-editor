# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_undo MCP command: classic one-step undo in an active edit session."""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    NOTHING_TO_UNDO,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.commands.universal_file_edit.session_history_sync import (
    sync_command_session_after_history,
)


class SessionUndoCommand(BaseMCPCommand):
    """MCP command: undo the last edit in an active universal_file_edit session."""

    name = "session_undo"

    version = "1.0.0"

    descr = "Undo the last edit in an active edit session (classic editor semantics)."

    category = "file_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        return "session_undo"

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
    def metadata(cls: Type["SessionUndoCommand"]) -> Dict[str, Any]:
        return {
            "name": "session_undo",
            "description": (
                "Move one step back in the edit-session undo stack without "
                "creating a new commit. Requires an active session_id from "
                "universal_file_open. A subsequent edit truncates the redo branch."
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
            state = session.core.undo()
        except RuntimeError as exc:
            if "nothing to undo" in str(exc):
                return error_result_from_make_error(
                    make_error(NOTHING_TO_UNDO, "Nothing to undo in this session.")
                )
            raise
        sync_command_session_after_history(session)
        payload: Dict[str, Any] = {"success": True, "action": "undo", **state}
        return SuccessResult(data=cast(Dict[str, Any], payload))
