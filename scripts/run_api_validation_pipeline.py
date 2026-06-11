#!/usr/bin/env python3
"""
API validation pipeline: run positive and negative scenarios for MCP commands
via real server (config.json). Groups: project_management, cst, refactor,
analysis, search, ast, code_quality, file_management.

Per command we run:
- positive: call with valid params (required = presence; values from fixtures or minimal).
- missing_required: omit one required param -> expect validation error.
- wrong_type: pass wrong type for one required param (e.g. project_id: 123) -> expect error.
- invalid_value: pass non-existent project_id or watch_dir_id (when required) -> expect error.

Parameters: required = presence only; all params validated strictly on type and value by server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Project root for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Command groups to validate. Use registered command names (name = "..." in command class).
# All commands in these groups get: positive, missing_required, wrong_type; invalid_value for project_id/watch_dir_id when required.
VALIDATION_GROUPS = {
    "project_management": {
        "list_projects",
        "list_watch_dirs",
        "create_project",
        "project_set_mark_del",
        "change_project_id",
        "list_trashed_projects",
        "clear_trash",
        "restore_project_from_trash",
        "permanently_delete_from_trash",
        "delete_unwatched_projects",
        "run_project_module",
        "run_project_script",
        "project_pip_check",
        "project_pip_search",
    },
    "cst": {
        "cst_load_file",
        "list_cst_blocks",
        "query_cst",
        "cst_save_tree",
        "cst_create_file",
        "cst_modify_tree",
        "cst_convert_and_save",
        "cst_find_node",
        "cst_get_node_info",
        "cst_get_node_by_range",
        "cst_get_node_at_line",
        "cst_reload_tree",
        "get_file_lines",
        "replace_file_lines",
    },
    "refactor": {
        "split_class",
        "extract_superclass",
        "split_file_to_package",
    },
    "analysis": {
        "comprehensive_analysis",
        "find_duplicates",
        "analyze_complexity",
        "update_indexes",
        "list_long_files",
        "list_errors_by_category",
        "check_vectors",
    },
    "search": {
        "fulltext_search",
        "semantic_search",
        "find_classes",
        "list_class_methods",
    },
    "ast": {
        "list_project_files",
        "get_ast",
        "get_code_entity_info",
        "list_code_entities",
        "get_imports",
        "find_dependencies",
        "get_entity_dependencies",
        "get_entity_dependents",
        "get_class_hierarchy",
        "export_graph",
        "find_usages",
        "search_ast_nodes",
        "ast_statistics",
        "read_only_batch",
    },
    "code_quality": {
        "format_code",
        "lint_code",
        "type_check_code",
    },
    "file_management": {
        "list_deleted_files",
        "delete_file",
        "restore_deleted_files",
        "unmark_deleted_file",
        "cleanup_deleted_files",
        "repair_database",
        "collapse_versions",
        # Non-Python text I/O (paths .py/.pyi/.pyw rejected; use CST for Python)
        "read_project_text_file",
        "write_project_text_lines",
    },
}

# Commands that run via queue (expect job_id or poll)
QUEUED_COMMANDS = {
    "update_indexes",
    "comprehensive_analysis",
    "export_graph",
    "project_set_mark_del",
    "split_class",
    "extract_superclass",
    "split_file_to_package",
    "clear_trash",
    "permanently_delete_from_trash",
    "delete_unwatched_projects",
    "project_pip_install",
    "run_project_script",
}

# Non-existent UUID for negative value tests
INVALID_UUID = "00000000-0000-0000-0000-000000000000"


def _get_commands_to_run(group_name: str) -> list[str]:
    """Return list of command names to run for a group (from VALIDATION_GROUPS)."""
    return sorted(VALIDATION_GROUPS.get(group_name, set()))


def _extract_schema_from_help(client: Any, command: str) -> dict[str, Any]:
    """Get required_params and all_params from help(command).

    Full walk of help response. Server filters params to schema properties when
    additionalProperties is False, so extra keys do not cause "unknown parameter".
    """
    try:
        resp = client.call_command(command="help", params={"command": command})
    except Exception as e:
        return {"error": str(e), "required_params": [], "all_params": []}

    all_params: set[str] = set()
    required_params: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            props = node.get("properties") or {}
            if isinstance(props, dict):
                all_params.update(props.keys())
            req = node.get("required") or []
            if isinstance(req, list):
                for r in req:
                    if isinstance(r, str):
                        required_params.add(r)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(resp)
    return {
        "required_params": (
            sorted(required_params & all_params)
            if all_params
            else sorted(required_params)
        ),
        "all_params": sorted(all_params),
    }


def _is_success(response: Any) -> bool:
    """True if response indicates success (no error, or job_id for queued)."""
    if response is None:
        return False
    if isinstance(response, dict):
        if response.get("error"):
            return False
        if response.get("success") is False:
            return False
        if "job_id" in response:
            return True
        if "data" in response or response.get("success") is True:
            return True
        if "result" in response and response.get("result") is not None:
            return True
    return True


def _error_message(response: Any) -> str:
    """Extract error message from response or exception; always returns a string."""
    if isinstance(response, Exception):
        return str(response)
    if isinstance(response, dict):
        raw = (
            response.get("error")
            or response.get("message")
            or (response.get("details") or {}).get("message")
            or json.dumps(response)[:200]
        )
        if isinstance(raw, str):
            return raw
        return json.dumps(raw)[:200] if raw is not None else json.dumps(response)[:200]
    return str(response)


def _run_positive(
    client: Any,
    command: str,
    params: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[bool, str]:
    """Run command with valid params; expect success or coherent result."""
    use_queue = command in QUEUED_COMMANDS
    try:
        resp = client.call_command(
            command=command,
            params=params,
            use_queue=use_queue if use_queue else None,
        )
    except Exception as e:
        return False, f"Exception: {e}"

    if _is_success(resp):
        return True, "OK"
    msg = _error_message(resp)
    return False, msg


def _run_negative_missing_required(
    client: Any,
    command: str,
    schema: dict[str, Any],
    valid_params: dict[str, Any],
) -> tuple[bool, str]:
    """Omit one required param; expect validation/schema error."""
    required = schema.get("required_params") or []
    if not required:
        return True, "skip (no required params)"
    # Omit first required
    key = required[0]
    params = {k: v for k, v in valid_params.items() if k != key}
    try:
        resp = client.call_command(command=command, params=params)
    except Exception as e:
        # Expected: validation may raise
        return True, f"Expected error: {e}"
    if _is_success(resp):
        return False, "Expected error for missing required param but got success"
    return True, "OK (got error)"


def _run_negative_wrong_type(
    client: Any,
    command: str,
    schema: dict[str, Any],
    valid_params: dict[str, Any],
) -> tuple[bool, str]:
    """Pass wrong type for one required param (e.g. project_id: 123); expect error."""
    required = schema.get("required_params") or []
    if not required:
        return True, "skip (no required params)"
    key = required[0]
    params = dict(valid_params)
    params[key] = 12345  # wrong type
    try:
        resp = client.call_command(command=command, params=params)
    except Exception as e:
        return True, f"Expected error: {e}"
    if _is_success(resp):
        return False, "Expected error for wrong type but got success"
    return True, "OK (got error)"


def _run_negative_invalid_value(
    client: Any,
    command: str,
    valid_params: dict[str, Any],
    param_for_invalid: str,
) -> tuple[bool, str]:
    """Pass invalid value (e.g. non-existent project_id); expect error."""
    params = dict(valid_params)
    params[param_for_invalid] = INVALID_UUID
    try:
        resp = client.call_command(command=command, params=params)
    except Exception as e:
        return True, f"Expected error: {e}"
    if _is_success(resp):
        return False, "Expected error for invalid value but got success"
    msg = _error_message(resp).lower()
    if "not found" in msg or "invalid" in msg or "error" in msg:
        return True, "OK (got error)"
    return True, "OK (got error)"


def _gather_valid_fixtures(client: Any) -> dict[str, Any]:
    """Get project_id, watch_dir_id, file_path from server for positive tests."""
    fixtures: dict[str, Any] = {}
    try:
        r = client.call_command("list_projects", params={})
        if _is_success(r) and isinstance(r, dict):
            data = r.get("data") or r
            projects = data.get("projects", []) or data.get("data", [])
            if isinstance(projects, list) and projects:
                first = projects[0]
                fixtures["project_id"] = first.get("id") or first.get("project_id")
    except Exception:
        pass
    try:
        r = client.call_command("list_watch_dirs", params={})
        if _is_success(r) and isinstance(r, dict):
            data = r.get("data") or r
            wds = data.get("watch_dirs", [])
            if wds:
                fixtures["watch_dir_id"] = wds[0].get("id")
    except Exception:
        pass
    if fixtures.get("project_id"):
        try:
            r = client.call_command(
                "list_cst_blocks",
                params={"project_id": fixtures["project_id"], "file_path": "README.md"},
            )
            if _is_success(r):
                fixtures["file_path"] = "README.md"
            else:
                r2 = client.call_command(
                    "list_cst_blocks",
                    params={
                        "project_id": fixtures["project_id"],
                        "file_path": "setup.py",
                    },
                )
                if _is_success(r2):
                    fixtures["file_path"] = "setup.py"
        except Exception:
            pass
    if not fixtures.get("file_path") and fixtures.get("project_id"):
        fixtures["file_path"] = "README.md"
    return fixtures


def _build_valid_params(
    command: str,
    schema: dict[str, Any],
    fixtures: dict[str, Any],
) -> dict[str, Any]:
    """Build minimal valid params for command (presence only for required)."""
    required = schema.get("required_params") or []
    params: dict[str, Any] = {}
    for r in required:
        if r == "project_id":
            params[r] = fixtures.get("project_id") or INVALID_UUID
        elif r == "watch_dir_id":
            params[r] = fixtures.get("watch_dir_id") or INVALID_UUID
        elif r == "file_path":
            params[r] = fixtures.get("file_path") or "README.md"
        elif r == "watched_dir_id":
            params[r] = fixtures.get("watch_dir_id") or INVALID_UUID
        elif r == "tree_id":
            params[r] = "dummy"
        elif r == "node_id":
            params[r] = "dummy"
        elif r == "trash_folder_name":
            params[r] = "dummy"
        elif r == "root_dir":
            params[r] = str(PROJECT_ROOT / "test_data" / "sample")
        elif r == "project_name":
            params[r] = "api_validation_test"
        elif r == "description":
            params[r] = "API validation pipeline"
        elif r == "new_project_id":
            params[r] = "11111111-1111-1111-1111-111111111111"
        elif r == "start_line":
            params[r] = 1
        elif r == "end_line":
            params[r] = 1
        elif r == "new_lines":
            params[r] = []
        elif r == "packages":
            params[r] = ["pip"]
        else:
            params[r] = "dummy"
    return params


def run_group(
    client: Any,
    group_name: str,
    commands: list[str],
    fixtures: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Run positive and negative validation for a group of commands."""
    results: dict[str, Any] = {
        "group": group_name,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "cases": [],
    }

    for command in commands:
        schema = _extract_schema_from_help(client, command)
        if schema.get("error"):
            results["cases"].append(
                {
                    "command": command,
                    "scenario": "schema",
                    "passed": False,
                    "message": schema["error"],
                }
            )
            results["failed"] += 1
            continue

        valid_params = _build_valid_params(command, schema, fixtures)

        # Positive: only if we have minimal valid params (e.g. project_id for project-scoped commands)
        requires_project = "project_id" in (
            schema.get("required_params") or []
        ) and command not in (
            "list_projects",
            "list_watch_dirs",
        )
        if requires_project and not fixtures.get("project_id"):
            results["cases"].append(
                {
                    "command": command,
                    "scenario": "positive",
                    "passed": True,
                    "message": "skipped (no project_id)",
                }
            )
            results["skipped"] += 1
        else:
            ok, msg = _run_positive(client, command, valid_params, schema)
            results["cases"].append(
                {
                    "command": command,
                    "scenario": "positive",
                    "passed": ok,
                    "message": msg,
                }
            )
            if ok:
                results["passed"] += 1
            else:
                results["failed"] += 1

        if options.get("no_negative"):
            continue

        # Negative: missing required
        ok, msg = _run_negative_missing_required(client, command, schema, valid_params)
        results["cases"].append(
            {
                "command": command,
                "scenario": "missing_required",
                "passed": ok,
                "message": msg,
            }
        )
        if ok:
            results["passed"] += 1
        elif "skip" in msg:
            results["skipped"] += 1
        else:
            results["failed"] += 1

        # Negative: wrong type
        ok, msg = _run_negative_wrong_type(client, command, schema, valid_params)
        results["cases"].append(
            {"command": command, "scenario": "wrong_type", "passed": ok, "message": msg}
        )
        if ok:
            results["passed"] += 1
        elif "skip" in msg:
            results["skipped"] += 1
        else:
            results["failed"] += 1

        # Negative: invalid value (for project_id / watch_dir_id)
        if "project_id" in valid_params:
            ok, msg = _run_negative_invalid_value(
                client, command, valid_params, "project_id"
            )
            results["cases"].append(
                {
                    "command": command,
                    "scenario": "invalid_value",
                    "passed": ok,
                    "message": msg,
                }
            )
            if ok:
                results["passed"] += 1
            else:
                results["failed"] += 1
        elif "watch_dir_id" in valid_params and command == "create_project":
            ok, msg = _run_negative_invalid_value(
                client, command, valid_params, "watch_dir_id"
            )
            results["cases"].append(
                {
                    "command": command,
                    "scenario": "invalid_value",
                    "passed": ok,
                    "message": msg,
                }
            )
            if ok:
                results["passed"] += 1
            else:
                results["failed"] += 1

    return results


