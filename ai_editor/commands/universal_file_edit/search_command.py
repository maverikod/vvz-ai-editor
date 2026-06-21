"""
UniversalFileSearchCommand: XPath/CSTQuery search on an open edit-session CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    UNKNOWN_FORMAT,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import FORMAT_SIDECAR
from ai_editor.commands.universal_file_edit.search_command_metadata import (
    get_universal_file_search_metadata,
)
from ai_editor.commands.universal_file_edit.session import get_session
from ai_editor.core.cst_tree.models import TreeNodeMetadata
from ai_editor.core.cst_tree.tree_builder import get_tree
from ai_editor.core.cst_tree.tree_finder import find_nodes

logger = logging.getLogger(__name__)

TREE_NOT_AVAILABLE = "TREE_NOT_AVAILABLE"
INVALID_SEARCH = "INVALID_SEARCH"


def _match_to_response(meta: TreeNodeMetadata) -> Dict[str, Any]:
    """Serialize one TreeNodeMetadata for universal edit workflow."""
    data = meta.to_dict()
    data["node_ref"] = meta.stable_id
    return data


class UniversalFileSearchCommand(BaseMCPCommand):
    """Search the in-memory CST tree of one universal_file_open session."""

    name = "universal_file_search"

    version = "1.0.0"

    descr = (
        "XPath/CSTQuery search on the open edit-session CST tree (Python sidecar only)."
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
                    "description": (
                        "Project UUID. Use list_projects to discover valid project_id values."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Active session from universal_file_open. Search runs on "
                        "that session's in-memory CST tree only."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path. Required when the session has "
                        "more than one open file."
                    ),
                },
                "search_type": {
                    "type": "string",
                    "enum": ["simple", "xpath"],
                    "default": "xpath",
                    "description": "xpath (CSTQuery in query) or simple (field filters).",
                },
                "query": {
                    "type": "string",
                    "description": "CSTQuery selector (required for xpath search_type).",
                },
                "node_type": {
                    "type": "string",
                    "description": "Simple search: LibCST node type filter.",
                },
                "name": {
                    "type": "string",
                    "description": "Simple search: exact node name.",
                },
                "qualname": {
                    "type": "string",
                    "description": "Simple search: exact qualified name.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Simple search: minimum start_line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Simple search: maximum end_line.",
                },
                "include_code": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include source code for each match.",
                },
                "require_one": {
                    "type": "boolean",
                    "default": False,
                    "description": "Require exactly one match.",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Optional cap on returned matches.",
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileSearchCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_universal_file_search_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        file_path: str = "",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = project_id
        search_type: str = kwargs.get("search_type", "xpath")
        query: Optional[str] = kwargs.get("query")
        node_type: Optional[str] = kwargs.get("node_type")
        name: Optional[str] = kwargs.get("name")
        qualname: Optional[str] = kwargs.get("qualname")
        start_line: Optional[int] = kwargs.get("start_line")
        end_line: Optional[int] = kwargs.get("end_line")
        include_code: bool = bool(kwargs.get("include_code", False))
        require_one: bool = bool(kwargs.get("require_one", False))
        max_results: Optional[int] = kwargs.get("max_results")

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

        if session.format_group != FORMAT_SIDECAR or session.is_invalid:
            return error_result_from_make_error(
                make_error(
                    UNKNOWN_FORMAT,
                    (
                        "universal_file_search applies only to an open Python sidecar "
                        "edit session (CST tree). JSON/YAML/text or is_invalid sessions "
                        "are not supported."
                    ),
                    {
                        "format_group": session.format_group,
                        "is_invalid": session.is_invalid,
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

        try:
            matches = find_nodes(
                tree_id=tree_id,
                query=query,
                search_type=search_type,
                node_type=node_type,
                name=name,
                qualname=qualname,
                start_line=start_line,
                end_line=end_line,
                include_code=include_code,
            )
        except ValueError as exc:
            return error_result_from_make_error(
                make_error(
                    INVALID_SEARCH,
                    str(exc),
                    {
                        "session_id": session_id,
                        "search_type": search_type,
                        "query": query,
                    },
                )
            )
        except Exception as exc:
            logger.exception("universal_file_search failed: %s", exc)
            return ErrorResult(message=f"universal_file_search failed: {exc}")

        total_matches = len(matches)

        if require_one:
            if total_matches == 0:
                return error_result_from_make_error(
                    make_error(
                        "NoMatch",
                        "Selector matched no nodes in the session tree",
                        {
                            "session_id": session_id,
                            "tree_id": tree_id,
                            "query": query,
                            "search_type": search_type,
                        },
                    )
                )
            if total_matches > 1:
                candidates = [
                    {
                        "node_ref": m.stable_id,
                        "name": m.name,
                        "type": m.type,
                        "start_line": m.start_line,
                    }
                    for m in matches[:10]
                ]
                return error_result_from_make_error(
                    make_error(
                        "NonUniqueMatch",
                        f"Selector matched {total_matches} nodes; exactly one required",
                        {
                            "session_id": session_id,
                            "total_matches": total_matches,
                            "candidates": candidates,
                        },
                    )
                )

        if max_results is not None and max_results > 0:
            matches = matches[:max_results]

        match_dicts: List[Dict[str, Any]] = [_match_to_response(m) for m in matches]

        data: Dict[str, Any] = {
            "success": True,
            "session_id": session_id,
            "file_path": session.file_path,
            "tree_id": tree_id,
            "search_type": search_type,
            "matches": match_dicts,
            "total_matches": total_matches,
            "returned_matches": len(match_dicts),
        }
        if require_one and len(matches) == 1:
            data["node_ref"] = matches[0].stable_id
            data["match"] = match_dicts[0]

        return SuccessResult(data=data)
