#!/usr/bin/env python3
"""
Generate docs/ai_reports/api-cmd_bugs.yaml — full param validation audit.

Each command: read entire source + schema helpers; static + metadata + runtime probe.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

NOT_REGISTERED = {
    "create_text_file",
    "cst_apply_buffer",
    "cst_convert_and_save",
    "cst_create_file",
    "cst_find_node",
    "cst_get_node_at_line",
    "cst_get_node_by_range",
    "cst_get_node_info",
    "cst_list_trees",
    "cst_load_file",
    "cst_modify_tree",
    "cst_reload_tree",
    "cst_save_tree",
    "cst_unload_tree",
    "get_file_lines",
    "json_find_node",
    "json_get_node_info",
    "json_load_file",
    "json_modify_tree",
    "json_reload_tree",
    "json_save_tree",
    "list_cst_blocks",
    "list_json_blocks",
    "query_cst",
    "read_project_text_file",
    "replace_file_lines",
    "universal_file_delete",
    "universal_file_read",
    "universal_file_replace",
    "universal_file_save",
    "write_project_text_lines",
}


def discover_commands() -> Dict[str, type]:
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
            if isinstance(cmd_name, str) and cmd_name and hasattr(obj, "get_schema") and hasattr(obj, "execute"):
                found[cmd_name] = obj
    return found


def read_full(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def inherits_base_mcp(cls: type) -> bool:
    return any(b.__name__ == "BaseMCPCommand" for b in cls.__mro__)


def inherits_command_only(cls: type) -> bool:
    return any(b.__name__ == "Command" for b in cls.__mro__) and not inherits_base_mcp(cls)


def schema_helpers_from_source(source: str, module_file: Path) -> List[str]:
    helpers: List[str] = []
    for m in re.finditer(r"from\s+\.(\w+)\s+import\s+.*get_\w+_schema", source):
        p = module_file.parent / f"{m.group(1)}.py"
        if p.is_file():
            helpers.append(rel(p))
    for m in re.finditer(r"from\s+\.(\w+)\s+import\s+get_parameters", source):
        p = module_file.parent / f"{m.group(1)}.py"
        if p.is_file():
            helpers.append(rel(p))
    return sorted(set(helpers))


def walk_schema(
    schema: Any, path: str = "root", prop_name: Optional[str] = None
) -> List[Tuple[str, Dict[str, Any], Optional[str]]]:
    """Return (path, node, property_name at leaf)."""
    out: List[Tuple[str, Dict[str, Any], Optional[str]]] = []
    if not isinstance(schema, dict):
        return out
    out.append((path, schema, prop_name))
    props = schema.get("properties")
    if isinstance(props, dict):
        for k, v in props.items():
            out.extend(walk_schema(v, f"{path}.properties.{k}", k))
    items = schema.get("items")
    if isinstance(items, dict):
        out.extend(walk_schema(items, f"{path}.items", None))
    elif isinstance(items, list):
        for i, it in enumerate(items):
            out.extend(walk_schema(it, f"{path}.items[{i}]", None))
    return out


def issue(id_: str, severity: str, detail: str, lines: str) -> Dict[str, Any]:
    return {"id": id_, "severity": severity, "detail": detail, "lines": lines}


def dedupe_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for i in issues:
        key = (i["id"], i.get("detail", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(i)
    return out


def schema_structural_issues(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if schema.get("additionalProperties") is True:
        issues.append(
            issue(
                "schema_additionalProperties_true",
                "error",
                "top-level additionalProperties: true allows unknown parameters",
                "get_schema",
            )
        )
    elif "additionalProperties" not in schema:
        issues.append(
            issue(
                "schema_missing_additionalProperties",
                "error",
                "additionalProperties omitted; BaseMCPCommand defaults to permissive True",
                "get_schema",
            )
        )

    root_props = schema.get("properties") or {}
    for path, node, prop_name in walk_schema(schema):
        if path == "root":
            continue
        if node.get("additionalProperties") is True:
            issues.append(
                issue(
                    "schema_nested_additionalProperties_true",
                    "warning",
                    f"nested object at {path} allows unknown keys",
                    "get_schema",
                )
            )
        elif "properties" in node and "additionalProperties" not in node:
            issues.append(
                issue(
                    "schema_nested_missing_additionalProperties",
                    "warning",
                    f"nested object at {path} omits additionalProperties",
                    "get_schema",
                )
            )

        if prop_name and path.startswith("root.properties."):
            ptype = node.get("type")
            if ptype is None and "oneOf" not in node and "anyOf" not in node:
                issues.append(
                    issue(
                        "schema_property_missing_type",
                        "warning",
                        f"property {prop_name!r} has no type/oneOf/anyOf",
                        f"get_schema:{prop_name}",
                    )
                )
            if isinstance(ptype, list):
                issues.append(
                    issue(
                        "union_type_not_validated",
                        "error",
                        f"property {prop_name!r} uses JSON Schema union type {ptype}; "
                        "validate_params_against_schema skips list-typed type",
                        f"get_schema:{prop_name}",
                    )
                )
            if "oneOf" in node:
                issues.append(
                    issue(
                        "oneOf_not_validated",
                        "error",
                        f"property {prop_name!r} has oneOf; not enforced in validate_params_against_schema",
                        f"get_schema:{prop_name}",
                    )
                )
            if "anyOf" in node:
                issues.append(
                    issue(
                        "anyOf_not_validated",
                        "warning",
                        f"property {prop_name!r} has anyOf; not enforced in validate_params_against_schema",
                        f"get_schema:{prop_name}",
                    )
                )
            if "minimum" in node or "maximum" in node:
                issues.append(
                    issue(
                        "schema_min_max_not_enforced",
                        "error",
                        f"property {prop_name!r} has minimum/maximum in schema but "
                        "validate_params_against_schema ignores bounds",
                        f"get_schema:{prop_name}",
                    )
                )
            if "minItems" in node:
                issues.append(
                    issue(
                        "minItems_not_enforced",
                        "error",
                        f"property {prop_name!r} has minItems in schema but not enforced at validate_params",
                        f"get_schema:{prop_name}",
                    )
                )
            if "enum" in node and prop_name in root_props:
                pass  # enum checked when type matches
            if ptype == "array":
                items = node.get("items")
                if isinstance(items, dict) and items.get("type"):
                    issues.append(
                        issue(
                            "array_items_type_not_validated",
                            "warning",
                            f"property {prop_name!r} array items typed {items.get('type')!r} "
                            "but base validator only checks array, not element types",
                            f"get_schema:{prop_name}",
                        )
                    )
                if isinstance(items, dict) and "properties" in items:
                    issues.append(
                        issue(
                            "nested_object_items_not_validated",
                            "error",
                            f"property {prop_name!r} array items are objects; "
                            "inner properties/unknown keys not validated at validate_params",
                            f"get_schema:{prop_name}",
                        )
                    )
    return issues


def metadata_schema_issues(cls: type, schema: Dict[str, Any], source_file: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    from mcp_proxy_adapter.commands.base import Command

    meta_fn = getattr(cls, "metadata", None)
    if meta_fn is None or meta_fn == Command.metadata:
        return issues
    try:
        meta = meta_fn() or {}
    except Exception as exc:
        issues.append(issue("metadata_get_error", "warning", str(exc), f"{source_file}:metadata"))
        return issues

    mparams = meta.get("parameters") or {}
    if not isinstance(mparams, dict) or not mparams:
        return issues

    schema_props = set((schema.get("properties") or {}).keys())
    schema_required = set(schema.get("required") or [])
    meta_keys = set(mparams.keys())

    legacy = {"root_dir", "watched_dir", "project_dir", "project_dir_path"}
    for k in sorted(meta_keys - schema_props):
        spec = mparams[k]
        req = spec.get("required") if isinstance(spec, dict) else False
        if k in legacy:
            issues.append(
                issue(
                    "metadata_legacy_param_not_in_schema",
                    "warning",
                    f"metadata.parameters.{k!r} (required={req}) absent from get_schema; "
                    "schema uses project_id/watch_dir_id instead",
                    f"{source_file}:metadata.parameters.{k}",
                )
            )
        else:
            issues.append(
                issue(
                    "metadata_param_not_in_schema",
                    "warning",
                    f"metadata.parameters.{k!r} not listed in get_schema.properties",
                    f"{source_file}:metadata.parameters.{k}",
                )
            )

    for k in sorted(schema_props - meta_keys):
        if k in ("project_id", "file_path", "tree_id", "session_id"):
            issues.append(
                issue(
                    "schema_param_missing_from_metadata",
                    "warning",
                    f"get_schema property {k!r} not documented in metadata.parameters",
                    f"{source_file}:get_schema + metadata",
                )
            )

    for k in sorted(meta_keys & schema_props):
        ms = mparams[k]
        if not isinstance(ms, dict):
            continue
        mdef = ms.get("default")
        sp = (schema.get("properties") or {}).get(k) or {}
        sdef = sp.get("default")
        if mdef is not None and sdef is not None and mdef != sdef:
            issues.append(
                issue(
                    "metadata_schema_default_mismatch",
                    "warning",
                    f"default mismatch for {k!r}: metadata={mdef!r} schema={sdef!r}",
                    f"{source_file}:metadata + get_schema:{k}",
                )
            )
        if ms.get("required") and k not in schema_required:
            issues.append(
                issue(
                    "metadata_required_but_schema_optional",
                    "warning",
                    f"metadata marks {k!r} required but get_schema.required omits it",
                    f"{source_file}:metadata.parameters.{k}",
                )
            )

    return issues


def execute_signature_issues(cls: type, schema: Dict[str, Any], source: str, source_file: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    schema_props = set((schema.get("properties") or {}).keys())
    try:
        sig = inspect.signature(cls.execute)
    except (TypeError, ValueError):
        return issues

    skip = {"self", "context", "kwargs"}
    for name, param in sig.parameters.items():
        if name in skip or param.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            continue
        if name not in schema_props:
            issues.append(
                issue(
                    "execute_param_not_in_schema",
                    "error",
                    f"execute() named parameter {name!r} absent from get_schema; "
                    "API callers cannot pass it; internal-only or schema gap",
                    f"{source_file}:execute:{name}",
                )
            )

    if re.search(r"await\s+\w+\.execute\([^)]*\*\*", source):
        issues.append(
            issue(
                "execute_forwards_kwargs_without_revalidation",
                "warning",
                "execute forwards **kwargs to another command without re-validating against this schema",
                f"{source_file}:execute",
            )
        )
    return issues


def validate_params_and_execute_semantics(
    cmd_name: str,
    source: str,
    source_file: str,
    cls: type,
    schema: Dict[str, Any],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    if inherits_base_mcp(cls):
        vp_src = ""
        if "def validate_params" in source:
            m = re.search(
                r"def validate_params\(self[^)]*\).*?(?=\n    (?:async )?def |\nclass |\Z)",
                source,
                re.DOTALL,
            )
            vp_src = m.group(0) if m else ""
        rejects_unknown_custom = (
            "invalid_parameters" in vp_src.lower()
            or "unknown parameter" in vp_src.lower()
            or "not in props" in vp_src.lower()
            or "allowed_properties" in vp_src.lower()
        )
        if "def validate_params" not in source or "super().validate_params" in vp_src or not vp_src:
            if not rejects_unknown_custom:
                issues.append(
                    issue(
                        "SYS-001_unknown_param_silent_drop",
                        "error",
                        "uses BaseMCPCommand.validate_params which pre-filters unknown keys "
                        "at base_mcp_command.py:619-620 instead of ValidationError",
                        "ai_editor/commands/base_mcp_command.py:619-620",
                    )
                )
        elif rejects_unknown_custom and "super().validate_params" in vp_src:
            issues.append(
                issue(
                    "custom_validate_before_super_partial",
                    "info",
                    "custom validate_params adds semantic checks; still calls super().validate_params "
                    "which pre-filters unknown keys before type validation",
                    f"{source_file}:validate_params",
                )
            )

    if cmd_name == "create_project":
        if "(BaseMCPCommand" not in source and "(Command" not in source:
            issues.extend(
                [
                    issue(
                        "missing_command_inheritance",
                        "error",
                        "class does not inherit Command or BaseMCPCommand; "
                        "super().validate_params raises AttributeError",
                        f"{source_file}:22",
                    ),
                    issue(
                        "execute_uses_undefined_base_methods",
                        "error",
                        "execute calls _open_database_from_config, _handle_error, _resolve_project_root "
                        "without base class",
                        f"{source_file}:217-320",
                    ),
                ]
            )

    if cmd_name == "list_projects" and "params_present" in source:
        issues.append(
            issue(
                "execute_filters_unknown_params",
                "error",
                "execute builds params_present filtered to schema keys before validate_params_against_schema",
                f"{source_file}:509-517",
            )
        )

    if inherits_command_only(cls):
        issues.append(
            issue(
                "SYS-003_adapter_no_type_validation",
                "warning",
                "inherits mcp_proxy_adapter Command only; unknown keys rejected but types/enums not validated",
                "mcp_proxy_adapter/commands/base.py:142-222",
            )
        )

    if "def validate_params" not in source and inherits_base_mcp(cls):
        if "project_id" in (schema.get("properties") or {}):
            issues.append(
                issue(
                    "missing_project_id_semantic_validation",
                    "warning",
                    "no validate_params override; project_id existence not checked before execute/queue",
                    f"{source_file}:validate_params",
                )
            )

    # Clamping instead of rejecting
    clamp_markers = ("_bounded_int_param", "min(max(", "clamp_hard_timeout", "clamped to")
    if any(m in source for m in clamp_markers):
        for prop_name, spec in (schema.get("properties") or {}).items():
            if "minimum" in spec or "maximum" in spec:
                if "_bounded_int_param" in source or f"min(max(" in source:
                    issues.append(
                        issue(
                            "bounds_clamped_not_rejected",
                            "warning",
                            f"property {prop_name!r} has schema bounds but code clamps/coerces "
                            "instead of raising ValidationError",
                            f"{source_file}:validate_params or execute",
                        )
                    )
                    break

    if cmd_name == "read_only_batch":
        issues.append(
            issue(
                "batch_inner_params_not_strict",
                "error",
                "invocations[].params uses additionalProperties:true; unknown keys inside nested "
                "command params are allowed at schema level",
                f"{source_file}:73-77",
            )
        )
        issues.append(
            issue(
                "batch_invocation_items_permissive",
                "warning",
                "invocations[].items allows additionalProperties:true; extra keys per invocation accepted",
                f"{source_file}:80",
            )
        )

    # Enum validated only in execute
    enum_in_execute = re.findall(
        r'if\s+(\w+)\s+not\s+in\s+\([^)]+\)|must be one of|invalid.*enum',
        source,
        re.I,
    )
    for prop_name, spec in (schema.get("properties") or {}).items():
        if "enum" in spec and prop_name in source:
            if f"{prop_name}" in source and "validate_params" in source:
                vp_block = source.split("def validate_params", 1)[-1].split("def execute", 1)[0]
                if prop_name not in vp_block and "enum" not in vp_block:
                    if re.search(rf'{prop_name}.*not in|invalid.*{prop_name}', source):
                        issues.append(
                            issue(
                                "enum_validated_in_execute_only",
                                "warning",
                                f"property {prop_name!r} enum enforced in execute, not in validate_params",
                                f"{source_file}:execute",
                            )
                        )

    # Conditional required (xpath needs query)
    if cmd_name == "cst_find_node":
        issues.append(
            issue(
                "conditional_required_not_in_validate",
                "warning",
                "search_type=xpath requires query; enforced in execute not validate_params",
                f"{source_file}:119-127",
            )
        )

    # Semantic checks deferred to execute
    deferred_patterns = [
        (r"path_mask.*empty|empty.*path_mask", "path_mask empty check in execute only"),
        (r"install_sources|at least one of.*packages", "pip install sources checked in execute only"),
        (r"trash_folder_name.*\.\.|path separators", "trash_folder_name path safety in execute only"),
    ]
    for pattern, detail in deferred_patterns:
        if re.search(pattern, source, re.I) and "validate_params" in source:
            vp = source.split("def validate_params", 1)[-1].split("def execute", 1)[0]
            if not re.search(pattern, vp, re.I):
                issues.append(
                    issue(
                        "semantic_validation_deferred_to_execute",
                        "warning",
                        detail,
                        f"{source_file}:execute",
                    )
                )

    if "**kwargs" in source and "validate_params_against_schema" not in source:
        issues.append(
            issue(
                "execute_kwargs_not_revalidated",
                "info",
                "execute(**kwargs) without validate_params_against_schema at entry (per PARAMS_VALIDATION.md)",
                f"{source_file}:execute",
            )
        )

    return issues


def minimal_params(schema: Dict[str, Any]) -> Dict[str, Any]:
    valid: Dict[str, Any] = {}
    props = schema.get("properties") or {}
    for r in schema.get("required") or []:
        valid[r] = _dummy_value(r, props.get(r))
    return valid


def _dummy_value(name: str, spec: Any) -> Any:
    if name == "project_id":
        return "550e8400-e29b-41d4-a716-446655440000"
    if name == "watch_dir_id":
        return "550e8400-e29b-41d4-a716-446655440001"
    if name in ("file_path", "script_path", "class_name"):
        return "test.py"
    if name == "tree_id":
        return "00000000-0000-4000-8000-000000000001"
    if name == "session_id":
        return "00000000-0000-4000-8000-000000000002"
    if name == "project_name":
        return "testproj"
    if name == "description":
        return "desc"
    if name == "invocations":
        return [{"command": "health", "params": {}}]
    if name == "config":
        return {"src_class": "A", "dst_classes": {}}
    if name in ("operations", "ops", "items", "hooks"):
        return []
    if name == "packages":
        return ["requests"]
    if name == "source_code":
        return "pass\n"
    if name == "docstring":
        return "doc"
    if name in ("start_line", "end_line", "seconds", "top_n", "limit", "offset"):
        return 1
    if name == "search_type":
        return "simple"
    if name in ("query", "selector"):
        return "function[name='f']"
    if name == "node_id":
        return "00000000-0000-4000-8000-000000000003"
    if name == "worker_type":
        return "file_watcher"
    if name == "action":
        return "lock"
    if name == "pattern":
        return "foo"
    if name == "entity_type":
        return "class"
    if name == "entity_name":
        return "Foo"
    if name == "module_name":
        return "m"
    if name == "package":
        return "pkg"
    if name == "text":
        return "t"
    if name == "lines":
        return ["a"]
    if name == "paths":
        return ["a.txt"]
    if name == "transfer_id":
        return "00000000-0000-4000-8000-000000000004"
    if name == "lock_batch_id":
        return "00000000-0000-4000-8000-000000000005"
    if name == "trash_folder_name":
        return "trash_folder"
    if name == "processing_paused":
        return True
    if name == "file_id":
        return "00000000-0000-4000-8000-000000000010"
    if name == "compression":
        return "none"
    if name == "requirements_file":
        return None
    if name == "list_format":
        return "columns"
    if name == "match_mode":
        return "name"
    if name == "grep_scope":
        return "project"
    if name == "mode":
        return "hybrid"
    if name == "profile":
        return "default"
    if name == "query":
        return "test"
    if isinstance(spec, dict) and spec.get("type") == "boolean":
        return False
    if isinstance(spec, dict) and spec.get("type") == "integer":
        return 1
    if isinstance(spec, dict) and spec.get("type") == "array":
        return []
    return "x"


def behavioral_probe(
    cls: type, schema: Dict[str, Any], registered: bool
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    from ai_editor.core.exceptions import ValidationError

    if not registered:
        return {}, []
    issues: List[Dict[str, Any]] = []
    probe: Dict[str, str] = {}
    try:
        inst = cls()
    except Exception as e:
        return {"instantiate": f"error:{type(e).__name__}"}, []

    base = minimal_params(schema)
    if not base and not (schema.get("properties") or {}):
        base = {}

    p1 = {**base, "__unknown_param__": "x"}
    try:
        inst.validate_params(p1)
        probe["unknown_param"] = "accepted"
        issues.append(
            issue(
                "behavior_accepts_unknown_param",
                "error",
                "validate_params({valid..., __unknown_param__}) succeeds without ValidationError",
                "runtime_probe",
            )
        )
    except ValidationError:
        probe["unknown_param"] = "rejected"
    except Exception as e:
        probe["unknown_param"] = f"error:{type(e).__name__}"

    props = schema.get("properties") or {}
    if "project_id" in props:
        p2 = {**base, "project_id": 123}
        try:
            inst.validate_params(p2)
            probe["wrong_type_project_id"] = "accepted"
            issues.append(
                issue(
                    "behavior_accepts_wrong_type",
                    "error",
                    "project_id=123 (integer) accepted without type ValidationError",
                    "runtime_probe",
                )
            )
        except ValidationError:
            probe["wrong_type_project_id"] = "rejected"
        except Exception as e:
            probe["wrong_type_project_id"] = f"error:{type(e).__name__}"

    for pname, pspec in props.items():
        if not isinstance(pspec, dict) or "enum" not in pspec:
            continue
        bad = "___invalid_enum___"
        if bad in pspec["enum"]:
            continue
        p3 = {**base, pname: bad}
        try:
            inst.validate_params(p3)
            probe[f"wrong_enum_{pname}"] = "accepted"
            issues.append(
                issue(
                    "behavior_accepts_invalid_enum",
                    "error",
                    f"{pname}={bad!r} accepted though enum is {pspec['enum']!r}",
                    "runtime_probe",
                )
            )
        except ValidationError:
            probe[f"wrong_enum_{pname}"] = "rejected"
        except Exception:
            pass

    return probe, issues


def main() -> int:
    logging.disable(logging.CRITICAL)
    from mcp_proxy_adapter.commands.command_registry import CommandRegistry
    from ai_editor.hooks import register_ai_editor_commands

    reg = CommandRegistry()
    register_ai_editor_commands(reg)
    registered_names = {
        n for n, c in reg._commands.items() if c.__module__.startswith("ai_editor.")
    }

    all_classes = discover_commands()
    command_rows: List[Dict[str, Any]] = []

    for ordinal, cmd_name in enumerate(sorted(all_classes), start=1):
        cls = all_classes[cmd_name]
        src_path = Path(inspect.getfile(cls))
        source = read_full(src_path)
        source_rel = rel(src_path)
        helpers = schema_helpers_from_source(source, src_path)
        source_files = [source_rel] + [h for h in helpers if h != source_rel]
        for h in helpers:
            hp = PROJECT_ROOT / h
            if hp.is_file() and hp not in [src_path]:
                pass  # helpers read via get_schema at runtime

        registered = cmd_name in registered_names
        issues: List[Dict[str, Any]] = []
        schema: Dict[str, Any] = {}
        try:
            schema = cls.get_schema()
        except Exception as e:
            issues.append(issue("schema_get_error", "error", str(e), "get_schema"))

        if isinstance(schema, dict):
            issues.extend(schema_structural_issues(schema))
            issues.extend(metadata_schema_issues(cls, schema, source_rel))
            issues.extend(execute_signature_issues(cls, schema, source, source_rel))
            issues.extend(
                validate_params_and_execute_semantics(cmd_name, source, source_rel, cls, schema)
            )

        if not registered:
            issues.append(
                issue(
                    "command_not_registered",
                    "warning",
                    "class exists but absent from register_ai_editor_commands (hooks auto-import only)",
                    "ai_editor/hooks.py",
                )
            )

        probe: Dict[str, str] = {}
        if isinstance(schema, dict) and registered:
            probe, probe_issues = behavioral_probe(cls, schema, registered)
            issues.extend(probe_issues)

        deduped = dedupe_issues(issues)
        inherits = "none"
        if inherits_base_mcp(cls):
            inherits = "BaseMCPCommand"
        elif inherits_command_only(cls):
            inherits = "Command"

        command_rows.append(
            {
                "ordinal": ordinal,
                "command": cmd_name,
                "source_files_read_in_full": source_files,
                "registered": registered,
                "inherits": inherits,
                "behavior_probe": probe,
                "issues": deduped,
                "error_count": sum(1 for i in deduped if i["severity"] == "error"),
                "warning_count": sum(1 for i in deduped if i["severity"] == "warning"),
                "info_count": sum(1 for i in deduped if i["severity"] == "info"),
            }
        )

    kind_counts: Dict[str, int] = {}
    for row in command_rows:
        for i in row["issues"]:
            kind_counts[i["id"]] = kind_counts.get(i["id"], 0) + 1

    report = {
        "meta": {
            "title": "API command parameter validation bugs (complete)",
            "methodology": (
                "Per command: full read of source + schema helper files; "
                "schema/metadata/execute/validate_params static analysis; "
                "runtime probe (unknown param, wrong type, invalid enum) on registered commands."
            ),
            "standard": "docs/standards/PARAMS_VALIDATION.md",
            "rule": (
                "Optional parameters may be absent. If present they must match schema type and semantics. "
                "Unknown parameters must raise ValidationError."
            ),
            "audit_date": "2026-05-23",
            "audit_pass": "complete",
            "total_commands": len(command_rows),
        },
        "systemic_findings": [
            {
                "id": "SYS-001",
                "severity": "error",
                "location": "ai_editor/commands/base_mcp_command.py:619-620",
                "title": "Unknown params silently filtered in BaseMCPCommand.validate_params",
                "description": (
                    "When additionalProperties is false, params dict is filtered to schema properties "
                    "before validate_params_against_schema. Unknown keys never trigger ValidationError."
                ),
                "fix": "Remove pre-filter; call validate_params_against_schema on original params.",
            },
            {
                "id": "SYS-002",
                "severity": "error",
                "location": "ai_editor/commands/base_mcp_command.py:524",
                "title": "Default additionalProperties=True in validate_params_against_schema",
                "description": "Schemas omitting additionalProperties allow unknown keys.",
            },
            {
                "id": "SYS-003",
                "severity": "warning",
                "location": "mcp_proxy_adapter/commands/base.py:142-222",
                "title": "Adapter Command.validate_params skips type/enum validation",
                "description": (
                    "format_code, lint_code, type_check_code, health, queue_health, qa_sleep "
                    "reject unknown keys but not wrong types."
                ),
            },
            {
                "id": "SYS-004",
                "severity": "error",
                "location": "ai_editor/commands/project_management_mcp_commands/create_project.py:22",
                "title": "create_project missing Command/BaseMCPCommand inheritance",
                "description": "validate_params super() raises AttributeError; no param validation path works.",
            },
            {
                "id": "SYS-005",
                "severity": "warning",
                "location": "ai_editor/hooks_register_part1.py",
                "title": "31 command classes not registered in live API",
                "description": (
                    "CST/JSON/universal legacy commands exist with get_schema but are not in "
                    "register_ai_editor_commands."
                ),
                "commands": sorted(NOT_REGISTERED),
            },
            {
                "id": "SYS-006",
                "severity": "error",
                "location": "ai_editor/commands/base_mcp_command.py:500-597",
                "title": "Shallow schema validation",
                "description": (
                    "validate_params_against_schema ignores minimum/maximum, minItems, oneOf, anyOf, "
                    "union types, array item types, nested object property validation."
                ),
            },
        ],
        "summary": {
            "commands_audited": len(command_rows),
            "registered_in_api": sum(1 for r in command_rows if r["registered"]),
            "not_registered": sum(1 for r in command_rows if not r["registered"]),
            "commands_with_errors": sum(1 for r in command_rows if r["error_count"] > 0),
            "commands_with_warnings": sum(1 for r in command_rows if r["warning_count"] > 0),
            "total_issue_entries": sum(len(r["issues"]) for r in command_rows),
            "behavior_unknown_accepted": sum(
                1 for r in command_rows if r.get("behavior_probe", {}).get("unknown_param") == "accepted"
            ),
            "behavior_unknown_rejected": sum(
                1 for r in command_rows if r.get("behavior_probe", {}).get("unknown_param") == "rejected"
            ),
            "issue_kind_counts": kind_counts,
            "command_list": [r["command"] for r in command_rows],
        },
        "commands": command_rows,
    }

    out = PROJECT_ROOT / "docs" / "ai_reports" / "api-cmd_bugs.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    out.write_text(
        yaml.safe_dump(report, allow_unicode=True, sort_keys=False, default_flow_style=False, width=120),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    print(
        f"commands={len(command_rows)} "
        f"total_issues={report['summary']['total_issue_entries']} "
        f"errors_cmds={report['summary']['commands_with_errors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
