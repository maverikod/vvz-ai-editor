"""
Metadata for universal_file_write command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_write_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_write.

    Args:
        cls: The command class (UniversalFileWriteCommand).

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
            "Write Stage (C-012) for files open in a CA session workspace.\n\n"
            "write_mode=preview:\n"
            "  Canonical-export comparison (format-specific export vs Origin "
            "Snapshot bytes).\n"
            "  Returns local unified diff only. No upload to Code Analysis Server.\n"
            "  Not yet implemented — current code returns NOT_IMPLEMENTED.\n\n"
            "write_mode=commit:\n"
            "  compare_session_to_origin; if equal — success no-op "
            "(unchanged=true, no CA RPC).\n"
            "  If diff — upload canonical export via Upstream Client; on CA success "
            "refresh workspace Origin Snapshot with accepted bytes. On CA error — "
            "local origin and draft unchanged.\n\n"
            "session_id is the CA session id (same id passed to all "
            "universal_file_* commands).\n\n"
            "In-session sidecar lockfile (legacy two-phase preview) is a local "
            "preview aid only; it is NOT a gate for CA upload RPC."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID. Required for CA upload RPC.",
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "session_id": {
                "description": (
                    "CA session id from session_create on Code Analysis Server; "
                    "required on every universal_file_* call."
                ),
                "type": "string",
                "required": True,
            },
            "file_path": {
                "description": (
                    "Project-relative path; required when session holds "
                    "multiple open files."
                ),
                "type": "string",
                "required": True,
            },
            "write_mode": {
                "description": (
                    "preview: local diff via canonical-export comparison, no CA "
                    "upload. commit: compare-and-upload to CA when content differs."
                ),
                "type": "string",
                "required": False,
                "default": "commit",
                "enum": ["preview", "commit"],
            },
        },
        "return_value": {
            "success": {
                "description": "Write completed without errors.",
                "data": {
                    "unchanged": (
                        "True when commit found no diff vs origin (no CA upload)."
                    ),
                    "uploaded": (
                        "True when commit uploaded to CA and origin snapshot refreshed."
                    ),
                    "session_id": "CA session id echoed from request.",
                    "project_id": "Project UUID echoed from request.",
                    "file_path": "Project-relative path of the written file.",
                },
                "example": {
                    "unchanged": True,
                    "uploaded": False,
                    "session_id": "<ca-session-id>",
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "src/example.py",
                },
            },
            "error": {
                "description": (
                    "Write failed; workspace origin snapshot and draft unchanged."
                ),
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Preview local diff (not yet implemented)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<ca-session-id>",
                    "file_path": "src/example.py",
                    "write_mode": "preview",
                },
                "explanation": (
                    "write_mode=preview returns a local unified diff only; no CA "
                    "upload. Current implementation returns NOT_IMPLEMENTED."
                ),
            },
            {
                "description": "Commit when content unchanged (no-op)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<ca-session-id>",
                    "file_path": "src/example.py",
                    "write_mode": "commit",
                },
                "explanation": (
                    "When canonical export matches origin, returns unchanged=true "
                    "and uploaded=false without any CA RPC."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": (
                    "session_id is not registered or file_path missing for a "
                    "multi-file session."
                ),
                "solution": (
                    "Re-open the file with universal_file_open; supply file_path "
                    "when the session holds multiple files."
                ),
            },
            "SESSION_REJECTED": {
                "description": "CA session id failed SessionGuard validation.",
                "solution": "Create a new CA session and re-open the file.",
            },
            "NOT_IMPLEMENTED": {
                "description": "write_mode=preview is not yet implemented.",
                "solution": "Use write_mode=commit or wait for preview support.",
            },
            "UPSTREAM_UPLOAD_FAILED": {
                "description": "CA rejected upload; origin and draft unchanged.",
                "solution": (
                    "Inspect upstream_error details, fix content or connectivity, "
                    "then retry write or call universal_file_close."
                ),
            },
        },
        "best_practices": [
            "Call write_mode=preview before commit to inspect diff.",
            (
                "write_mode=commit with equal content returns unchanged=true "
                "without CA RPC."
            ),
            "On upload failure, retry write or call universal_file_close.",
            "Supply file_path when the CA session has multiple open files.",
            "To discard uncommitted edits, call universal_file_close without commit.",
        ],
    }
