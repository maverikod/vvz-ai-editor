"""
Metadata for universal_file_preview command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from ai_editor.commands.command_metadata_helpers import build_command_metadata
from ai_editor.commands.identifier_types_reference import PREVIEW_IDENTIFIER_SECTION


def get_universal_file_preview_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_preview."""
    return build_command_metadata(
        cls,
        detailed_description=_DETAILED_DESCRIPTION,
        usage_examples=_USAGE_EXAMPLES,
        error_cases=_ERROR_CASES,
        return_value=_RETURN_VALUE,
        best_practices=_BEST_PRACTICES,
    )


_DETAILED_DESCRIPTION = (
    "Read-only structured preview of any project file node.\n\n"
    "Works without an edit session. Supports .py, .json, .yaml, .yml, .md, .txt,\n"
    ".rst, .adoc, .jsonl, .ndjson. Does not modify files, DB, or tree sessions.\n\n"
    "Two addressing modes (mutually exclusive):\n"
    "  **Structural (parseable source):** omit preview_offset; use node_ref and/or "
    "selector to navigate the file tree.\n"
    "  **Plain-text fallback (parse errors or line-based text):** omit node_ref and "
    "selector; use preview_lines (window size in **lines**), preview_offset (line "
    "index), and optional max_chars. Response includes preview_total_lines, "
    "preview_has_more, preview_next_offset.\n\n"
    "Navigation (structural mode):\n"
    "  Omit node_ref — file root.\n"
    "  Pass node_ref from a previous response — drill into that node.\n"
    "  Each block carries its own node_ref for further drill-down.\n\n"
    f"{PREVIEW_IDENTIFIER_SECTION}\n"
    "selector parameter (structural mode only):\n"
    "  String slice: '0:5', '-3:', '2:8'\n"
    "  list[int]: explicit block indices\n"
    "  list[str]: explicit block node_ref values\n"
    "  Omit: first preview_lines blocks (default 20)\n\n"
    "full_text_max_lines (marked-tree formats):\n"
    "  When the file has fewer lines than this threshold (default 200), annotated "
    "full source may be returned as one text block instead of a structural tree. "
    "Set 0 to disable.\n\n"
    "Invalid / degraded preview:\n"
    "  On syntax errors the command **succeeds** with focus.is_invalid=true, "
    "focus.text showing a line window of raw source, and mode_notice describing "
    "line-based fallback. The full file is never dumped when preview_lines is "
    "smaller than the file.\n\n"
    "Edit session integration:\n"
    "  Pass session_id to preview the workspace draft (CST sidecar, tree_temp, or "
    "text draft).\n\n"
    "One-shot preview (file not open):\n"
    "  project_id + file_path only — downloads via CA download_without_lock into a "
    "temporary file. If the file is already open, returns "
    "OPEN_FILE_USE_WORKSPACE_PREVIEW — retry with session_id."
)

_RETURN_VALUE = {
    "success": {
        "description": "Preview returned without errors.",
        "data": {
            "focus": (
                "Focus node: node_kind, node_ref (int short_id, JSON Pointer, line index, "
                "or empty string when is_invalid), type, name, attributes, optional text."
            ),
            "blocks": "Child block summaries with node_ref for drill-down.",
            "total_blocks": "Total child count (may exceed len(blocks) when selector caps output).",
            "selector_applied": "Selector echoed back, or null when omitted.",
            "mode_notice": "Explains structural vs line-based fallback mode.",
            "preview_total_lines": (
                "Plain-text fallback only: total lines in source file."
            ),
            "preview_line_offset": "Plain-text fallback: line index of window start.",
            "preview_lines_returned": "Plain-text fallback: lines in focus.text window.",
            "preview_has_more": "Plain-text fallback: true when more lines exist.",
            "preview_next_offset": "Plain-text fallback: next preview_offset for pagination.",
            "preview_total_chars": "Character length of focus.text in current window.",
            "tree_id": "Present when session_origin is command_created.",
        },
        "example": {
            "focus": {
                "node_kind": "mapping",
                "node_ref": 1,
                "is_invalid": False,
            },
            "blocks": [{"node_kind": "scalar", "node_ref": 2}],
            "total_blocks": 3,
            "selector_applied": None,
            "mode_notice": "Structural preview (identifier-based navigation).",
        },
    },
    "error": {
        "description": "Preview failed before or during navigation.",
        "code": "Stable error code (see error_cases).",
        "message": "Human-readable description.",
        "details": "Optional diagnostic object (file_path, node_ref, …).",
    },
}

