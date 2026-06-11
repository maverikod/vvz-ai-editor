# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_git_log MCP command (C-014): SessionRepo commit history.

Returns the commit history of the SessionRepo (C-013) of an active
EditSession (C-012): commit hash, message, and timestamp per commit
(HRS {e002}). Requires a valid session_id; refuses without an active
session (HRS {e001}).
"""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.core.edit_session.edit_session import get_active_session


class SessionGitLogCommand(BaseMCPCommand):
    """MCP command returning the SessionRepo commit history (C-014, {e002})."""

    name = "session_git_log"

    version = "1.0.0"

    descr = "Return the commit history of an active edit session's git repository."

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
        return "session_git_log"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and session_id.
        """
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
    def metadata(cls: Type["SessionGitLogCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for session_git_log.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "session_git_log",
            "description": (
                "Return the commit history (hash, message, timestamp) of the "
                "SessionRepo for an active edit session. Requires session_id."
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
        """Execute the session_git_log command.

        Args:
            project_id: Required by schema; the session registry is
                authoritative for the repository location.
            session_id: Active session identifier (C-012).
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the commit list, or ErrorResult when no
            active session exists.
        """
        _ = project_id  # registry is authoritative; project_id is schema-required
        _ = kwargs
        try:
            session = get_active_session(session_id)
        except KeyError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"No active session: {session_id}")
            )
        commits = session.session_repo.log()
        payload: Dict[str, Any] = {
            "success": True,
            "commits": [
                {
                    "hash": c.hash,
                    "message": c.message,
                    "timestamp": c.timestamp,
                }
                for c in commits
            ],
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
