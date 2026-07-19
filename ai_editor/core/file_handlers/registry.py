"""
Config-driven extension → handler registry for universal file commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, FrozenSet, List

HANDLER_TEXT = "text"
HANDLER_JSON = "json"
HANDLER_YAML = "yaml"
HANDLER_INI = "ini"
HANDLER_TOML = "toml"
HANDLER_PYTHON = "python"

HANDLER_IDS = (
    HANDLER_TEXT,
    HANDLER_JSON,
    HANDLER_YAML,
    HANDLER_INI,
    HANDLER_TOML,
    HANDLER_PYTHON,
)

OPERATIONS = frozenset({"read", "save", "replace", "delete"})

# Default mapping (centralized; swap for config-driven dict merge later).
_DEFAULT_SUFFIX_MAP: Dict[str, str] = {
    ".md": HANDLER_TEXT,
    ".txt": HANDLER_TEXT,
    ".rst": HANDLER_TEXT,
    ".adoc": HANDLER_TEXT,
    ".jsonl": HANDLER_TEXT,
    ".ndjson": HANDLER_TEXT,
    ".json": HANDLER_JSON,
    ".yaml": HANDLER_YAML,
    ".yml": HANDLER_YAML,
    ".ini": HANDLER_INI,
    ".cfg": HANDLER_INI,
    ".toml": HANDLER_TOML,
    ".py": HANDLER_PYTHON,
    ".pyi": HANDLER_PYTHON,
    ".pyw": HANDLER_PYTHON,
}

_HANDLER_SUPPORTED_OPS: Dict[str, FrozenSet[str]] = {
    HANDLER_TEXT: OPERATIONS,
    HANDLER_JSON: OPERATIONS,
    HANDLER_YAML: OPERATIONS,
    HANDLER_INI: OPERATIONS,
    HANDLER_TOML: OPERATIONS,
    HANDLER_PYTHON: OPERATIONS,
}


class RegistryError(Exception):
    """Raised when routing fails; carries MCP-oriented code and details."""

    def __init__(self, code: str, details: Dict[str, Any]) -> None:
        super().__init__(details.get("message", code))
        self.code = code
        self.details = details


def _suffix(file_path: str) -> str:
    return Path(file_path).suffix.lower()


def resolve_handler(file_path: str, operation: str) -> str:
    """Return handler id if ``file_path`` and ``operation`` are supported."""
    validate_supported(file_path, operation)
    suf = _suffix(file_path)
    return _DEFAULT_SUFFIX_MAP[suf]


def validate_supported(file_path: str, operation: str) -> None:
    """Raise RegistryError when extension or operation is not supported."""
    op = (operation or "").lower().strip()
    if op not in OPERATIONS:
        raise RegistryError(
            "UNSUPPORTED_FILE_OPERATION",
            {
                "message": f"Unsupported file operation: {operation!r}",
                "file_path": file_path,
                "handler_id": "",
                "operation": operation,
            },
        )

    suf = _suffix(file_path)
    if not suf:
        raise RegistryError(
            "UNSUPPORTED_FILE_EXTENSION",
            {
                "message": "Path has no extension; cannot resolve handler",
                "file_path": file_path,
                "suffix": suf,
                "operation": op,
            },
        )

    hid = _DEFAULT_SUFFIX_MAP.get(suf)
    if hid is None:
        raise RegistryError(
            "UNSUPPORTED_FILE_EXTENSION",
            {
                "message": f"No handler for suffix {suf!r}",
                "file_path": file_path,
                "suffix": suf,
                "operation": op,
            },
        )

    if op not in _HANDLER_SUPPORTED_OPS.get(hid, frozenset()):
        raise RegistryError(
            "UNSUPPORTED_FILE_OPERATION",
            {
                "message": f"Handler {hid!r} does not support operation {op!r}",
                "file_path": file_path,
                "handler_id": hid,
                "operation": op,
            },
        )


def list_handler_mappings() -> List[Dict[str, str]]:
    """Return sorted extension → handler rows for discovery."""
    rows = [
        {"suffix": suf, "handler_id": hid}
        for suf, hid in sorted(_DEFAULT_SUFFIX_MAP.items())
    ]
    return rows


def get_handler_schema(handler_id: str, operation: str) -> Dict[str, Any]:
    """JSON-schema-like fragment per handler and operation (documentation aid)."""
    op = (operation or "").lower().strip()
    base_common: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "file_path": {"type": "string"},
            "dry_run": {"type": "boolean"},
            "diff": {"type": "boolean"},
            "backup": {"type": "boolean"},
        },
    }

    if handler_id == HANDLER_TEXT:
        if op == "read":
            return {
                **base_common,
                "description": "Plain text: optional start_line/end_line (1-based inclusive); reads may clamp.",
                "properties": {
                    **base_common["properties"],
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
            }
        if op in ("save", "replace", "delete"):
            return {
                **base_common,
                "description": "Plain text: full content or line ranges; no Python/CST parsing.",
                "properties": {
                    **base_common["properties"],
                    "content": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "new_lines": {"type": "array", "items": {"type": "string"}},
                },
            }

    if handler_id == HANDLER_JSON:
        return {
            **base_common,
            "description": "JSON: use JSON Pointer / structured payloads; not raw ambiguous line edits.",
            "properties": {
                **base_common["properties"],
                "json_pointer": {"type": "string"},
                "content": {},
                "value": {},
            },
        }

    if handler_id == HANDLER_YAML:
        return {
            **base_common,
            "description": "YAML: path-based edits; comments may not round-trip.",
            "properties": {
                **base_common["properties"],
                "yaml_path": {"type": "string"},
                "content": {"type": "string"},
                "value": {},
            },
        }

    if handler_id in (HANDLER_INI, HANDLER_TOML):
        return {
            **base_common,
            "description": (
                f"{handler_id.upper()}: structured key-based configuration edits."
            ),
            "properties": {
                **base_common["properties"],
                "json_pointer": {"type": "string"},
                "content": {"type": "string"},
                "value": {},
            },
        }

    if handler_id == HANDLER_PYTHON:
        return {
            **base_common,
            "description": "Python: CST replace-ops only (run_ops_mode); no raw text line editor.",
            "properties": {
                **base_common["properties"],
                "content": {"type": "string"},
                "ops": {"type": "array"},
            },
        }

    return {
        "type": "object",
        "description": f"Unknown handler {handler_id!r} operation {op!r}",
    }
