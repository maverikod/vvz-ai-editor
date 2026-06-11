"""
Helpers to build command ``metadata()`` dicts per METADATA_SCHEMA_STANDARD.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Type

REQUIRED_METADATA_KEYS = (
    "name",
    "version",
    "description",
    "category",
    "author",
    "email",
    "detailed_description",
    "parameters",
    "return_value",
    "usage_examples",
    "error_cases",
    "best_practices",
)


def identity_fields(cls: Type[Any]) -> Dict[str, Any]:
    """Class-attribute identity block for metadata."""
    return {
        "name": getattr(cls, "name", ""),
        "version": getattr(cls, "version", "0.1"),
        "description": getattr(cls, "descr", "") or "",
        "category": getattr(cls, "category", ""),
        "author": getattr(cls, "author", ""),
        "email": getattr(cls, "email", ""),
    }


def empty_params_schema(
    *,
    description: str = "",
    additional_properties: bool = False,
) -> Dict[str, Any]:
    """JSON Schema for zero-parameter commands."""
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": additional_properties,
    }
    if description:
        schema["description"] = description
    return schema


def parameters_from_schema(
    schema: Mapping[str, Any],
    *,
    required_flags: Optional[Mapping[str, bool]] = None,
) -> Dict[str, Any]:
    """
    Build metadata ``parameters`` from ``get_schema()`` properties.

    ``required_flags`` overrides required True/False per key (e.g. when schema
    lists a key in ``required`` but docs should mark optional semantics).
    """
    props = schema.get("properties") or {}
    if not isinstance(props, dict):
        return {}
    required_set = set(schema.get("required") or [])
    out: Dict[str, Any] = {}
    for key, spec in props.items():
        if not isinstance(spec, dict):
            continue
        req = required_flags.get(key) if required_flags else (key in required_set)
        entry: Dict[str, Any] = {
            "description": spec.get("description", ""),
            "type": spec.get("type", "string"),
            "required": bool(req),
        }
        if "default" in spec:
            entry["default"] = spec["default"]
        if "enum" in spec:
            entry["enum"] = spec["enum"]
        if "items" in spec:
            entry["items"] = spec["items"]
        if "minimum" in spec:
            entry["minimum"] = spec["minimum"]
        if "maximum" in spec:
            entry["maximum"] = spec["maximum"]
        if "minItems" in spec:
            entry["minItems"] = spec["minItems"]
        if "maxItems" in spec:
            entry["maxItems"] = spec["maxItems"]
        if spec.get("examples"):
            entry["examples"] = spec["examples"]
        out[key] = entry
    return out


def normalize_usage_examples(
    examples: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Ensure each example uses flat param dict under ``command`` (no ``params`` envelope).
    """
    normalized: List[Dict[str, Any]] = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        item = dict(ex)
        cmd = item.get("command")
        if isinstance(cmd, dict) and "params" in cmd and len(cmd) == 1:
            inner = cmd.get("params")
            if isinstance(inner, dict):
                item["command"] = dict(inner)
        normalized.append(item)
    return normalized


