# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""session_git_diff MCP command (C-014): unified diff in tree or source mode.

Produces a unified diff in ``tree`` mode (commit vs commit on three-section
tree artefacts) or ``source`` mode (tree revision rev_a vs the most recent
per-mutation unmark-exported in-session source at ``session.session_source_path``).
Distinct from ``session_write``, which diffs in-session artefacts against live
external files.
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    INVALID_OPERATION,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.core.edit_session.edit_session import get_active_session


class SessionGitDiffCommand(BaseMCPCommand):
    """MCP command returning a unified diff from SessionRepo history (C-014)."""

    name = "session_git_diff"

    version = "1.0.0"

    descr = (
        "Return a unified diff between tree revisions or between a tree revision "
        "and the in-session source copy."
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
        return "session_git_diff"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, session_id, mode, rev_a,
            and optional rev_b.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
                "mode": {"type": "string", "enum": ["tree", "source"]},
                "rev_a": {"type": "string"},
                "rev_b": {"type": "string"},
            },
            "required": ["project_id", "session_id", "mode", "rev_a"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["SessionGitDiffCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for session_git_diff.

        Returns:
            Metadata dict with description, parameters, and examples.
        """
        return {
            "name": "session_git_diff",
            "description": (
                "Return a unified diff in tree mode (rev_a vs rev_b tree content) "
                "or source mode (rev_a tree content vs in-session source copy). "
                "Requires an active session_id."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True},
                "session_id": {"type": "string", "required": True},
                "mode": {
                    "type": "string",
                    "required": True,
                    "enum": ["tree", "source"],
                },
                "rev_a": {"type": "string", "required": True},
                "rev_b": {"type": "string", "required": False},
            },
            "examples": [
                {
                    "command": {
                        "project_id": "<uuid>",
                        "session_id": "<uuid>",
                        "mode": "tree",
                        "rev_a": "<commit-hash-a>",
                        "rev_b": "<commit-hash-b>",
                    }
                },
                {
                    "command": {
                        "project_id": "<uuid>",
                        "session_id": "<uuid>",
                        "mode": "source",
                        "rev_a": "<commit-hash>",
                    }
                },
            ],
        }

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        mode: str,
        rev_a: str,
        rev_b: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the session_git_diff command.

        Args:
            project_id: Required by schema; the session registry is
                authoritative for the repository location.
            session_id: Active session identifier (C-012).
            mode: Diff mode: ``tree`` (rev_a vs rev_b) or ``source`` (rev_a
                tree vs in-session source).
            rev_a: Left-side tree revision commit hash.
            rev_b: Right-side tree revision; required when mode is ``tree``.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with the unified diff text, or ErrorResult on
            missing session or invalid mode/parameters.
        """
        _ = project_id  # registry is authoritative; project_id is schema-required
        _ = kwargs
        try:
            session = get_active_session(session_id)
        except KeyError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"No active session: {session_id}")
            )

        repo = session.session_repo

        if mode == "tree":
            if rev_b is None:
                return error_result_from_make_error(
                    make_error(INVALID_OPERATION, "tree mode requires rev_b")
                )
            left_text = repo.show_tree(rev=rev_a).decode("utf-8", errors="replace")
            right_text = repo.show_tree(rev=rev_b).decode("utf-8", errors="replace")
            from_label = f"tree@{rev_a}"
            to_label = f"tree@{rev_b}"
        elif mode == "source":
            left_text = repo.show_tree(rev=rev_a).decode("utf-8", errors="replace")
            right_text = session.session_source_path.read_text(encoding="utf-8")
            from_label = f"tree@{rev_a}"
            to_label = "in-session-source"
        else:
            return error_result_from_make_error(
                make_error(INVALID_OPERATION, f"Unknown diff mode: {mode}")
            )

        diff = "".join(
            difflib.unified_diff(
                left_text.splitlines(keepends=True),
                right_text.splitlines(keepends=True),
                fromfile=from_label,
                tofile=to_label,
            )
        )
        payload: Dict[str, Any] = {
            "success": True,
            "mode": mode,
            "diff": diff,
        }
        return SuccessResult(data=cast(Dict[str, Any], payload))
