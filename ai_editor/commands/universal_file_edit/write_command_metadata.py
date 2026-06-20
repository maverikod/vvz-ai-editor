"""
Metadata for universal_file_write command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from ai_editor.commands.universal_file_edit.workflow_brief import WORKFLOW_STEPS_TEXT


def get_universal_file_write_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_write."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Write Stage (C-012) for files open in a CA session workspace.\n\n"
            f"{WORKFLOW_STEPS_TEXT}\n"
            "write_mode=preview:\n"
            "  Canonical-export comparison (format-specific export vs Origin "
            "Snapshot bytes).\n"
            "  Returns local unified diff only. No quality validation and no "
            "upload to Code Analysis Server.\n\n"
            "write_mode=commit:\n"
            "  compare_session_to_origin; if equal — success no-op "
            "(unchanged=true, no CA RPC).\n"
            "  If diff — serialize to temp file, run quality tools (Python: "
            "black-parseable, flake8, mypy), then handler-specific validation "
            "(compile + docstrings for .py; JSON/YAML parse for structured files). "
            "On validation failure returns VALIDATION_ERROR with full error lists; "
            "origin and draft unchanged.\n"
            "  On success — upload canonical export via Upstream Client; on CA "
            "success refresh workspace Origin Snapshot with accepted bytes. On CA "
            "error — local origin and draft unchanged.\n\n"
            "session_id is the CA session id (same id passed to all "
            "universal_file_* commands).\n\n"
            "Sidecar (.py) legacy two-phase: when write_mode is omitted, the first "
            "call behaves as preview and sets a session lockfile; the second call "
            "with the same PID commits (same as explicit write_mode=commit)."
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
                    "Project-relative path. Required when the CA session holds "
                    "more than one open file; optional when exactly one file is open."
                ),
                "type": "string",
                "required": False,
            },
            "write_mode": {
                "description": (
                    "preview: local diff via canonical-export comparison, no CA "
                    "upload and no pre-write validation. commit: validate then "
                    "compare-and-upload to CA when content differs."
                ),
                "type": "string",
                "required": False,
                "default": "preview",
                "enum": ["preview", "commit"],
            },
            "format_python": {
                "description": (
                    "When true and the file is .py/.pyi/.pyw, run black on canonical "
                    "export before preview diff or CA upload (does not skip commit "
                    "validation when write_mode=commit)."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "verify_after_upload": {
                "description": (
                    "When true and commit uploaded content, download the file from "
                    "CA without lock and include ca_verify in the response."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Write completed without errors.",
                "data": {
                    "phase": (
                        "preview when write_mode=preview; committed on successful commit."
                    ),
                    "write_mode": "Echo of effective write mode.",
                    "has_changes": (
                        "True when canonical export differs from origin (preview or commit)."
                    ),
                    "unchanged": (
                        "True when commit found no diff vs origin (no CA upload)."
                    ),
                    "uploaded": (
                        "True when commit uploaded to CA and origin snapshot refreshed."
                    ),
                    "diff": "Unified diff string (preview or commit when has_changes).",
                    "format_python": "Echo of format_python request flag.",
                    "ca_verify": (
                        "Optional read-back verification payload when "
                        "verify_after_upload=true and upload succeeded."
                    ),
                    "session_id": "CA session id echoed from request.",
                    "project_id": "Project UUID echoed from request.",
                    "file_path": "Project-relative path of the written file.",
                },
                "example": {
                    "success": True,
                    "phase": "preview",
                    "write_mode": "preview",
                    "has_changes": True,
                    "unchanged": False,
                    "uploaded": False,
                    "diff": "--- origin\n+++ export\n...",
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
                "description": "Preview local diff vs origin snapshot",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<ca-session-id>",
                    "file_path": "src/example.py",
                    "write_mode": "preview",
                },
                "explanation": (
                    "Inspect diff placement only; no flake8/mypy/docstring checks."
                ),
            },
            {
                "description": "Commit after preview (validate then upload)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<ca-session-id>",
                    "file_path": "src/example.py",
                    "write_mode": "commit",
                },
                "explanation": (
                    "Runs pre-write validation on commit; uploads to CA when content "
                    "differs and validation passes."
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
                    "session_id is not registered locally or file_path missing for a "
                    "multi-file session."
                ),
                "message": "Unknown session: {session_id}",
                "solution": (
                    "Re-open the file with universal_file_open; supply file_path "
                    "when the session holds multiple files."
                ),
            },
            "SESSION_FILE_PATH_REQUIRED": {
                "description": (
                    "The CA session has multiple open files and file_path was omitted."
                ),
                "message": (
                    "file_path is required when the session has multiple open files"
                ),
                "solution": (
                    "Pass file_path from multi_file_bundle or close other files first."
                ),
            },
            "SESSION_REJECTED": {
                "description": "CA session id failed SessionGuard validation.",
                "message": "invalid CA session",
                "solution": "Create a new CA session and re-open the file.",
            },
            "VALIDATION_ERROR": {
                "description": (
                    "Pre-write validation failed on commit (quality tools and/or "
                    "handler validator). Temp file removed; origin and draft unchanged."
                ),
                "message": "Validation failed: {details}",
                "solution": (
                    "Fix reported flake8/mypy/docstring/syntax issues and retry commit."
                ),
            },
            "WRITE_FAILED": {
                "description": (
                    "Canonical export or preview generation failed before upload."
                ),
                "message": "{serialization or export error}",
                "solution": (
                    "Fix draft/session state; re-open if the session is corrupted."
                ),
            },
            "UPSTREAM_UPLOAD_FAILED": {
                "description": "CA rejected upload after local validation passed.",
                "message": "{upstream_error}",
                "solution": (
                    "Inspect upstream_error details, fix content or connectivity, "
                    "then retry commit or call universal_file_close."
                ),
            },
        },
        "best_practices": [
            "Always call write_mode=preview before commit to verify diff placement.",
            "Expect VALIDATION_ERROR on commit for Python docstring, flake8, or mypy issues.",
            "write_mode=commit with equal content returns unchanged=true without CA RPC.",
            "On upload failure, fix issues and retry commit or call universal_file_close.",
            "Supply file_path when the CA session has multiple open files.",
            "Use format_python only when black-formatted export is required before diff/upload.",
            "To discard uncommitted edits, call universal_file_close without commit.",
        ],
    }
