# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_git_show MCP command (C-014): tree content at a revision.

Returns the full content of the tree file at a given commit of the active
EditSession's SessionRepo (C-013), HRS {e004}. Requires a valid session_id;
refuses without an active session (HRS {e001}).
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


class SessionGitShowCommand(BaseMCPCommand):
    """MCP command returning tree content at a revision (C-014, {e004})."""

    name = "session_git_show"

    version = "1.0.0"

    descr = "Return the tree-file content at a revision of an edit session repo."

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
        return "session_git_show"

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
    def metadata(cls: Type["SessionGitShowCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for session_git_show.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "session_git_show",
            "description": (
                "Return the tree-file content at a commit revision of the "
                "SessionRepo for an active edit session. Requires session_id "
                "and rev."
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
        """Execute the session_git_show command.

        Args:
            project_id: Required by schema; the session registry is
                authoritative for the repository location.
            session_id: Active session identifier (C-012).
            rev: Commit hex sha whose tree content is returned.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the tree content (UTF-8 text), or ErrorResult
            when no active session exists.
        """
        _ = project_id  # registry is authoritative; project_id is schema-required
        _ = kwargs
        try:
            session = get_active_session(session_id)
        except KeyError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"No active session: {session_id}")
            )
        content_bytes = session.session_repo.show_tree(rev=rev)
        payload: Dict[str, Any] = {
            "success": True,
            "rev": rev,
            "content": content_bytes.decode("utf-8", errors="replace"),
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
