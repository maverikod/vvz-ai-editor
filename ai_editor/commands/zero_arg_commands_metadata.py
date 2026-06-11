"""
Metadata for zero-parameter health commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from ai_editor.commands.command_metadata_helpers import identity_fields


def health_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    return {
        **identity_fields(cls),
        "detailed_description": (
            "Returns server health, uptime, registered command count, proxy registration "
            "status, and queue dependency compatibility diagnostics."
        ),
        "parameters": {},
        "return_value": {
            "success": {
                "description": "Health payload with status, version, uptime, and components.",
                "data": {"status": "ok", "version": "1.0.6", "uptime": 12.5},
            }
        },
        "usage_examples": [
            {
                "description": "Check server health",
                "command": {},
                "explanation": "No parameters; returns health diagnostics.",
            }
        ],
        "error_cases": [],
        "best_practices": [
            "Use before long edit sessions to confirm queue dependencies are ready."
        ],
    }


def queue_health_command_metadata(cls: Type[Any]) -> Dict[str, Any]:
    schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
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
                "data": {"status": "ok", "queue_enabled": True},
            }
        },
        "usage_examples": [
            {
                "description": "Check queue subsystem",
                "command": {},
                "explanation": "No parameters.",
            }
        ],
        "error_cases": [],
        "best_practices": ["Call when queued commands fail to start."],
    }
