"""
Metadata for universal_file_close command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_close_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_close.

    Args:
        cls: The command class (UniversalFileCloseCommand).

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
            "Close Stage (C-013): end editing for one file in a CA session and "
            "clean up workspace artefacts.\n\n"
            "The required `session_id` is the **CA session id** — the same value "
            "the agent obtains from Code Analysis Server `session_create`. It is "
            "passed to every universal_file_* command in the thin workflow. This is "
            "**not** the editor DB client-session id and there is **no** separate "
            "`session_close_file` MCP command on the AI Editor; CA unlock runs "
            "inside this command via the upstream client.\n\n"
            "universal_file_close is the final step in the universal file edit workflow:\n"
            "  1. universal_file_open  — lock+download (or upload+lock); workspace draft\n"
            "  2. universal_file_preview — obtain node_ref values\n"
            "  3. universal_file_edit  — apply operations to the in-memory draft\n"
            "  4. universal_file_write — preview diff, then commit to disk\n"
            "  5. universal_file_close — CA unlock + workspace cleanup  (THIS COMMAND)\n\n"
            "Close orchestration per call:\n"
            "  1. Best-effort CA unlock via `CodeAnalysisClient.unlock_session_file` "
            "(CA RPC `session_close_file`).\n"
            "     Unlock failure (CA session NOT_FOUND, file not locked, broken "
            "session) does **not** abort close — Session Guard permits terminating "
            "close (C-015) and local cleanup always continues.\n"
            "  2. Format-group draft/sidecar reconciliation (see below).\n"
            "  3. Remove the File Subtree for `(project_id, file_path)` under "
            "`{workspace_root}/{session_id}/` (origin snapshot + edit subdirs).\n"
            "  4. When this was the last open file in the CA session, remove the "
            "Editor Session Directory `{workspace_root}/{session_id}/`.\n\n"
            "Multi-file CA sessions: one file closes per call. Pass `file_path` when "
            "more than one file is open in the same `session_id`; omit it when exactly "
            "one file is open. The response lists `remaining_open_files` and "
            "`session_retained` until the last file is closed.\n\n"
            "Cleanup behavior by file type:\n\n"
            "Python (.py):\n"
            "  Verifies the sidecar SHA-256 against the source file. If they match,\n"
            "  the sidecar is left intact for the next session. If they differ (e.g.\n"
            "  the file was modified externally), the sidecar is rebuilt from source.\n"
            "  draft_rebuilt=true is returned when the sidecar had to be rebuilt.\n\n"
            "JSON/YAML (.json, .yaml, .yml):\n"
            "  Frees the in-memory tree. If the draft differs from disk (uncommitted "
            "edits), the draft is rebuilt from the on-disk source — uncommitted "
            "changes are discarded.\n\n"
            "text (.md, .txt, .rst, .adoc, …):\n"
            "  Uncommitted edits in the workspace draft are discarded.\n\n"
            "Uncommitted edits (universal_file_edit without universal_file_write commit)\n"
            "are silently discarded on close. Always commit before closing if changes matter."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID. Required for CA unlock (C-023) and workspace "
                    "path resolution. Use list_projects to discover valid values."
                ),
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "session_id": {
                "description": (
                    "CA session id (required; same id as session_create on "
                    "Code Analysis Server). Not returned by universal_file_open — "
                    "the agent supplies it for the whole workflow."
                ),
                "type": "string",
                "required": True,
            },
            "file_path": {
                "description": (
                    "Project-relative path. Required when the CA session has more "
                    "than one open file (see multi_file_bundle from open). Optional "
                    "when exactly one file is open."
                ),
                "type": "string",
                "required": False,
                "examples": ["config/settings.yaml"],
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "File closed; CA unlock attempted; workspace subtree removed."
                ),
                "data": {
                    "success": "Always True on success.",
                    "draft_rebuilt": (
                        "True when the sidecar or draft was rebuilt from source "
                        "(sidecar/tree-temp only)."
                    ),
                    "session_id": "CA session id echoed from the request.",
                    "project_id": "Project UUID echoed from the request.",
                    "file_path": "Project-relative path of the closed file.",
                    "closed_file_path": "Same as file_path; path removed from the bundle.",
                    "remaining_open_files": (
                        "Sorted list of project-relative paths still open in the "
                        "CA session after this close (empty when last file closed)."
                    ),
                    "session_retained": (
                        "True when other files remain open in the same CA session."
                    ),
                    "unlock_ok": (
                        "True when upstream CA unlock succeeded; False on best-effort "
                        "failure — local cleanup still completed."
                    ),
                    "workspace_subtree_removed": (
                        "True when the File Subtree for this file was removed."
                    ),
                    "session_dir_removed": (
                        "True when the Editor Session Directory was removed because "
                        "this was the last open file."
                    ),
                },
                "example": {
                    "success": True,
                    "draft_rebuilt": False,
                    "session_id": "4b4255c7-6a0c-4396-94c6-6f2bcf297912",
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "config/settings.yaml",
                    "closed_file_path": "config/settings.yaml",
                    "remaining_open_files": [],
                    "session_retained": False,
                    "unlock_ok": True,
                    "workspace_subtree_removed": True,
                    "session_dir_removed": True,
                },
            },
            "error": {
                "description": "Close could not proceed before cleanup.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Close the only open file in a CA session",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<CA session_create id>",
                },
                "explanation": (
                    "After universal_file_write (commit), close releases the CA lock, "
                    "removes the workspace File Subtree, and deletes the session "
                    "directory when this was the last file."
                ),
            },
            {
                "description": "Close one file in a multi-file CA session",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<CA session_create id>",
                    "file_path": "ai_editor/commands/foo.py",
                },
                "explanation": (
                    "file_path is required when multiple files are open. "
                    "remaining_open_files lists paths still held in the session."
                ),
            },
            {
                "description": "Close when CA unlock fails (best-effort success)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<CA session_create id>",
                    "file_path": "config/settings.yaml",
                },
                "explanation": (
                    "Success still returns when unlock_session_file returns False "
                    "(unlock_ok=False). Workspace subtree removal and bundle release "
                    "completed; do not retry close solely because unlock failed."
                ),
            },
        ],
        "error_cases": {
            "SESSION_REJECTED": {
                "description": (
                    "session_id is missing or empty after parameter normalization "
                    "(Session Guard REJECT on CLOSE)."
                ),
                "message": "session_id is required for universal_file_close",
                "solution": "Pass the CA session id from session_create.",
            },
            "SESSION_NOT_FOUND": {
                "description": (
                    "No editor bundle entry for session_id, or file_path does not "
                    "match an open file in that CA session (file not open locally)."
                ),
                "message": "Unknown session: {session_id}",
                "solution": (
                    "Verify session_id and file_path; open the file with "
                    "universal_file_open first. After server restart local bundles "
                    "are lost — use terminating close semantics only when a zombie "
                    "workspace needs cleanup."
                ),
            },
            "SESSION_FILE_PATH_REQUIRED": {
                "description": (
                    "The CA session has more than one open file but file_path was "
                    "omitted."
                ),
                "message": (
                    "file_path is required when the session has multiple open files"
                ),
                "solution": (
                    "Pass the project-relative file_path to close, or close each "
                    "remaining path from remaining_open_files until the session ends."
                ),
            },
        },
        "best_practices": [
            "Always close each opened file when done — workspace subtrees are not "
            "reclaimed until close runs.",
            "In multi-file CA sessions, pass file_path on every close call.",
            "unlock_ok=False is informational only — local workspace cleanup still "
            "runs; do not retry close solely because unlock failed.",
            "Call close even when write failed — it cleans up partial workspace drafts.",
            "Do not call editor session_close_file — CA unlock is internal to this command.",
            "Calling close without commit discards uncommitted draft edits (cancel workflow).",
        ],
    }