def simple_success_return(
    *,
    description: str = "Command completed successfully.",
    data_fields: Optional[Dict[str, str]] = None,
    example: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Standard success/error return_value block."""
    data_fields = data_fields or {"success": "True when the command succeeds."}
    example = example or {"success": True}
    return {
        "success": {
            "description": description,
            "data": data_fields,
            "example": example,
        },
        "error": {
            "description": "Command failed.",
            "code": "Stable error code from the command implementation.",
            "message": "Human-readable error message.",
            "details": "Optional diagnostic object.",
        },
    }


def project_file_error_cases() -> Dict[str, Any]:
    """Common project_id / file_path errors."""
    return {
        "PROJECT_NOT_FOUND": {
            "description": "The project_id does not exist.",
            "message": "Project not found: {project_id}",
            "solution": "Call list_projects and use a valid project_id.",
        },
        "FILE_NOT_FOUND": {
            "description": "File path missing or outside project root.",
            "solution": "Use list_project_files to confirm the relative path.",
        },
        "VALIDATION_ERROR": {
            "description": "Parameter or path validation failed.",
            "solution": "Fix params per get_schema() and retry.",
        },
    }


def build_command_metadata(
    cls: Type[Any],
    *,
    detailed_description: str,
    parameters: Optional[Dict[str, Any]] = None,
    usage_examples: List[Dict[str, Any]],
    error_cases: Dict[str, Any],
    return_value: Dict[str, Any],
    best_practices: List[str],
) -> Dict[str, Any]:
    """
    Assemble a full metadata dict compliant with METADATA_SCHEMA_STANDARD.

    If ``parameters`` is omitted, derives from ``cls.get_schema()``.
    """
    if parameters is None:
        schema_fn = getattr(cls, "get_schema", None)
        schema = schema_fn() if callable(schema_fn) else {}
        parameters = parameters_from_schema(schema if isinstance(schema, dict) else {})

    meta = identity_fields(cls)
    meta.update(
        {
            "detailed_description": detailed_description,
            "parameters": parameters,
            "return_value": return_value,
            "usage_examples": normalize_usage_examples(usage_examples),
            "error_cases": error_cases,
            "best_practices": best_practices,
        }
    )
    return meta


def _schema_properties(schema: Mapping[str, Any]) -> Dict[str, Any]:
    props = schema.get("properties") or {}
    return props if isinstance(props, dict) else {}


def _default_usage_examples(
    cls: Type[Any],
    schema: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    props = _schema_properties(schema)
    command: Dict[str, Any] = {}
    if "project_id" in props:
        command["project_id"] = "550e8400-e29b-41d4-a716-446655440000"
    elif "tree_id" in props:
        command["tree_id"] = "550e8400-e29b-41d4-a716-446655440000"
    elif "job_id" in props:
        command["job_id"] = "550e8400-e29b-41d4-a716-446655440000"
    elif "message" in props:
        command["message"] = "hello"
    elif "seconds" in props:
        command["seconds"] = 1.0
    return [
        {
            "description": f"Run {getattr(cls, 'name', 'command')}",
            "command": command,
            "explanation": "Minimal example aligned with get_schema().",
        },
    ]


def _sanitize_usage_examples(
    examples: List[Dict[str, Any]],
    schema: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Drop schema-unknown keys; map legacy root_dir examples to project_id."""
    props = set(_schema_properties(schema).keys())
    out: List[Dict[str, Any]] = []
    for ex in normalize_usage_examples(examples):
        if not isinstance(ex, dict):
            continue
        item = dict(ex)
        cmd = item.get("command")
        if isinstance(cmd, dict):
            cmd = dict(cmd)
            if "root_dir" in cmd and "project_id" in props and "project_id" not in cmd:
                cmd.pop("root_dir", None)
                cmd.setdefault(
                    "project_id",
                    "550e8400-e29b-41d4-a716-446655440000",
                )
            cmd = {k: v for k, v in cmd.items() if k in props}
            item["command"] = cmd
        out.append(item)
    return out


def finalize_command_metadata(
    cls: Type[Any],
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize metadata to METADATA_SCHEMA_STANDARD.

    - Fills identity and missing top-level blocks.
    - ``parameters`` always mirrors ``get_schema()`` (drops legacy ``root_dir``).
    - Sanitizes ``usage_examples`` command dicts to schema keys.
    """
    schema_fn = getattr(cls, "get_schema", None)
    schema: Dict[str, Any] = schema_fn() if callable(schema_fn) else {}
    if not isinstance(schema, dict):
        schema = {}

    out: Dict[str, Any] = dict(meta or {})
    ident = identity_fields(cls)
    for key, value in ident.items():
        if key not in out or out[key] in (None, ""):
            out[key] = value

    if not out.get("detailed_description"):
        out["detailed_description"] = out.get("description") or ident["description"]

    out["parameters"] = parameters_from_schema(schema)

    if not out.get("return_value"):
        out["return_value"] = simple_success_return()

    examples = out.get("usage_examples")
    if not examples:
        out["usage_examples"] = _default_usage_examples(cls, schema)
    else:
        out["usage_examples"] = _sanitize_usage_examples(
            list(examples) if isinstance(examples, list) else [],
            schema,
        )

    if not out.get("error_cases"):
        props = _schema_properties(schema)
        if "project_id" in props:
            out["error_cases"] = project_file_error_cases()
        else:
            out["error_cases"] = {
                "COMMAND_ERROR": {
                    "description": "Command failed.",
                    "solution": "See server logs and get_schema().",
                },
            }

    if not out.get("best_practices"):
        props = _schema_properties(schema)
        if "project_id" in props:
            out["best_practices"] = [
                "Resolve project_id via list_projects.",
                "Use project-relative file_path values.",
            ]
        else:
            out["best_practices"] = [
                "Call help for parameter details.",
            ]

    return out


def wrap_command_metadata_class(cmd_cls: Type[Any]) -> Type[Any]:
    """Wrap ``metadata()`` so registration returns finalized metadata."""
    from mcp_proxy_adapter.commands.base import Command

    if getattr(cmd_cls, "_metadata_finalized", False):
        return cmd_cls

    original = cmd_cls.__dict__.get("metadata")
    if original is None:
        original = Command.metadata

    @classmethod  # type: ignore[misc]
    def metadata(cls: Type[Any]) -> Dict[str, Any]:
        raw = original.__func__(cls) if hasattr(original, "__func__") else original(cls)  # type: ignore[call-arg]
        return finalize_command_metadata(cls, raw if isinstance(raw, dict) else {})

    metadata._metadata_finalized = True  # type: ignore[attr-defined]
    cmd_cls.metadata = metadata  # type: ignore[method-assign]
    cmd_cls._metadata_finalized = True
    return cmd_cls


def apply_metadata_finalization_to_registry(reg: Any) -> None:
    """Finalize metadata for all registered ai_editor command classes."""
    commands = getattr(reg, "_commands", None)
    if not isinstance(commands, dict):
        return
    for cmd_cls in commands.values():
        mod = getattr(cmd_cls, "__module__", "") or ""
        if mod.startswith("ai_editor."):
            wrap_command_metadata_class(cmd_cls)
