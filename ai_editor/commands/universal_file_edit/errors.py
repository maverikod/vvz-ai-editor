"""
ErrorCodes constants and error-construction helper for universal_file_edit commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult

SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
SESSION_FILE_PATH_REQUIRED = "SESSION_FILE_PATH_REQUIRED"
DRAFT_NOT_FOUND = "DRAFT_NOT_FOUND"
NESTED_BATCH_FORBIDDEN = "NESTED_BATCH_FORBIDDEN"
WRITE_FAILED = "WRITE_FAILED"
UNKNOWN_FORMAT = "UNKNOWN_FORMAT"
PARSE_ERROR = "PARSE_ERROR"
FILE_ALREADY_OPEN = "FILE_ALREADY_OPEN"
FORMAT_INVALID_ON_OPEN = "FORMAT_INVALID_ON_OPEN"
ANCHOR_MISMATCH = "ANCHOR_MISMATCH"
LINE_OUT_OF_RANGE = "LINE_OUT_OF_RANGE"
UNKNOWN_NODE_REF = "UNKNOWN_NODE_REF"
INVALID_OPERATION = "INVALID_OPERATION"
NOTHING_TO_UNDO = "NOTHING_TO_UNDO"
NOTHING_TO_REDO = "NOTHING_TO_REDO"
MODIFIED_NOT_WRITTEN = "MODIFIED_NOT_WRITTEN"
READ_ONLY_SESSION = "READ_ONLY_SESSION"

# These are the operation names exposed by ``universal_file_edit`` metadata.
# Keep remediation text tied to this catalog instead of leaking internal CST
# helper names such as ``replace_range`` into the public API.
PUBLIC_EDIT_OPERATION = "universal_file_edit"
PUBLIC_EDIT_OPERATION_TYPES = frozenset({"replace", "insert", "delete", "move"})


def public_edit_operation_remediation(operation_type: str = "replace") -> str:
    """Return remediation text using a callable public edit operation."""
    if operation_type not in PUBLIC_EDIT_OPERATION_TYPES:
        raise ValueError(f"Unsupported public edit operation: {operation_type}")
    return (
        f"Use type: {operation_type} with {PUBLIC_EDIT_OPERATION}; "
        "address the target with the current universal_file_preview data."
    )


def make_error(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a structured error dict for MCP command responses.

    Args:
        code: One of the ErrorCodes string constants.
        message: Human-readable description of the error.
        details: Optional mapping of additional diagnostic fields.

    Returns:
        Dict with keys success=False, code, message, and optional details.
    """
    result: Dict[str, Any] = {"success": False, "code": code, "message": message}
    if details:
        result["details"] = details
    return result


def error_result_for_edit(
    message: str,
    code: str,
    details: Optional[Dict[str, Any]] = None,
) -> ErrorResult:
    """Build ``ErrorResult`` with a string application error code.

    ``mcp_proxy_adapter`` types ``ErrorResult.code`` as int (JSON-RPC numeric
    codes); this codebase uses string codes for application errors.
    """
    return ErrorResult(message=message, code=cast(Any, code), details=details)


def error_result_from_make_error(err: Dict[str, Any]) -> ErrorResult:
    """Convert a ``make_error()`` dict into an ``ErrorResult``."""
    return ErrorResult(
        message=str(err["message"]),
        code=cast(Any, err["code"]),
        details=err.get("details"),
    )
