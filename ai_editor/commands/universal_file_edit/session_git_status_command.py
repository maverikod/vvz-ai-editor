# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_git_status MCP command (C-014): uncommitted-changes check.

Reports whether the active EditSession's SessionRepo (C-013) has
uncommitted changes relative to HEAD (HRS {e005}). Under the
one-commit-per-edit invariant the repository is always clean; this command
is a consistency check. Requires a valid session_id; refuses without an
active session (HRS {e001}).
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


class SessionGitStatusCommand(BaseMCPCommand):
    """MCP command reporting SessionRepo cleanliness (C-014, {e005})."""

    name = "session_git_status"

    version = "1.0.0"

    descr = "Report whether an edit session's git repository is clean."

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
        return "session_git_status"

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
    def metadata(cls: Type["SessionGitStatusCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for session_git_status.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "session_git_status",
            "description": (
                "Report whether the SessionRepo of an active edit session "
                "has uncommitted changes relative to HEAD. Requires "
                "session_id. Normally always clean."
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
        """Execute the session_git_status command.

        Args:
            project_id: Required by schema; the session registry is
                authoritative for the repository location.
            session_id: Active session identifier (C-012).
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with a clean flag, or ErrorResult when no active
            session exists.
        """
        _ = project_id  # registry is authoritative; project_id is schema-required
        _ = kwargs
        try:
            session = get_active_session(session_id)
        except KeyError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"No active session: {session_id}")
            )
        clean = session.session_repo.status_is_clean()
        payload: Dict[str, Any] = {"success": True, "clean": clean}
        return SuccessResult(data=cast(Dict[str, Any], payload))