_USAGE_EXAMPLES = [
    {
        "description": "Preview the root of a YAML file",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "file_path": "config/settings.yaml",
        },
        "explanation": (
            "Returns top-level keys as blocks with integer node_ref values for drill-down."
        ),
    },
    {
        "description": "Drill into a nested node (marked-tree int id)",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "file_path": "config/settings.yaml",
            "node_ref": "2",
        },
        "explanation": "Pass node_ref from a previous preview response.",
    },
    {
        "description": "Paginate invalid JSON as plain text by lines",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "file_path": "broken.json",
            "preview_lines": 20,
            "preview_offset": 0,
        },
        "explanation": (
            "Do not pass node_ref on invalid files. Use preview_next_offset from the "
            "response for subsequent pages."
        ),
    },
    {
        "description": "One-shot preview when file is not open",
        "command": {
            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
            "file_path": "ai_editor/commands/my_command.py",
        },
        "explanation": (
            "Downloads from CA without lock. If OPEN_FILE_USE_WORKSPACE_PREVIEW is "
            "returned, pass session_id from universal_file_open."
        ),
    },
]

_ERROR_CASES = {
    "UNKNOWN_EXTENSION": {
        "description": "File extension not supported by any preview handler.",
        "message": "Unsupported file extension: {suffix}",
        "solution": (
            "Use .py, .json, .yaml, .yml, .md, .txt, .rst, .adoc, .jsonl, or .ndjson."
        ),
    },
    "UNKNOWN_NODE_REF": {
        "description": "node_ref not found in the current file tree.",
        "message": "Unknown node_ref: {node_ref}",
        "solution": "Re-run preview without node_ref to refresh valid node_ref values.",
    },
    "REQUIRES_LINE_ADDRESSING": {
        "description": (
            "File has parse errors but caller used node_ref or selector (structural "
            "addressing)."
        ),
        "message": "File has parse errors. Use line-based preview pagination …",
        "solution": (
            "Omit node_ref and selector; use preview_offset (line index) and "
            "preview_lines at file root."
        ),
    },
    "REQUIRES_IDENTIFIER_ADDRESSING": {
        "description": (
            "File parsed successfully but caller used preview_offset > 0 (line "
            "pagination)."
        ),
        "message": "File parsed successfully. Use identifier-based preview …",
        "solution": "Use node_ref / selector from a prior structural response.",
    },
    "INVALID_SELECTOR_FORM": {
        "description": "Selector string is not a valid slice form.",
        "message": "Invalid selector form: {selector}",
        "solution": "Use '0:5', '-3:', or a list of indices/identifiers.",
    },
    "CONFLICTING_PARAMETERS": {
        "description": "Mutually exclusive preview parameters (e.g. tree_id with session_id).",
        "message": "{conflict detail}",
        "solution": "Use session_id only; omit tree_id for open sessions.",
    },
    "OPEN_FILE_USE_WORKSPACE_PREVIEW": {
        "description": "File is open in workspace; one-shot download is not used.",
        "message": "File is open; use workspace preview with session_id",
        "solution": "Pass session_id from universal_file_open.",
    },
    "SESSION_NOT_FOUND": {
        "description": "session_id failed SessionGuard PREVIEW validation.",
        "message": "CA session not found or invalid: {session_id}",
        "solution": "Create a CA session via session_create and re-open the file.",
    },
    "UPSTREAM_ERROR": {
        "description": "One-shot preview: CA download_without_lock failed.",
        "message": "{upstream error}",
        "solution": "Verify file_path and CA connectivity.",
    },
    "VALIDATION_ERROR": {
        "description": "Parameter validation failed before preview execution.",
        "message": "{ValidationError message}",
        "solution": "Fix parameters per get_schema() and retry.",
    },
    "HANDLER_ERROR": {
        "description": "Unexpected failure inside preview orchestration.",
        "message": "{handler error}",
        "solution": "Retry; check server logs and file content.",
    },
}

_BEST_PRACTICES = [
    "Call universal_file_preview before universal_file_edit to obtain valid node_ref values.",
    "Marked-tree (.py/.json/.yaml/.md): response node_ref is integer short_id — pass as string in the next request.",
    "universal_file_search returns UUID stable_id (not short_id); use as node_id in edit.",
    "On invalid files: never pass node_ref; paginate with preview_offset (lines) and preview_lines.",
    "Re-fetch preview after each edit before relying on node_ref or line numbers.",
    "Use full_text_max_lines=0 to force structural tree output on small files.",
    "Pass session_id to preview the draft after edits but before commit.",
    "Use selector='0:N' to cap block count in structural mode for large nodes.",
]
