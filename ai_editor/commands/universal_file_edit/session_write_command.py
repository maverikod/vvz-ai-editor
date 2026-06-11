# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_write MCP command (C-012): two-stage external copy-out.

Preview (confirm=false) diffs in-session artefacts against live external
files without writing. Confirm (confirm=true) atomically copies both
artefacts externally when the session tree is valid, or source only when
invalid. Distinct from session_git_diff, which diffs SessionRepo history.
"""

from __future__ import annotations

from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from ai_editor.core.edit_session.edit_session import get_active_session


class SessionWriteCommand(BaseMCPCommand):
    """MCP command for EditSession two-stage external copy-out (C-012)."""

    name = "session_write"

    version = "1.0.0"

    descr = (
        "Two-stage external copy-out for an active edit session (preview or confirm)."
    )

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
        return "session_write"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, session_id, and confirm.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "session_id": {
                    "type": "string",
                    "description": "Active edit session id.",
                },
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "False (default): preview diffs only. "
                        "True: atomic external copy-out."
                    ),
                    "default": False,
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["SessionWriteCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for session_write.

        Returns:
            Metadata dict with description, parameters, examples, and errors.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Two-stage external copy-out for an active EditSession (C-012). "
                "Preview (confirm=false or omitted) calls preview_external_write() "
                "and never modifies live external files. Confirm (confirm=true) "
                "calls confirm_external_copy_out() and atomically copies both "
                "in-session source and tree to external co-located paths when "
                "the session tree is valid; when invalid, only the in-session "
                "source is copied and the external tree is left unchanged. "
                "Distinct from session_git_diff, which diffs SessionRepo commit "
                "history rather than live external files. This command does not "
                "create SessionRepo commits."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID.",
                    "type": "string",
                    "required": True,
                },
                "session_id": {
                    "description": "Active edit session id.",
                    "type": "string",
                    "required": True,
                },
                "confirm": {
                    "description": (
                        "False (default): preview diffs only. "
                        "True: atomic external copy-out."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "Command completed successfully.",
                    "data": {
                        "success": "Always true on success.",
                        "phase": "Either preview or confirmed.",
                        "has_changes": (
                            "Whether in-session artefacts differ from external files."
                        ),
                        "source_diff": "Unified diff for source (preview phase only).",
                        "tree_diff": "Unified diff for tree (preview phase only).",
                    },
                },
                "error": {
                    "description": "Session not found or external write failed.",
                    "code": "SESSION_NOT_FOUND or WRITE_FAILED",
                },
            },
            "usage_examples": [
                {
                    "description": "Preview diffs without modifying external files.",
                    "command": {"project_id": "<uuid>", "session_id": "<uuid>"},
                },
                {
                    "description": "Confirm atomic external copy-out.",
                    "command": {
                        "project_id": "<uuid>",
                        "session_id": "<uuid>",
                        "confirm": True,
                    },
                },
            ],
            "error_cases": {
                SESSION_NOT_FOUND: {
                    "description": "No active edit session for the given session_id.",
                    "message": "No active session: {session_id}",
                    "solution": "Open session first.",
                },
                WRITE_FAILED: {
                    "description": "External copy-out failed with an OS error.",
                    "message": "OS error text from the failed copy operation.",
                    "solution": (
                        "Verify external file permissions and disk space; "
                        "retry confirm after resolving the filesystem issue."
                    ),
                },
            },
            "best_practices": [
                "Always call preview (confirm=false) before confirm=true to inspect diffs.",
                "Preview never writes to external files; only confirm performs copy-out.",
                "Use session_git_diff for SessionRepo history diffs, not live external files.",
                "This command does not commit to SessionRepo; mutations commit separately.",
            ],
        }

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        confirm: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the session_write command.

        Args:
            project_id: Required by schema; the session registry is authoritative.
            session_id: Active session identifier (C-012).
            confirm: When true, perform atomic external copy-out; otherwise preview.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with preview or confirmed phase payload, or ErrorResult
            when the session is missing or external write fails.
        """
        _ = project_id
        _ = kwargs
        try:
            session = get_active_session(session_id)
        except KeyError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"No active session: {session_id}")
            )

        if confirm:
            preview = session.preview_external_write()
            has_changes = bool(preview["has_changes"])
            try:
                session.confirm_external_copy_out()
            except OSError as exc:
                return error_result_from_make_error(make_error(WRITE_FAILED, str(exc)))
            payload: Dict[str, Any] = {
                "success": True,
                "phase": "confirmed",
                "has_changes": has_changes,
            }
            return SuccessResult(data=cast(Dict[str, Any], payload))

        preview = session.preview_external_write()
        preview_payload: Dict[str, Any] = {
            "success": True,
            "phase": "preview",
            "has_changes": preview["has_changes"],
            "source_diff": preview["source_diff"],
            "tree_diff": preview["tree_diff"],
        }
        return SuccessResult(data=cast(Dict[str, Any], preview_payload))
