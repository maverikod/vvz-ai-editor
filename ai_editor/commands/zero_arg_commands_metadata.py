"""
Metadata for zero-parameter health commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from ai_editor.commands.command_metadata_helpers import identity_fields
from ai_editor.commands.editor_info_content import (
    EDITOR_INFO_MARKDOWN,
    GUIDE_VERSION,
)


def health_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        **identity_fields(cls),
        "detailed_description": (
            "Returns server health, uptime, registered command count, proxy registration "
            "status, and queue dependency compatibility diagnostics. "
            "For file edit workflow call command `info`; for quick start see server help."
        ),
        "parameters": {},
        "return_value": {
            "success": {
                "description": "Health payload with status, version, uptime, and components.",
                "data": {
                    "status": "Server status string (typically ok).",
                    "version": "Package version string.",
                    "uptime": "Seconds since server start.",
                },
                "example": {"status": "ok", "version": "1.0.17", "uptime": 12.5},
            },
            "error": {
                "description": "Health check failed unexpectedly.",
                "code": "HANDLER_ERROR",
                "message": "Human-readable failure description.",
            },
        },
        "usage_examples": [
            {
                "description": "Check server health",
                "command": {},
                "explanation": "No parameters; returns health diagnostics.",
            }
        ],
        "error_cases": {},
        "best_practices": [
            "Use before long edit sessions to confirm queue dependencies are ready.",
            "Call `info` before the first file edit session for the full workflow guide.",
        ],
    }


def info_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        **identity_fields(cls),
        "detailed_description": EDITOR_INFO_MARKDOWN,
        "parameters": {},
        "return_value": {
            "success": {
                "description": "Structured editor guide with markdown and examples.",
                "data": {
                    "guide_version": "Guide semver string.",
                    "summary": "One-line lifecycle summary.",
                    "markdown": "Full prose guide (same as detailed_description).",
                    "lifecycle": "Ordered list of workflow steps.",
                    "registered_commands": "MCP commands available in thin server.",
                    "format_groups": "sidecar / tree-temp / text mapping.",
                    "examples": "JSON parameter examples per step.",
                    "docs": "Paths to repo documentation files.",
                },
                "example": {
                    "guide_version": GUIDE_VERSION,
                    "summary": "CA session_create → open → preview ↔ edit → write → close",
                },
            },
            "error": {
                "description": "Guide could not be returned.",
                "code": "HANDLER_ERROR",
                "message": "Human-readable failure description.",
            },
        },
        "usage_examples": [
            {
                "description": "Load full file edit workflow guide",
                "command": {},
                "explanation": (
                    "No parameters. Returns markdown, lifecycle steps, format groups, "
                    "and JSON examples for universal_file_* commands."
                ),
            }
        ],
        "error_cases": {},
        "best_practices": [
            "Call `info` once before the first edit task in a session.",
            "Use `help(command=...)` for parameter schemas after reading the guide.",
            "Server list card and server help are brief; this command is the full reference.",
        ],
    }


def queue_health_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    return {
        **identity_fields(cls),
        "detailed_description": (
            "Inspects the global queue manager when enabled and reports dependency "
            "compatibility alongside queue readiness."
        ),
        "parameters": {},
        "return_value": {
            "success": {
                "description": "Queue health and dependency compatibility payload.",
                "data": {
                    "status": "Queue subsystem status.",
                    "queue_enabled": "Whether the global queue manager is enabled.",
                },
                "example": {"status": "ok", "queue_enabled": True},
            },
            "error": {
                "description": "Queue health check failed.",
                "code": "HANDLER_ERROR",
                "message": "Human-readable failure description.",
            },
        },
        "usage_examples": [
            {
                "description": "Check queue subsystem",
                "command": {},
                "explanation": "No parameters.",
            }
        ],
        "error_cases": {},
        "best_practices": ["Call when queued commands fail to start."],
    }
