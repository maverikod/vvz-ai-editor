"""
Input schema for universal_file_preview (get_schema source of truth).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from ai_editor.commands.preview_config_defaults import (
    DEFAULT_FULL_TEXT_MAX_LINES,
    DEFAULT_PREVIEW_LINES,
    DEFAULT_PREVIEW_MAX_CHARS,
    DEFAULT_PREVIEW_VALUE_PREVIEW_LEN,
)


def get_universal_file_preview_schema() -> dict[str, Any]:
    """Return JSON Schema for universal_file_preview parameters."""
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "Project UUID. Use list_projects to discover valid project_id values."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Literal project-relative file path. Wildcards are not allowed."
                ),
            },
            "session_id": {
                "type": "string",
                "description": (
                    "CA session id from session_create / universal_file_open. "
                    "Required when the file is already open in the workspace "
                    "(open-file preview mode); optional for one-shot upstream preview."
                ),
            },
            "node_ref": {
                "type": "string",
                "description": (
                    "Node identifier for structural drill-down. Omit for file root. "
                    "Type depends on format — see command metadata table: marked-tree "
                    "formats use decimal string short_id (preview returns int); "
                    "legacy tree-temp JSON/YAML use JSON Pointer; plain text/jsonl use "
                    "zero-based line index string. Forbidden when file is invalid "
                    "(use preview_offset line pagination)."
                ),
            },
            "selector": {
                "description": (
                    "Subset of focus blocks: slice string ('0:5', '-3:'), "
                    "list of int indices, or list of node_ref strings. "
                    "Only in structural (parseable) mode."
                ),
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "array",
                        "items": {
                            "oneOf": [{"type": "integer"}, {"type": "string"}]
                        },
                    },
                ],
            },
            "preview_lines": {
                "type": "integer",
                "default": DEFAULT_PREVIEW_LINES,
                "description": (
                    "Structural mode: max blocks returned when selector is omitted. "
                    "Invalid/fallback (plain-text) mode: max source lines in the "
                    "visible window. Default from server config "
                    f"({DEFAULT_PREVIEW_LINES})."
                ),
            },
            "value_preview_len": {
                "type": "integer",
                "default": DEFAULT_PREVIEW_VALUE_PREVIEW_LEN,
                "description": (
                    "Max character length for inline scalar previews in structural "
                    f"mode. Default {DEFAULT_PREVIEW_VALUE_PREVIEW_LEN}."
                ),
            },
            "full_text_max_lines": {
                "type": "integer",
                "default": DEFAULT_FULL_TEXT_MAX_LINES,
                "description": (
                    "Marked-tree formats (.py, .json, .yaml, .md, …): when line "
                    "count is below this threshold, return annotated full source as "
                    "one inline text block instead of drilling the tree. Set 0 to "
                    f"disable. Default {DEFAULT_FULL_TEXT_MAX_LINES}."
                ),
            },
            "max_chars": {
                "type": "integer",
                "default": DEFAULT_PREVIEW_MAX_CHARS,
                "description": (
                    "Invalid/fallback plain-text mode: optional cap on characters "
                    "within one visible window (truncates with …). Default from "
                    f"server config ({DEFAULT_PREVIEW_MAX_CHARS})."
                ),
            },
            "preview_offset": {
                "type": "integer",
                "default": 0,
                "description": (
                    "Invalid/fallback plain-text mode: zero-based line index of the "
                    "first source line to return. Use preview_next_offset from a "
                    "prior response for the next page. Ignored in structural mode "
                    "(use node_ref / selector instead)."
                ),
            },
            "tree_id": {
                "type": "string",
                "description": (
                    "Legacy in-memory TreeSession UUID. Prefer session_id."
                ),
            },
        },
        "required": ["project_id", "file_path"],
        "additionalProperties": False,
    }
