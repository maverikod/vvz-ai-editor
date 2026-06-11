# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_git_revert MCP command (C-014): roll tree back by a new commit.

Rolls the tree of the active EditSession's SessionRepo (C-013) back to a
prior revision by creating a NEW revert commit (HRS {e006}); history is
preserved and no commit is deleted. Requires a valid session_id; refuses
without an active session (HRS {e001}).
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


class SessionGitRevertCommand(BaseMCPCommand):
    """MCP command reverting the SessionRepo tree by a new commit (C-014, {e006})."""

    name = "session_git_revert"

    version = "1.0.0"

    descr = "Roll an edit session's tree back to a revision via a new revert commit."

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
        return "session_git_revert"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, session_id, and rev.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
                "rev": {"type": "string"},
            },
            "required": ["project_id", "session_id", "rev"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["SessionGitRevertCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for session_git_revert.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "session_git_revert",
            "description": (
                "Roll the tree of an active edit session back to a prior "
                "revision by creating a new revert commit; history is "
                "preserved. Requires session_id and rev."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "session_id": {"type": "string", "required": True},
                "rev": {"type": "string", "required": True},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "session_id": "<uuid>",
                        "rev": "<commit-hash>",
                    }
                }
            ],
        }

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        rev: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the session_git_revert command.

        Args:
            project_id: Required by schema; the session registry is
                authoritative for the repository location.
            session_id: Active session identifier (C-012).
            rev: Commit hex sha to roll the tree back to.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the new revert commit hash, or ErrorResult
            when no active session exists.
        """
        _ = project_id  # registry is authoritative; project_id is schema-required
        _ = kwargs
        try:
            core = get_active_session(session_id)
        except KeyError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"No active session: {session_id}")
            )
        from ai_editor.commands.universal_file_edit.session import get_session
        from ai_editor.commands.universal_file_edit.session_history_sync import (
            sync_command_session_after_history,
        )

        try:
            facade = get_session(session_id)
        except ValueError:
            facade = None
        new_commit = core.record_revert_commit(rev=rev)
        if facade is not None:
            sync_command_session_after_history(facade)
        payload: Dict[str, Any] = {
            "success": True,
            "reverted_to": rev,
            "new_commit": new_commit,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
