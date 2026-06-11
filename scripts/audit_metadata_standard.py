#!/usr/bin/env python3
"""
Audit registered MCP commands against docs/standards/METADATA_SCHEMA_STANDARD.md.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

REQUIRED_KEYS = (
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


def _load_commands() -> Dict[str, Any]:
    from mcp_proxy_adapter.commands.command_registry import CommandRegistry
    from ai_editor.hooks import register_ai_editor_commands

    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    return reg._commands


def _audit(cmd_name: str, cmd_class: type) -> Dict[str, Any]:
    from mcp_proxy_adapter.commands.base import Command

    issues: List[str] = []
    schema = cmd_class.get_schema() if hasattr(cmd_class, "get_schema") else {}
    if not isinstance(schema, dict) or schema.get("type") != "object":
        issues.append("schema:type!=object")
    if "additionalProperties" not in schema:
        issues.append("schema:missing additionalProperties")
    if "required" not in schema:
        issues.append("schema:missing required")

    meta_fn = getattr(cmd_class, "metadata", None)
    base_meta = Command.metadata
    if meta_fn is None or meta_fn == base_meta:
        issues.append("metadata:not_overridden")
        meta: Dict[str, Any] = {}
    else:
        meta = meta_fn() or {}

    props_for_empty = schema.get("properties") or {}
    has_schema_params = bool(
        isinstance(props_for_empty, dict) and props_for_empty
    )

    for key in REQUIRED_KEYS:
        val = meta.get(key)
        if key not in meta or val in (None, ""):
            issues.append(f"metadata:missing_or_empty:{key}")
            continue
        if key == "parameters" and val == {} and not has_schema_params:
            continue
        if val in ([], {}):
            issues.append(f"metadata:missing_or_empty:{key}")

    props = set((schema.get("properties") or {}).keys())
    mparams = meta.get("parameters") or {}
    if isinstance(mparams, dict):
        for k in mparams:
            if k not in props:
                issues.append(f"parameters:extra:{k}")
        for k in props:
            if k not in mparams:
                issues.append(f"parameters:missing:{k}")

    for ex in meta.get("usage_examples") or []:
        if isinstance(ex, dict) and isinstance(ex.get("command"), dict):
            if "params" in ex["command"] and len(ex["command"]) == 1:
                issues.append("usage_examples:params_envelope")

    return {"command": cmd_name, "issues": issues, "ok": not issues}


def main() -> int:
    import logging

    logging.disable(logging.CRITICAL)
    commands = _load_commands()
    rows = []
    for n, c in sorted(commands.items()):
        mod = getattr(c, "__module__", "") or ""
        if mod.startswith("ai_editor."):
            rows.append(_audit(n, c))
    ok = sum(1 for r in rows if r["ok"])
    print(json.dumps({"total": len(rows), "ok": ok, "rows": rows}, indent=2))
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
