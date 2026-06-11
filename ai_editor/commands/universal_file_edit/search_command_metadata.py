"""
Metadata for universal_file_search command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_search_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_search."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
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
            "JSON/YAML/text sessions return UNSUPPORTED_FORMAT.\n"
            "  - Searches the **current draft** after prior edits in the same session.\n"
            "  - Does not modify disk or the draft.\n\n"
            "Search modes:\n"
            "  - search_type=xpath (default): CSTQuery selector in `query` "
            "(//FunctionDef, ClassDef[name='X'], :not(), numeric predicates).\n"
            "  - search_type=simple: filters node_type, name, qualname, start_line, end_line.\n\n"
            "Results:\n"
            "  - Each match includes `stable_id` and `node_ref` (same UUID — use as "
            "`node_id` in universal_file_edit).\n"
            "  - Set include_code=true to return source snippets without a separate preview call.\n"
            "  - Set require_one=true when exactly one match is expected (edit target pin).\n\n"
            "Not a substitute for:\n"
            "  - fulltext_search / fs_grep (project-wide text)\n"
            "  - cst_find_node / query_cst (legacy CST API outside edit session)\n"
            "  - universal_file_preview (hierarchical drill-down without selector)"
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID (schema consistency).",
                "type": "string",
                "required": True,
            },
            "session_id": {
                "description": (
                    "Active session from universal_file_open. Search runs on that session's "
                    "in-memory CST tree only."
                ),
                "type": "string",
                "required": True,
            },
            "search_type": {
                "description": "xpath (CSTQuery in query) or simple (field filters).",
                "type": "string",
                "enum": ["simple", "xpath"],
                "required": False,
                "default": "xpath",
            },
            "query": {
                "description": (
                    "CSTQuery selector for xpath mode. Supports // descendant traversal, "
                    "[name='foo'], [@start_line>=10], :not(...), :first. "
                    "See query_cst / cst_find_node metadata for full syntax."
                ),
                "type": "string",
                "required": False,
                "examples": [
                    "FunctionDef[name='process']",
                    "//FunctionDef",
                    "ClassDef[name='Widget']//FunctionDef",
                    "FunctionDef:not([name='__init__'])",
                ],
            },
            "node_type": {
                "description": "Simple search: LibCST type (FunctionDef, ClassDef, …).",
                "type": "string",
                "required": False,
            },
            "name": {
                "description": "Simple search: exact node name.",
                "type": "string",
                "required": False,
            },
            "qualname": {
                "description": "Simple search: exact qualname (e.g. Widget.method).",
                "type": "string",
                "required": False,
            },
            "start_line": {
                "description": "Simple search: minimum start_line (inclusive).",
                "type": "integer",
                "required": False,
            },
            "end_line": {
                "description": "Simple search: maximum end_line (inclusive).",
                "type": "integer",
                "required": False,
            },
            "include_code": {
                "description": "Include source code of each match in the response.",
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "require_one": {
                "description": (
                    "If true, fail when match count is not exactly 1; on success echo "
                    "node_ref at top level for direct edit."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "max_results": {
                "description": "Optional cap on returned matches (default: all).",
                "type": "integer",
                "required": False,
                "minimum": 1,
            },
        },
        "return_value": {
            "success": {
                "description": "Search completed on the session tree.",
                "data": {
                    "session_id": "Session that was searched.",
                    "file_path": "Project-relative path from the session.",
                    "tree_id": "In-memory CST tree UUID (internal; same session tree).",
                    "search_type": "xpath or simple.",
                    "matches": "List of match dicts with stable_id, node_ref, type, name, lines.",
                    "total_matches": "Count before max_results truncation.",
                    "returned_matches": "Count in matches after truncation.",
                    "node_ref": "Present when require_one=true and exactly one match.",
                },
            },
            "error": {
                "description": "Search failed or constraint violated.",
                "code": "Stable error code (see error_cases).",
            },
        },
        "usage_examples": [
            {
                "description": "Find a function in the open session draft, then edit",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "query": "FunctionDef[name='process_data']",
                    "include_code": True,
                },
                "explanation": (
                    "Runs only on the session tree. Use matches[0].node_ref as node_id "
                    "in universal_file_edit in the same session."
                ),
            },
            {
                "description": "Pin exactly one target for replace",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "query": "ClassDef[name='Widget']",
                    "require_one": True,
                },
                "explanation": (
                    "Fails with NoMatch or NonUniqueMatch if ambiguous. "
                    "On success response.node_ref is ready for edit."
                ),
            },
            {
                "description": "All methods inside a class in the current draft",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "query": "ClassDef[name='Widget']//FunctionDef",
                },
                "explanation": (
                    "Deep traversal within the session tree only — not project-wide."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": "session_id is not registered (expired or server restarted).",
                "solution": "Call universal_file_open again.",
            },
            "UNSUPPORTED_FORMAT": {
                "description": (
                    "Session is not sidecar Python (JSON/YAML/text or is_invalid fallback)."
                ),
                "solution": (
                    "Open a .py file with structural editing, or use fs_grep / fulltext_search "
                    "for non-Python files."
                ),
            },
            "TREE_NOT_AVAILABLE": {
                "description": "Session has no loaded CST tree_id.",
                "solution": "Re-open the file with universal_file_open.",
            },
            "INVALID_SEARCH": {
                "description": "Missing or invalid search parameters (e.g. xpath without query).",
                "solution": "Provide query for xpath or at least one simple filter.",
            },
            "NoMatch": {
                "description": "require_one=true but selector matched 0 nodes in this tree.",
                "solution": "Broaden query or confirm edits did not remove the target.",
            },
            "NonUniqueMatch": {
                "description": "require_one=true but selector matched >1 node.",
                "solution": "Narrow the CSTQuery or omit require_one.",
            },
        },
        "best_practices": [
            "Always pass session_id from the same universal_file_open session you edit.",
            "Remember: searches the session draft tree only — not disk after uncommitted close.",
            "Use node_ref from matches as node_id in universal_file_edit (stable_id).",
            "Combine include_code=true with require_one=true for find-and-replace planning.",
            "After universal_file_edit changes structure, re-run search in the same session.",
            "For project-wide symbol lookup use fulltext_search; then open file and search tree.",
            "Do not use cst_load_file tree_id here — this command is session-scoped only.",
        ],
    }
