"""
UniversalFileNodeAtLineCommand: resolve MAP node_ref for a 1-based source line.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.command_metadata_helpers import build_command_metadata
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    UNKNOWN_FORMAT,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import FORMAT_SIDECAR
from ai_editor.commands.universal_file_edit.search_command import (
    TREE_NOT_AVAILABLE,
    _build_short_id_lookup,
    _node_ref_from_stable_id,
)
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.core.cst_tree.models import TreeNodeMetadata
from ai_editor.core.cst_tree.tree_builder import get_tree

logger = logging.getLogger(__name__)

LINE_NOT_FOUND = "LINE_NOT_FOUND"


def _span_sort_key(meta: TreeNodeMetadata) -> tuple[int, int]:
    return (meta.end_line - meta.start_line, -meta.start_line)


def _nodes_containing_line(tree_id: str, line: int) -> List[TreeNodeMetadata]:
    tree = get_tree(tree_id)
    if tree is None:
        return []
    matches = [
        meta
        for meta in tree.metadata_map.values()
        if meta.start_line <= line <= meta.end_line
    ]
    return sorted(matches, key=_span_sort_key)


def _node_payload(
    meta: TreeNodeMetadata,
    *,
    lookup: Any,
) -> Dict[str, Any]:
    node_ref, kind = _node_ref_from_stable_id(meta, lookup=lookup)
    payload: Dict[str, Any] = {
        "node_ref": node_ref,
        "stable_id": meta.stable_id,
        "type": meta.type,
        "name": meta.name,
        "qualname": meta.qualname,
        "start_line": meta.start_line,
        "end_line": meta.end_line,
    }
    if kind == "uuid":
        payload["node_ref_kind"] = "uuid"
    return payload


class UniversalFileNodeAtLineCommand(BaseMCPCommand):
    """Return the most specific CST node_ref covering a 1-based line number."""

    name = "universal_file_node_at_line"

    version = "1.0.0"

    descr = (
        "Resolve MAP node_ref for the most specific CST node at a 1-based line "
        "(Python sidecar edit session)."
    )

    category = "file_management"

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
                    "description": "Project UUID.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Active session from universal_file_open.",
                },
                "line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-based source line number.",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path when the session has multiple open files."
                    ),
                },
                "include_ancestors": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, include all covering nodes sorted by span "
                        "(smallest first) in ancestors."
                    ),
                },
            },
            "required": ["project_id", "session_id", "line"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileNodeAtLineCommand"]) -> Dict[str, Any]:
        return cast(
            Dict[str, Any],
            build_command_metadata(
                cls,
                detailed_description=_DETAILED_DESCRIPTION,
                usage_examples=_USAGE_EXAMPLES,
                error_cases=_ERROR_CASES,
                return_value=_RETURN_VALUE,
                best_practices=_BEST_PRACTICES,
            ),
        )

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        line: int,
        file_path: str = "",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = project_id
        include_ancestors = bool(kwargs.get("include_ancestors", False))
        if line < 1:
            return error_result_from_make_error(
                make_error(LINE_NOT_FOUND, f"No CST node covers line {line}")
            )

        try:
            session = get_session(session_id, file_path=file_path or None)
        except ValueError as exc:
            msg = str(exc)
            if msg == "SESSION_FILE_PATH_REQUIRED":
                return error_result_from_make_error(
                    make_error(
                        SESSION_FILE_PATH_REQUIRED,
                        "file_path is required when the session has multiple open files",
                        details={"session_id": session_id},
                    )
                )
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )

        if session.format_group != FORMAT_SIDECAR:
            return error_result_from_make_error(
                make_error(
                    UNKNOWN_FORMAT,
                    (
                        "universal_file_node_at_line applies only to an open Python "
                        "sidecar edit session."
                    ),
                    {
                        "format_group": session.format_group,
                        "file_path": session.file_path,
                    },
                )
            )

        tree_id = session.tree_id
        if not tree_id or get_tree(tree_id) is None:
            from ai_editor.commands.universal_file_edit.sidecar_cst_apply import (
                _refresh_in_memory_cst_without_sidecar,
            )

            try:
                _refresh_in_memory_cst_without_sidecar(session)
                tree_id = session.tree_id
            except Exception:
                tree_id = session.tree_id
        if not tree_id or get_tree(tree_id) is None:
            return error_result_from_make_error(
                make_error(
                    TREE_NOT_AVAILABLE,
                    "Session has no loaded CST tree.",
                    {"session_id": session_id, "file_path": session.file_path},
                )
            )

        covering = _nodes_containing_line(tree_id, line)
        if not covering:
            return error_result_from_make_error(
                make_error(
                    LINE_NOT_FOUND,
                    f"No CST node covers line {line}",
                    {
                        "session_id": session_id,
                        "file_path": session.file_path,
                        "line": line,
                    },
                )
            )

        lookup = _build_short_id_lookup(session)
        primary = covering[0]
        data: Dict[str, Any] = {
            "success": True,
            "session_id": session_id,
            "file_path": session.file_path,
            "tree_id": tree_id,
            "line": line,
            **_node_payload(primary, lookup=lookup),
        }
        if include_ancestors:
            data["ancestors"] = [
                _node_payload(meta, lookup=lookup) for meta in covering[1:]
            ]
        return SuccessResult(data=data)


_DETAILED_DESCRIPTION = (
    "Resolve the **most specific** CST node on a 1-based line in an open Python "
    "sidecar edit session. Returns `node_ref` (MAP short_id when known) suitable "
    "for `universal_file_edit`.\n\n"
    "Use after edits when prior node_ref values may be stale — re-call with the "
    "target line to obtain the current node_ref.\n\n"
    "Optional `include_ancestors=true` returns remaining covering nodes sorted "
    "from smallest span to largest (method, class, module)."
)

_USAGE_EXAMPLES = [
    {
        "description": "Node ref for line 42",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "session_id": "<ca-session-id>",
            "file_path": "src/example.py",
            "line": 42,
        },
        "explanation": "Returns node_ref for the innermost node spanning line 42.",
    },
]

_ERROR_CASES = {
    LINE_NOT_FOUND: {
        "description": "No CST node spans the requested line.",
        "solution": "Pick a line inside a statement, definition, or expression.",
    },
    TREE_NOT_AVAILABLE: {
        "description": "Session tree is not loaded.",
        "solution": "Call universal_file_open first or refresh the session.",
    },
    UNKNOWN_FORMAT: {
        "description": "Session is not Python sidecar.",
        "solution": "Use only on .py sidecar edit sessions.",
    },
    SESSION_NOT_FOUND: {
        "description": "Unknown session_id.",
        "solution": "Open the file with universal_file_open.",
    },
    SESSION_FILE_PATH_REQUIRED: {
        "description": "Multi-file session without file_path.",
        "solution": "Pass file_path from the open bundle.",
    },
}

_RETURN_VALUE = {
    "success": {
        "description": "Most specific node at the line.",
        "data": {
            "node_ref": "MAP short_id or UUID",
            "stable_id": "UUID4 stable id",
            "type": "LibCST node type",
            "start_line": "int",
            "end_line": "int",
            "ancestors": "optional list when include_ancestors=true",
        },
    },
}

_BEST_PRACTICES = [
    "Re-call after replace on a parent node to refresh node_ref for nested lines.",
    "Use include_ancestors when you need class- or module-level scope.",
]
