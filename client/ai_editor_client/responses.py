"""Parse JSON-RPC command envelopes from ai-editor-server."""

from __future__ import annotations

from typing import Any, Dict

from ai_editor_client.exceptions import ClientValidationError


def command_error_code(data: Dict[str, Any]) -> str:
    """Return domain or JSON-RPC error code from a failed command response."""
    if data.get("success") is True:
        return ""
    top = data.get("code")
    if top is not None and str(top).strip():
        return str(top).strip()
    err = data.get("error")
    if isinstance(err, dict):
        nested = err.get("code")
        if nested is not None:
            return str(nested).strip()
    if isinstance(err, str) and err.strip():
        return err.strip()
    return ""


def unwrap_command_result(
    data: Dict[str, Any],
    *,
    session_not_found_type: type[ClientValidationError] | None = None,
) -> Dict[str, Any]:
    """Return success ``data`` dict or raise :class:`ClientValidationError`."""
    if data.get("success"):
        inner = data.get("data")
        return inner if isinstance(inner, dict) else data
    code = command_error_code(data)
    message = data.get("message")
    err = data.get("error")
    if message is None and isinstance(err, dict):
        message = err.get("message")
    if message is None:
        message = str(data)
    if code == "SESSION_NOT_FOUND" and session_not_found_type is not None:
        raise session_not_found_type(message, field="session_id", details=data)
    raise ClientValidationError(message, field="command", details=data)
