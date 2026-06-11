"""
Metadata for universal_file_move_nodes command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_move_nodes_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_move_nodes.

    Args:
        cls: The command class (UniversalFileMoveNodesCommand).

    Returns:
        Metadata dict with description, parameters, examples, errors.
    """
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Move a contiguous block of sibling CST nodes to a new position within\n"
            "the same file edit session.\n\n"
            "universal_file_move_nodes fits into the universal file edit workflow:\n"
            "  1. universal_file_open  — open a .py file, get session_id\n"
            "  2. universal_file_preview — obtain node_ref UUIDs\n"
            "  3. universal_file_move_nodes — move nodes to target position\n"
            "  4. universal_file_write — preview diff; second call commits to disk\n"
            "  5. universal_file_close — release the session\n\n"
            "Supports Python (.py) sidecar sessions only.\n\n"
            "Safety:\n"
            "  All mutations happen on a temporary .py.tmp copy of the source file.\n"
            "  The original file is replaced atomically only after the result passes\n"
            "  compile() validation. On failure, the temp copy is deleted and the\n"
            "  original session is left untouched.\n\n"
            "Target addressing (mutually exclusive):\n"
            "  target_node_id + position before|after — sibling-relative insert\n"
            "  parent_node_id + position first|last   — container insert\n"
            "  __root__ as parent_node_id targets the module level.\n\n"
            "Node ordering:\n"
            "  Caller-supplied order in source_node_ids is ignored.\n"
            "  Nodes are moved in their original source order (by start_line)."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID. Use list_projects to discover valid project_id values.",
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "session_id": {
                "description": (
                    "Active session UUID returned by universal_file_open. "
                    "Sessions are invalidated on server restart."
                ),
                "type": "string",
                "required": True,
                "examples": ["4b4255c7-6a0c-4396-94c6-6f2bcf297912"],
            },
            "source_node_ids": {
                "description": (
                    "Stable UUIDs of CST nodes to move (from universal_file_preview node_ref). "
                    "All nodes must exist in the current draft tree. "
                    "Caller-supplied order is ignored; nodes are moved in source order (by start_line)."
                ),
                "type": "array",
                "required": True,
                "items": {"type": "string"},
                "examples": [["<uuid-1>", "<uuid-2>"]],
            },
            "target_node_id": {
                "description": (
                    "Stable UUID of the sibling anchor node. "
                    "Block is inserted before or after this node (controlled by position). "
                    "Mutually exclusive with parent_node_id."
                ),
                "type": "string",
                "required": False,
                "examples": ["<anchor-uuid>"],
            },
            "parent_node_id": {
                "description": (
                    "Stable UUID of the container node. "
                    "Block is inserted as first or last child (controlled by position). "
                    "Use __root__ for module level. "
                    "Mutually exclusive with target_node_id."
                ),
                "type": "string",
                "required": False,
                "examples": ["__root__", "<class-uuid>"],
            },
            "position": {
                "description": (
                    "Insertion position. "
                    "With target_node_id: before or after. "
                    "With parent_node_id: first or last. "
                    "Default: after (or last when no anchor is specified)."
                ),
                "type": "string",
                "required": False,
                "enum": ["before", "after", "first", "last"],
                "default": "after",
            },
        },
        "return_value": {
            "success": {
                "description": "Nodes moved successfully; temp file validated and committed.",
                "data": {
                    "success": "Always True on success.",
                    "updated": "True when the draft was modified.",
                    "moved": "Number of nodes that were moved.",
                },
                "example": {"success": True, "updated": True, "moved": 3},
            },
            "error": {
                "description": "Move rejected; original session is untouched.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description of what failed.",
                "details": "Optional dict with node ids or syntax error detail.",
            },
        },
        "usage_examples": [
            {
                "description": "Move a function before another function (sibling-relative)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "source_node_ids": ["<uuid-of-helper-func>"],
                    "target_node_id": "<uuid-of-main-func>",
                    "position": "before",
                },
                "explanation": (
                    "Open .py with universal_file_open, run universal_file_preview to get "
                    "node_ref UUIDs, then call move_nodes. "
                    "Follow with universal_file_write to commit."
                ),
            },
            {
                "description": "Move a block of statements to end of module",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "source_node_ids": ["<uuid-1>", "<uuid-2>"],
                    "parent_node_id": "__root__",
                    "position": "last",
                },
                "explanation": (
                    "Use parent_node_id=__root__ with position=last to append to module level. "
                    "source_node_ids order does not matter; nodes are placed in their original source order."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": "The session_id is not registered on the server.",
                "message": "Unknown session: {session_id}",
                "solution": "Open a new session with universal_file_open. Sessions are lost on server restart.",
            },
            "STALE_NODE_ID": {
                "description": "One or more source_node_ids not found in the current draft tree.",
                "message": "Node not found: {node_id}",
                "solution": "Re-call universal_file_preview with session_id to obtain fresh node_ref values.",
            },
            "INVALID_OPERATION": {
                "description": (
                    "Move rejected: both target_node_id and parent_node_id supplied, "
                    "non-sidecar session, structural error, or compile() validation failed."
                ),
                "message": "Move produced invalid Python: SyntaxError at line N: ...",
                "solution": (
                    "Check that the move is structurally valid (e.g. not moving a class method "
                    "to module level without adjusting indentation). "
                    "Inspect syntax_error in details for line/column information."
                ),
            },
            "FILE_NOT_FOUND": {
                "description": "Source file disappeared between open and move.",
                "message": "File not found: {path}",
                "solution": "Close the session and re-open the file.",
            },
            "WRITE_FAILED": {
                "description": "Failed to create the temp copy or commit the renamed files.",
                "message": "Write failed: {exc}",
                "solution": "Check disk space and permissions under the project root.",
            },
        },
        "best_practices": [
            "Call universal_file_preview before universal_file_move_nodes to obtain valid node_ref UUIDs.",
            "Use target_node_id + before|after for sibling-relative placement.",
            "Use parent_node_id + first|last (or __root__) for container placement.",
            "Do not supply both target_node_id and parent_node_id in the same call.",
            "After move_nodes, call universal_file_preview with session_id to verify the new tree layout before writing.",
            "Call universal_file_write after move to commit changes to disk.",
            "The source_node_ids order in the request is irrelevant; nodes are placed in their original source order.",
            "Only Python (.py) sidecar sessions are supported; JSON/YAML and text sessions are rejected.",
        ],
    }
