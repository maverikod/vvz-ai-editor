"""
Load per-command JSON schema from the running server via ``help`` (cmdname).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from ai_editor_client.exceptions import ClientValidationError


def parse_schema_from_help_payload(
    payload: Dict[str, Any], *, command_name: str
) -> Dict[str, Any]:
    """Extract ``get_schema()``-style dict from ``help`` JSON-RPC result."""
    if not payload.get("success"):
        raise ClientValidationError(
            f"{command_name}: help returned success=false: {payload!r}",
            field="help",
            details={"payload": payload},
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ClientValidationError(
            f"{command_name}: help response missing object 'data'",
            field="help",
        )
    if data.get("error") and "schema" not in data:
        raise ClientValidationError(
            f"{command_name}: {data.get('error')}",
            field="help",
            details={"note": data.get("note"), "example": data.get("example")},
        )
    schema = data.get("schema")
    if not isinstance(schema, dict):
        raise ClientValidationError(
            f"{command_name}: help response has no 'schema' object",
            field="help",
        )
    return schema


async def fetch_command_schema_from_server(
    rpc: Any,
    command_name: str,
) -> Dict[str, Any]:
    """Call server ``help`` with ``cmdname`` and return that command's input schema."""
    raw = await rpc.help(command_name)
    if not isinstance(raw, dict):
        raise ClientValidationError(
            f"{command_name}: help returned non-dict: {type(raw).__name__}",
            field="help",
        )
    return parse_schema_from_help_payload(raw, command_name=command_name)
