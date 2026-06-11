"""
Shallow JSON-schema validation aligned with BaseMCPCommand.validate_params_against_schema.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from ai_editor_client.exceptions import ClientValidationError


def prepare_params_for_schema(
    params: Dict[str, Any], schema: Dict[str, Any]  # noqa: ARG001
) -> Dict[str, Any]:
    """Return a shallow copy of params for validation and dispatch."""
    return dict(params)


def validate_params_against_schema(
    params: Dict[str, Any],
    schema: Dict[str, Any],
    command_name: str = "command",
) -> None:
    """Validate params against a command ``get_schema()``-style object (subset)."""
    if not isinstance(params, dict):
        raise ClientValidationError(
            f"{command_name}: params must be a dict, got {type(params).__name__}",
            field="params",
        )
    props = schema.get("properties") or {}
    additional_ok = schema.get("additionalProperties", False)
    required_set = set(schema.get("required") or [])
    for key, value in params.items():
        if key not in props:
            if not additional_ok:
                raise ClientValidationError(
                    f"{command_name}: unknown parameter {key!r}. "
                    "Only schema-defined properties are allowed.",
                    field=key,
                    details={"allowed": list(props.keys())},
                )
            continue
        if value is None:
            continue
        prop = props[key]
        expected_type = prop.get("type")
        if expected_type == "string":
            if not isinstance(value, str):
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be string, got {type(value).__name__}",
                    field=key,
                )
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be integer, got {type(value).__name__}",
                    field=key,
                )
        elif expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be number, got {type(value).__name__}",
                    field=key,
                )
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be boolean, got {type(value).__name__}",
                    field=key,
                )
        elif expected_type == "array":
            if not isinstance(value, list):
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be array, got {type(value).__name__}",
                    field=key,
                )
        elif expected_type == "object":
            if not isinstance(value, dict):
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be object, got {type(value).__name__}",
                    field=key,
                )
        if "enum" in prop and value is not None:
            if value not in prop["enum"]:
                raise ClientValidationError(
                    f"{command_name}: parameter {key!r} must be one of {prop['enum']!r}, got {value!r}",
                    field=key,
                    details={"enum": prop["enum"]},
                )
    for key in required_set:
        if key not in params or params[key] is None:
            raise ClientValidationError(
                f"{command_name}: required parameter {key!r} is missing",
                field=key,
            )
