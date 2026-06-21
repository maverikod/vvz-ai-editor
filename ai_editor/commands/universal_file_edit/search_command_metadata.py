"""
Metadata for universal_file_search command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from ai_editor.commands.command_metadata_helpers import build_command_metadata
from ai_editor.commands.identifier_types_reference import SEARCH_IDENTIFIER_SECTION


def get_universal_file_search_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_search."""
    return build_command_metadata(
        cls,
        detailed_description=_DETAILED_DESCRIPTION,
        usage_examples=_USAGE_EXAMPLES,
        error_cases=_ERROR_CASES,
        return_value=_RETURN_VALUE,
        best_practices=_BEST_PRACTICES,
    )


_DETAILED_DESCRIPTION = (
    "XPath / CSTQuery search **inside one open edit-session tree** (Python sidecar only).\n\n"
    "This command does **not** search the project, disk, or index. It runs selectors "
    "only against the **in-memory CST tree bound to session_id** from "
    "`universal_file_open` — the same draft tree that `universal_file_edit` mutates.\n\n"
    "Use it like editor structural Find: locate nodes by type, name, qualname, or "
    "CSTQuery path, then pass returned `node_ref` values to `universal_file_edit`.\n\n"
    "Workflow placement (universal file edit block):\n"
    "  1. universal_file_open  → session_id\n"
    "  2. universal_file_search → node_ref list (this command)\n"
    "  3. universal_file_edit  → apply ops using node_ref as node_id\n"
    "  4. universal_file_write / universal_file_close\n\n"
    "Optional: call `universal_file_preview` for outline navigation; use "
    "`universal_file_search` when you need a **selector query** over the whole tree.\n\n"
    "Scope rules:\n"
    "  - Requires active `session_id` (server restart invalidates sessions).\n"
    "  - **Sidecar Python only** (`.py` / `.pyi` / `.pyw` with CST tree). "
    "JSON/YAML/text sessions return UNKNOWN_FORMAT.\n"
    "  - Pass `file_path` when the session has multiple open files.\n"
    "  - Searches the **current draft** after prior edits in the same session.\n"
    "  - Does not modify disk or the draft.\n\n"
    "Search modes:\n"
    "  - search_type=xpath (default): CSTQuery selector in `query`.\n"
    "  - search_type=simple: filters node_type, name, qualname, start_line, end_line.\n\n"
    "Results:\n"
    f"  - {SEARCH_IDENTIFIER_SECTION}\n"
    "  - Set include_code=true to return source snippets without a separate preview call.\n"
    "  - Set require_one=true when exactly one match is expected (edit target pin)."
)

_RETURN_VALUE = {
    "success": {
        "description": "Search completed on the session tree.",
        "data": {
            "session_id": "Session that was searched.",
            "file_path": "Project-relative path from the session.",
            "tree_id": "In-memory CST tree UUID (internal; same session tree).",
            "search_type": "xpath or simple.",
            "matches": (
                "List of match dicts: stable_id and node_ref (both CST UUID), type, name, lines."
            ),
            "total_matches": "Count before max_results truncation.",
            "returned_matches": "Count in matches after truncation.",
            "node_ref": "Present when require_one=true and exactly one match.",
        },
    },
    "error": {
        "description": "Search failed or constraint violated.",
        "code": "Stable error code (see error_cases).",
        "message": "Human-readable error message.",
        "details": "Optional diagnostic object.",
    },
}

_USAGE_EXAMPLES = [
    {
        "description": "Find a function in the open session draft, then edit",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "session_id": "<from universal_file_open>",
            "query": "FunctionDef[name='process_data']",
            "include_code": True,
        },
        "explanation": (
            "Runs only on the session tree. Use matches[0].node_ref (UUID) as node_id "
            "in universal_file_edit — not the int short_id from universal_file_preview."
        ),
    },
    {
        "description": "Search in a multi-file session",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "session_id": "<from universal_file_open>",
            "file_path": "ai_editor/commands/my_command.py",
            "query": "//FunctionDef",
        },
        "explanation": "file_path is required when more than one file is open.",
    },
]

_ERROR_CASES = {
    "SESSION_NOT_FOUND": {
        "description": "session_id is not registered (expired or server restarted).",
        "message": "Unknown session: {session_id}",
        "solution": "Call universal_file_open again.",
    },
    "UNKNOWN_FORMAT": {
        "description": (
            "Session is not sidecar Python (JSON/YAML/text or is_invalid fallback)."
        ),
        "message": (
            "universal_file_search applies only to an open Python sidecar edit session"
        ),
        "solution": (
            "Open a .py file with structural editing, or use fs_grep / fulltext_search "
            "for non-Python files."
        ),
    },
    "SESSION_FILE_PATH_REQUIRED": {
        "description": "Session has multiple open files but file_path was omitted.",
        "message": "file_path is required when the session has multiple open files",
        "solution": (
            "Pass file_path from multi_file_bundle in universal_file_open response."
        ),
    },
    "TREE_NOT_AVAILABLE": {
        "description": "Session has no loaded CST tree_id.",
        "message": "Session has no loaded CST tree.",
        "solution": "Re-open the file with universal_file_open.",
    },
    "INVALID_SEARCH": {
        "description": "Missing or invalid search parameters (e.g. xpath without query).",
        "message": "{validation detail}",
        "solution": "Provide query for xpath or at least one simple filter.",
    },
    "NoMatch": {
        "description": "require_one=true but selector matched 0 nodes in this tree.",
        "message": "Selector matched no nodes in the session tree",
        "solution": "Broaden query or confirm edits did not remove the target.",
    },
    "NonUniqueMatch": {
        "description": "require_one=true but selector matched >1 node.",
        "message": "Selector matched {total_matches} nodes; exactly one required",
        "solution": "Narrow the CSTQuery or omit require_one.",
    },
}

_BEST_PRACTICES = [
    "Always pass session_id from the same universal_file_open session you edit.",
    "Pass file_path when multi_file_bundle from open lists more than one file.",
    "Remember: searches the session draft tree only — not disk after uncommitted close.",
    "Use node_ref from matches as node_id in universal_file_edit (CST UUID, not preview short_id).",
    "Combine include_code=true with require_one=true for find-and-replace planning.",
]
