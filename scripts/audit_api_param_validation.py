#!/usr/bin/env python3
"""
Audit MCP API commands for strict parameter validation gaps.

Produces docs/ai_reports/api-cmd_bugs.yaml

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def walk_schema_nodes(schema: Any, path: str = "root") -> List[Tuple[str, Dict[str, Any]]]:
    nodes: List[Tuple[str, Dict[str, Any]]] = []
    if not isinstance(schema, dict):
        return nodes
    nodes.append((path, schema))
    props = schema.get("properties")
    if isinstance(props, dict):
        for k, v in props.items():
            nodes.extend(walk_schema_nodes(v, f"{path}.properties.{k}"))
    items = schema.get("items")
    if isinstance(items, dict):
        nodes.extend(walk_schema_nodes(items, f"{path}.items"))
    elif isinstance(items, list):
        for i, it in enumerate(items):
            nodes.extend(walk_schema_nodes(it, f"{path}.items[{i}]"))
    for key in ("oneOf", "anyOf", "allOf"):
        alts = schema.get(key)
        if isinstance(alts, list):
            for i, alt in enumerate(alts):
                nodes.extend(walk_schema_nodes(alt, f"{path}.{key}[{i}]"))
    return nodes


def get_source_file(cls: type) -> str:
    try:
        p = Path(inspect.getfile(cls))
        try:
            return str(p.relative_to(project_root))
        except ValueError:
            return str(p)
    except TypeError:
        return getattr(cls, "__module__", "unknown")


def inherits_base_mcp(cls: type) -> bool:
    return any(b.__name__ == "BaseMCPCommand" for b in cls.__mro__)


def inherits_adapter_command(cls: type) -> bool:
    return any(b.__name__ == "Command" for b in cls.__mro__)


def schema_static_issues(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if schema.get("type") != "object":
        issues.append({"id": "schema_root_not_object", "severity": "error", "path": "root"})
    if "additionalProperties" not in schema:
        issues.append(
            {
                "id": "schema_missing_additionalProperties",
                "severity": "error",
                "path": "root",
                "detail": (
                    "schema omits additionalProperties; BaseMCPCommand treats missing as True"
                ),
            }
        )
    elif schema.get("additionalProperties") is True:
        issues.append(
            {
                "id": "schema_additionalProperties_true",
                "severity": "error",
                "path": "root",
                "detail": "unknown top-level parameters are allowed by schema",
            }
        )
    if "required" not in schema:
        issues.append({"id": "schema_missing_required", "severity": "warning", "path": "root"})

    for path, node in walk_schema_nodes(schema):
        if path == "root":
            continue
        is_object = node.get("type") == "object" or "properties" in node
        if not is_object:
            continue
        nap = node.get("additionalProperties")
        if nap is True:
            issues.append(
                {
                    "id": "schema_nested_additionalProperties_true",
                    "severity": "warning",
                    "path": path,
                    "detail": "nested object allows unknown keys (additionalProperties: true)",
                }
            )
        elif "properties" in node and "additionalProperties" not in node:
            issues.append(
                {
                    "id": "schema_nested_missing_additionalProperties",
                    "severity": "warning",
                    "path": path,
                    "detail": "nested object omits additionalProperties (defaults permissive)",
                }
            )
        if path.startswith("root.properties.") and path.count(".") == 2:
            if "type" not in node and "oneOf" not in node and "anyOf" not in node:
                issues.append(
                    {
                        "id": "schema_property_missing_type",
                        "severity": "warning",
                        "path": path,
                        "property": path.split(".")[-1],
                    }
                )
    return issues


def analyze_validate_params(cls: type) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if "validate_params" not in cls.__dict__:
        if inherits_base_mcp(cls):
            issues.append(
                {
                    "id": "uses_base_validate_params_prefilter",
                    "severity": "error",
                    "systemic_ref": "SYS-001",
                    "detail": "see systemic_findings SYS-001 (BaseMCPCommand pre-filter)",
                }
            )
        elif inherits_adapter_command(cls):
            issues.append(
                {
                    "id": "uses_adapter_validate_params_no_type_check",
                    "severity": "warning",
                    "detail": (
                        "uses mcp_proxy_adapter Command.validate_params: rejects unknown "
                        "keys when additionalProperties is false, but does not validate "
                        "parameter types or enum values"
                    ),
                }
            )
        else:
            issues.append(
                {
                    "id": "validate_params_missing",
                    "severity": "error",
                    "detail": "no validate_params; class does not inherit Command or BaseMCPCommand",
                }
            )
        return issues

    src = inspect.getsource(cls.validate_params)
    if (
        "super().validate_params" in src
        and not inherits_base_mcp(cls)
        and not inherits_adapter_command(cls)
    ):
        issues.append(
            {
                "id": "validate_params_super_without_base",
                "severity": "error",
                "systemic_ref": "SYS-004",
                "detail": (
                    "validate_params calls super().validate_params but class does not inherit "
                    "Command or BaseMCPCommand (runtime AttributeError)"
                ),
            }
        )
    if "super().validate_params" not in src and "validate_params_against_schema" not in src:
        issues.append(
            {
                "id": "validate_params_override_without_super",
                "severity": "error",
                "detail": (
                    "custom validate_params does not call super().validate_params or "
                    "validate_params_against_schema"
                ),
            }
        )
    if inherits_base_mcp(cls) and "super().validate_params" in src:
        issues.append(
            {
                "id": "uses_base_validate_params_prefilter",
                "severity": "error",
                "systemic_ref": "SYS-001",
                "detail": "see systemic_findings SYS-001 (BaseMCPCommand pre-filter)",
            }
        )
    return issues


def analyze_execute(cls: type) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    execute = getattr(cls, "execute", None)
    if execute is None:
        return issues
    try:
        src = inspect.getsource(execute)
    except (OSError, TypeError):
        return issues
    if (
        "if k in schema_props" in src
        or "k in schema_props" in src
        or "{k: v for k, v in params.items() if k in" in src
    ):
        issues.append(
            {
                "id": "execute_filters_unknown_params",
                "severity": "error",
                "detail": "execute() filters params to schema keys instead of rejecting unknown keys",
            }
        )
    sig = inspect.signature(execute)
    has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    return issues


def discover_command_classes() -> Dict[str, type]:
    """Find command classes under ai_editor.commands with a ``name`` attribute."""
    import ai_editor.commands as commands_pkg

    found: Dict[str, type] = {}
    prefix = commands_pkg.__name__ + "."
    for modinfo in pkgutil.walk_packages(commands_pkg.__path__, prefix):
        try:
            mod = importlib.import_module(modinfo.name)
        except Exception:
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if obj.__module__ != modinfo.name:
                continue
            cmd_name = getattr(obj, "name", None)
            if not isinstance(cmd_name, str) or not cmd_name:
                continue
            if not hasattr(obj, "get_schema") or not hasattr(obj, "execute"):
                continue
            found[cmd_name] = obj
    return found


def minimal_valid_params(schema: Dict[str, Any]) -> Dict[str, Any]:
    valid: Dict[str, Any] = {}
    req = schema.get("required") or []
    for r in req:
        if r == "project_id":
            valid[r] = "550e8400-e29b-41d4-a716-446655440000"
        elif r == "watch_dir_id":
            valid[r] = "550e8400-e29b-41d4-a716-446655440000"
        elif r in ("file_path", "script_path"):
            valid[r] = "test.py"
        elif r == "tree_id":
            valid[r] = "00000000-0000-4000-8000-000000000001"
        elif r == "session_id":
            valid[r] = "00000000-0000-4000-8000-000000000002"
        elif r == "project_name":
            valid[r] = "testproj"
        elif r == "description":
            valid[r] = "desc"
        elif r == "invocations":
            valid[r] = [{"command": "health", "params": {}}]
        elif r == "config":
            valid[r] = {"src_class": "A", "dst_classes": {}}
        elif r in ("operations", "ops", "items", "hooks"):
            valid[r] = []
        elif r == "source_code":
            valid[r] = "pass\n"
        elif r == "docstring":
            valid[r] = "doc"
        elif r in ("start_line", "end_line", "seconds"):
            valid[r] = 1
        elif r in ("search_type",):
            valid[r] = "simple"
        elif r in ("query", "selector"):
            valid[r] = "function[name='f']"
        elif r == "node_id":
            valid[r] = "00000000-0000-4000-8000-000000000003"
        elif r == "worker_type":
            valid[r] = "file_watcher"
        elif r == "action":
            valid[r] = "lock"
        elif r == "pattern":
            valid[r] = "foo"
        elif r == "entity_type":
            valid[r] = "class"
        elif r == "entity_name":
            valid[r] = "Foo"
        elif r == "module_name":
            valid[r] = "m"
        elif r == "package":
            valid[r] = "pkg"
        elif r == "text":
            valid[r] = "t"
        elif r == "lines":
            valid[r] = ["a"]
        elif r == "paths":
            valid[r] = ["a.txt"]
        elif r == "transfer_id":
            valid[r] = "00000000-0000-4000-8000-000000000004"
        elif r == "lock_batch_id":
            valid[r] = "00000000-0000-4000-8000-000000000005"
        elif r == "parent_session_id":
            valid[r] = "00000000-0000-4000-8000-000000000006"
        elif r == "server_id":
            valid[r] = "srv"
        elif r == "subordinate_session_id":
            valid[r] = "00000000-0000-4000-8000-000000000007"
        else:
            valid[r] = "x"
    return valid


def behavioral_probe(cls: type, schema: Dict[str, Any]) -> Dict[str, str]:
    from ai_editor.core.exceptions import ValidationError

    inst = cls()
    base = minimal_valid_params(schema)
    out: Dict[str, str] = {}

    p_unknown = dict(base)
    p_unknown["__unknown_param__"] = "x"
    try:
        inst.validate_params(p_unknown)
        out["unknown_param"] = "accepted"
    except ValidationError:
        out["unknown_param"] = "rejected"
    except Exception as exc:
        out["unknown_param"] = f"error:{type(exc).__name__}"

    if "project_id" in (schema.get("properties") or {}):
        p_type = dict(base)
        p_type["project_id"] = 123
        try:
            inst.validate_params(p_type)
            out["wrong_type_project_id"] = "accepted"
        except ValidationError:
            out["wrong_type_project_id"] = "rejected"
        except Exception as exc:
            out["wrong_type_project_id"] = f"error:{type(exc).__name__}"

    return out


def audit() -> Dict[str, Any]:
    from mcp_proxy_adapter.commands.command_registry import CommandRegistry
    from ai_editor.hooks import register_ai_editor_commands

    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    registered = {
        n: c
        for n, c in reg._commands.items()
        if (getattr(c, "__module__", "") or "").startswith("ai_editor.")
    }

    all_classes = discover_command_classes()
    not_registered = sorted(set(all_classes) - set(registered))

    command_rows: List[Dict[str, Any]] = []
    for cmd_name in sorted(set(all_classes) | set(registered)):
        cls = all_classes.get(cmd_name) or registered.get(cmd_name)
        if cls is None:
            continue
        row_issues: List[Dict[str, Any]] = []
        schema: Dict[str, Any] = {}
        schema_error: Optional[str] = None
        try:
            schema = cls.get_schema()
        except Exception as exc:
            schema_error = str(exc)

        if schema_error:
            row_issues.append(
                {"id": "schema_get_error", "severity": "error", "detail": schema_error}
            )
        elif isinstance(schema, dict):
            row_issues.extend(schema_static_issues(schema))
        else:
            row_issues.append(
                {
                    "id": "schema_invalid_return",
                    "severity": "error",
                    "detail": f"get_schema returned {type(schema).__name__}",
                }
            )

        row_issues.extend(analyze_validate_params(cls))
        row_issues.extend(analyze_execute(cls))

        if cmd_name not in registered:
            row_issues.append(
                {
                    "id": "command_not_registered",
                    "severity": "warning",
                    "detail": (
                        "command class exists with get_schema/execute but is not registered "
                        "via register_ai_editor_commands (not exposed in live API registry)"
                    ),
                }
            )

        behavior: Dict[str, str] = {}
        if cmd_name in registered and not schema_error and isinstance(schema, dict):
            try:
                behavior = behavioral_probe(cls, schema)
            except Exception as exc:
                behavior = {"probe": f"failed:{type(exc).__name__}"}
            if behavior.get("unknown_param") == "accepted":
                row_issues.append(
                    {
                        "id": "behavior_accepts_unknown_param",
                        "severity": "error",
                        "detail": (
                            "validate_params({...valid..., __unknown_param__}) succeeds; "
                            "unknown parameter is not rejected"
                        ),
                    }
                )
            if behavior.get("wrong_type_project_id") == "accepted":
                row_issues.append(
                    {
                        "id": "behavior_accepts_wrong_type",
                        "severity": "error",
                        "detail": "validate_params accepts project_id=123 (integer) without type error",
                        "field": "project_id",
                    }
                )

        command_rows.append(
            {
                "command": cmd_name,
                "source_file": get_source_file(cls),
                "registered": cmd_name in registered,
                "inherits_base_mcp_command": inherits_base_mcp(cls),
                "inherits_adapter_command_only": inherits_adapter_command(cls)
                and not inherits_base_mcp(cls),
                "behavior_probe": behavior,
                "issues": row_issues,
            }
        )

    kind_counts: Dict[str, int] = {}
    for row in command_rows:
        for issue in row["issues"]:
            kind_counts[issue["id"]] = kind_counts.get(issue["id"], 0) + 1

    return {
        "meta": {
            "title": "API command parameter validation discrepancies",
            "generated_by": "scripts/audit_api_param_validation.py",
            "standard": "docs/standards/PARAMS_VALIDATION.md",
            "rule": (
                "Optional parameters may be absent. If present, they must match schema type "
                "and semantics. Unknown parameters must produce a validation error."
            ),
        },
        "systemic_findings": [
            {
                "id": "SYS-001",
                "severity": "error",
                "location": "ai_editor/commands/base_mcp_command.py:619-620",
                "title": "BaseMCPCommand.validate_params silently drops unknown keys",
                "description": (
                    "Before validate_params_against_schema, params are filtered to schema "
                    "properties when additionalProperties is false. Extra keys never reach the "
                    "unknown-parameter check and are accepted silently."
                ),
                "expected": (
                    "Raise ValidationError for any key not listed in schema.properties when "
                    "additionalProperties is false."
                ),
            },
            {
                "id": "SYS-002",
                "severity": "error",
                "location": "ai_editor/commands/base_mcp_command.py:524",
                "title": "validate_params_against_schema defaults additionalProperties to True",
                "description": (
                    "Schemas that omit additionalProperties allow unknown keys. Contradicts "
                    "Command Metadata standard requiring explicit additionalProperties."
                ),
            },
            {
                "id": "SYS-003",
                "severity": "warning",
                "location": "mcp_proxy_adapter/commands/base.py:142-222",
                "title": "Adapter Command.validate_params skips type/enum checks",
                "description": (
                    "Commands inheriting Command directly (not BaseMCPCommand) reject unknown "
                    "keys when additionalProperties is false, but never validate types or enums."
                ),
                "affected_commands": [
                    "format_code",
                    "lint_code",
                    "type_check_code",
                    "health",
                    "queue_health",
                    "qa_sleep",
                ],
            },
            {
                "id": "SYS-004",
                "severity": "error",
                "location": "ai_editor/commands/project_management_mcp_commands/create_project.py",
                "title": "create_project.validate_params is broken (no base class)",
                "description": (
                    "CreateProjectMCPCommand does not inherit Command or BaseMCPCommand but "
                    "calls super().validate_params → AttributeError at runtime."
                ),
            },
            {
                "id": "SYS-005",
                "severity": "warning",
                "location": "ai_editor/hooks_register_part1.py",
                "title": "CST/JSON tree commands not registered in API registry",
                "description": (
                    "Command classes exist (cst_*, json_*, list_cst_blocks, query_cst, …) but "
                    "are absent from register_ai_editor_commands; only listed in "
                    "register_auto_import_module for worker spawn."
                ),
                "not_registered_commands": not_registered,
            },
        ],
        "summary": {
            "command_classes_discovered": len(all_classes),
            "commands_registered_in_api": len(registered),
            "commands_not_registered": not_registered,
            "commands_with_issues": sum(1 for r in command_rows if r["issues"]),
            "behavior_unknown_param_accepted": sum(
                1
                for r in command_rows
                if r.get("behavior_probe", {}).get("unknown_param") == "accepted"
            ),
            "behavior_unknown_param_rejected": sum(
                1
                for r in command_rows
                if r.get("behavior_probe", {}).get("unknown_param") == "rejected"
            ),
            "issue_kind_counts": kind_counts,
        },
        "commands": command_rows,
    }


def main() -> int:
    logging.disable(logging.CRITICAL)
    report = audit()
    out_path = project_root / "docs" / "ai_reports" / "api-cmd_bugs.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        text = yaml.safe_dump(
            report,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )
    except ImportError:
        text = json.dumps(report, indent=2, ensure_ascii=False)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