def main() -> int:
    """Run API validation pipeline against real server."""
    parser = argparse.ArgumentParser(
        description="Run API validation pipeline (positive + negative) via real server"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config.json",
        help="Server config path",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override server host (e.g. 127.0.0.1 for local)",
    )
    parser.add_argument("--port", type=int, default=None, help="Override server port")
    parser.add_argument(
        "--protocol",
        type=str,
        default=None,
        choices=["http", "mtls"],
        help="Override server protocol (e.g. http for local test server)",
    )
    parser.add_argument(
        "--group",
        type=str,
        choices=list(VALIDATION_GROUPS.keys()),
        help="Run only this group",
    )
    parser.add_argument(
        "--list-commands", action="store_true", help="List commands per group and exit"
    )
    parser.add_argument(
        "--no-negative", action="store_true", help="Skip negative scenarios"
    )
    parser.add_argument(
        "--use-test-server",
        action="store_true",
        help="Start server with test config (127.0.0.1:15001), run validation, then stop server",
    )
    args = parser.parse_args()

    # Resolve commands per group
    category_to_names: dict[str, list[str]] = {}
    for group_name in VALIDATION_GROUPS:
        if args.group and args.group != group_name:
            continue
        category_to_names[group_name] = _get_commands_to_run(group_name)

    if args.list_commands:
        for g, cmds in category_to_names.items():
            print(f"{g}: {', '.join(cmds)}")
        return 0

    # Build client against real server (config.json)
    try:
        from scripts.pipeline.config import PipelineConfig
        from scripts.pipeline.mcp_client import MCPClientWrapper, is_available
        from scripts.pipeline.server_manager import ServerManager
    except ImportError as e:
        print(
            "Import error (run from repo root, need scripts.pipeline):",
            e,
            file=sys.stderr,
        )
        return 1

    if not is_available():
        print("MCP direct client not available", file=sys.stderr)
        return 1

    config_path = args.config
    if args.protocol and (args.host or args.port):
        # Write a small config so client uses the desired protocol/host/port
        base = config_path.exists() and json.loads(config_path.read_text()) or {}
        base.setdefault("server", {})
        if args.host:
            base["server"]["host"] = args.host
        if args.port is not None:
            base["server"]["port"] = args.port
        if args.protocol:
            base["server"]["protocol"] = args.protocol
        config_path = PROJECT_ROOT / "tmp_validation_client_config.json"
        config_path.write_text(json.dumps(base, indent=2))
    config = PipelineConfig(
        server_config_path=config_path,
        server_host=args.host,
        server_port=args.port,
    )
    server_manager = None
    if args.use_test_server:
        config = PipelineConfig(
            server_config_path=args.config,
            server_host="127.0.0.1",
            server_port=15001,
        )
        test_config_path = PROJECT_ROOT / "test_config_validation_pipeline.json"
        config.create_test_config(test_config_path)
        # Force HTTP for local test (no mTLS)
        with open(test_config_path, "r", encoding="utf-8") as f:
            test_cfg = json.load(f)
        test_cfg.setdefault("server", {})["protocol"] = "http"
        with open(test_config_path, "w", encoding="utf-8") as f:
            json.dump(test_cfg, f, indent=2)
        config.server_config_path = test_config_path
        server_manager = ServerManager(config)
        server_manager.config_file = test_config_path
        print("Starting test server (127.0.0.1:15001, HTTP)...", flush=True)
        if not server_manager._apply_schema(timeout=60):
            print("Schema apply failed", file=sys.stderr)
            return 1
        server_manager._run_server_cli("stop", timeout=15)
        started = server_manager._run_server_cli("start", timeout=30)
        if not started:
            print(
                "Failed to start test server (start command returned false)",
                file=sys.stderr,
            )
            return 1
        deadline = time.time() + 45
        while time.time() < deadline:
            if server_manager._can_connect():
                break
            time.sleep(0.5)
        else:
            print("Server did not become reachable", file=sys.stderr)
            return 1
        time.sleep(1)
        print("Test server started.", flush=True)
        config = PipelineConfig(server_config_path=test_config_path)

    client = MCPClientWrapper(config=config)
    # Preflight: ensure server is reachable
    try:
        client.call_command("list_projects", params={})
    except Exception as e:
        if server_manager:
            server_manager.stop_server(timeout=10)
        print(
            "Server unreachable. Ensure server is running and --host/--port match.",
            file=sys.stderr,
        )
        print("Example (local): --host 127.0.0.1 --port 15001", file=sys.stderr)
        print(
            "Or use: --use-test-server (server needs DB RPC driver running).",
            file=sys.stderr,
        )
        print("Error:", e, file=sys.stderr)
        return 1
    fixtures = _gather_valid_fixtures(client)
    print("Fixtures:", json.dumps({k: v for k, v in fixtures.items() if v}, indent=2))

    total_passed = total_failed = total_skipped = 0
    for group_name, commands in category_to_names.items():
        if not commands:
            continue
        res = run_group(
            client, group_name, commands, fixtures, {"no_negative": args.no_negative}
        )
        total_passed += res["passed"]
        total_failed += res["failed"]
        total_skipped += res["skipped"]
        print(f"\n--- {group_name} ---")
        for c in res["cases"]:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['command']} {c['scenario']}: {c['message'][:80]}")
        print(
            f"  Summary: passed={res['passed']} failed={res['failed']} skipped={res['skipped']}"
        )

    print("\n--- Total ---")
    print(f"passed={total_passed} failed={total_failed} skipped={total_skipped}")
    exit_code = 0 if total_failed == 0 else 1
    if server_manager:
        print("Stopping test server...", flush=True)
        server_manager.stop_server(timeout=15)
        print("Test server stopped.", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
