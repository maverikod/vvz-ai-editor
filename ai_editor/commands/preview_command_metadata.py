"""
Metadata for universal_file_preview command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_preview_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_preview.

    Args:
        cls: The command class (UniversalFilePreviewCommand).

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
            "Read-only structured preview of any project file node.\n\n"
            "Works without an edit session. Supports .py, .json, .yaml, .yml, .md, .txt,\n"
            "  .rst, .adoc, .jsonl, .ndjson. Does not modify files, DB, or tree sessions.\n\n"
            "Navigation model:\n"
            "  Omit node_ref — get the file root.\n"
            "  Pass a node_ref from a previous response — drill into that node.\n"
            "  Each block in the response carries its own node_ref for further drill-down.\n\n"
            "node_ref format by file type:\n"
            "  sidecar (.py)    — stable UUID (CST node identifier)\n"
            "  tree-temp (.json/.yaml/.yml/.jsonl/.ndjson) — JSON Pointer, e.g. /database/host\n"
            "  markdown (.md)   — dot-separated slug path from document root, e.g. intro.setup; "
            "root is ''\n"
            "  plain text (.txt, .rst, .adoc, …) — zero-based line index string, e.g. '3'\n\n"
            "selector parameter:\n"
            "  String slice (contains ':' or starts with '-'): '0:5', '-3:', '2:8'\n"
            "  list[int]: explicit block indices, e.g. [0, 2, 4]\n"
            "  list[str]: explicit block identifiers (node_ref values)\n"
            "  Omit: return first preview_lines blocks (default 20)\n\n"
            "Python full-text mode:\n"
            "  When the .py file has fewer lines than full_text_max_lines (default 200),\n"
            "  the entire source is returned as a single text block instead of the\n"
            "  structured CST rendering. Set full_text_max_lines=0 to disable.\n\n"
            "Edit session integration:\n"
            "  Pass session_id from universal_file_open to preview the current draft\n"
            "  (in-memory CST tree for sidecar, tree_temp_roots for tree-temp, draft file for text).\n"
            "  This session_id is unrelated to client session commands (session_create, …).\n\n"
            "One-shot preview (file not open in workspace):\n"
            "  When no editor bundle exists for (project_id, file_path), preview downloads file bytes from\n"
            "  Code Analysis Server via Upstream Client download_without_lock (C-023) without session_open_file\n"
            "  or CA lock. Content is previewed from a temporary in-memory/ephemeral file; no File Subtree is\n"
            "  created and no bundle registry entry is written. Optional session_id performs SessionGuard\n"
            "  PREVIEW touch only; it does not switch to workspace draft mode.\n"
            "  When the file is already open in the editor workspace, one-shot mode is rejected with\n"
            "  OPEN_FILE_USE_WORKSPACE_PREVIEW — pass session_id (CA id from universal_file_open) to preview\n"
            "  the workspace Edit Subdirectory draft instead (open-file preview mode, G-004/T-002)."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID. Required for both one-shot and open-file preview modes.",
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "file_path": {
                "description": "Project-relative literal path. Required. No globs.",
                "type": "string",
                "required": True,
                "examples": [
                    "ai_editor/commands/my_command.py",
                    "config/settings.yaml",
                ],
            },
            "node_ref": {
                "description": (
                    "Stable node identifier in the file handler's native format. "
                    "Omit for the file root (empty or whitespace-only string is treated "
                    "the same as omitted). Use a node_ref value from a previous response "
                    "to drill down."
                ),
                "type": "string",
                "required": False,
            },
            "selector": {
                "description": (
                    "Subset of the focus node's blocks. "
                    "String slice (e.g. '0:5', '-3:'), list of int indices, or list of node_ref strings. "
                    "Omit to get the first preview_lines blocks."
                ),
                "type": "string | list[int] | list[str]",
                "required": False,
            },
            "preview_lines": {
                "description": "Max blocks returned when selector is omitted. Default 20.",
                "type": "integer",
                "required": False,
                "default": 20,
            },
            "value_preview_len": {
                "description": "Max character length for inline scalar previews. Default 120.",
                "type": "integer",
                "required": False,
                "default": 120,
            },
            "full_text_max_lines": {
                "description": (
                    "Python handler only: return entire file as a text block when "
                    "line count is below this threshold. Default 200. Set to 0 to disable."
                ),
                "type": "integer",
                "required": False,
                "default": 200,
            },
            "session_id": {
                "description": (
                    "Optional CA session id. On one-shot preview (file not open): performs SessionGuard "
                    "PREVIEW validation when provided; does not read workspace draft. On open-file preview "
                    "(file already open in workspace): required — must match the ca_session_id that owns "
                    "the open bundle; previews the current draft in the Edit Subdirectory without CA lock "
                    "or session_view."
                ),
                "type": "string",
                "required": False,
            },
            "tree_id": {
                "description": "UUID of an existing in-memory TreeSession (legacy; prefer session_id).",
                "type": "string",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Preview returned without errors.",
                "data": {
                    "focus": "Metadata of the focus node: node_kind, node_ref, type, name, attributes, text.",
                    "blocks": "List of child block summaries, each with node_ref for drill-down.",
                    "total_blocks": "Total child count of the focus node (may exceed len(blocks) when selector limits output).",
                    "selector_applied": "The selector that was applied, or null when omitted.",
                },
                "example": {
                    "focus": {"node_kind": "mapping", "node_ref": "/database"},
                    "blocks": [{"node_kind": "scalar", "node_ref": "/database/host"}],
                    "total_blocks": 3,
                    "selector_applied": None,
                },
            },
            "error": {
                "description": "Preview failed.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Preview the root of a YAML file",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "config/settings.yaml",
                },
                "explanation": (
                    "Returns the top-level keys as blocks. "
                    "Each block has a node_ref (JSON Pointer) for drill-down."
                ),
            },
            {
                "description": "Drill into a nested YAML key",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "config/settings.yaml",
                    "node_ref": "/database",
                },
                "explanation": "Pass node_ref from a previous preview response to see the children of /database.",
            },
            {
                "description": "Preview a Python file (full-text for small files)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "ai_editor/commands/my_command.py",
                    "full_text_max_lines": 300,
                },
                "explanation": (
                    "Files under 300 lines are returned as a single text block. "
                    "Larger files return the CST structured rendering."
                ),
            },
            {
                "description": "One-shot preview of a file not open in the workspace",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "ai_editor/commands/my_command.py",
                },
                "explanation": (
                    "Downloads bytes from CA via download_without_lock without acquiring a lock or creating "
                    "a local File Subtree. Returns structured preview JSON with session_origin 'none'. "
                    "Omit session_id when the file is not open. If the file is already open, the command "
                    "returns OPEN_FILE_USE_WORKSPACE_PREVIEW — retry with session_id from universal_file_open."
                ),
            },
        ],
        "error_cases": {
            "UNKNOWN_EXTENSION": {
                "description": "File extension not supported by any preview handler.",
                "solution": "Use a supported extension: .py, .json, .yaml, .yml, .md, .txt, .rst, .adoc, .jsonl.",
            },
            "UNKNOWN_NODE_REF": {
                "description": "node_ref not found in the current file tree.",
                "solution": "Re-run preview without node_ref to get valid node_ref values from the current file state.",
            },
            "FILE_STRUCTURE_ERROR": {
                "description": "File could not be parsed (e.g. invalid JSON or YAML syntax).",
                "solution": "Fix the file syntax, or open it with universal_file_open which falls back to text mode.",
            },
            "GLOB_IN_FILE_PATH": {
                "description": "file_path contains glob characters (* ? [).",
                "solution": "Provide a single literal file path.",
            },
            "INVALID_SELECTOR_FORM": {
                "description": "Selector string does not contain ':' and does not start with '-'.",
                "solution": "Use slice syntax (e.g. '0:5', '-3:') or a list of indices/identifiers.",
            },
            "FILE_LOCKED": {
                "description": (
                    "File is locked by another universal_file_open edit session "
                    "(preview without session_id). universal_file_open returns PARSE_ERROR "
                    "for the same lock."
                ),
                "solution": (
                    "Pass the owning session_id from universal_file_open, or call "
                    "universal_file_close on that session."
                ),
            },
            "CONFLICTING_PARAMETERS": {
                "description": "Unknown or invalid session_id when resolving edit draft.",
                "solution": "Re-open the file with universal_file_open and use the new session_id.",
            },
            "HANDLER_ERROR": {
                "description": "Unexpected failure inside a preview handler.",
                "solution": "Retry; if persistent, check server logs and file content.",
            },
            "OPEN_FILE_USE_WORKSPACE_PREVIEW": {
                "description": (
                    "The file is already open in the editor workspace for this project_id and file_path. "
                    "One-shot upstream download is not used for open files."
                ),
                "solution": (
                    "Call universal_file_open first (or reuse existing open), then call universal_file_preview "
                    "with session_id set to the CA session id that owns the open bundle to preview the "
                    "workspace draft (open-file preview mode)."
                ),
            },
        },
        "best_practices": [
            "Call universal_file_preview before universal_file_edit to obtain valid node_ref values.",
            "For JSON/YAML: node_ref from preview is a JSON Pointer; pass it as json_pointer in edit operations, not node_id.",
            "For .md: node_ref is a section slug path from preview; pass it as node_ref in edit operations.",
            "For .txt/.rst/.adoc: node_ref is a zero-based line index; convert to 1-based start_line = int(node_ref) + 1 for edit.",
            "For Python: use full_text_max_lines=0 to force CST structured output and get stable UUID node_refs.",
            "Pass session_id to preview the draft after edits but before commit.",
            "Use selector='0:N' to cap the response size for large files.",
            "Use one-shot preview (project_id + file_path only) only when the file is not open in the "
            "workspace; if OPEN_FILE_USE_WORKSPACE_PREVIEW is returned, pass session_id for draft preview.",
        ],
    }
