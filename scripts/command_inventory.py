#!/usr/bin/env python3
"""
Command Inventory Utility - Comprehensive command discovery and verification tool.

This utility provides multiple modes:
- discover: Find all commands from registry and update documentation
- check: Verify command files, imports, and registration
- verify: Check command availability via MCP interface
- full: Run all checks (default)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_all_registered_commands() -> Dict[str, Dict[str, Any]]:
    """Get all registered commands from the real registry."""
    from mcp_proxy_adapter.commands.command_registry import CommandRegistry
    from ai_editor.hooks import register_ai_editor_commands

    # Create a fresh registry and register commands
    reg = CommandRegistry()
    register_ai_editor_commands(reg)

    # Get all commands from registry
    commands = {}
    for cmd_name, cmd_class in reg._commands.items():
        # Get command metadata
        category = getattr(cmd_class, "category", "uncategorized")
        commands[cmd_name] = {
            "name": cmd_name,
            "category": category,
            "class": cmd_class.__name__,
        }

    return commands


def get_standard_adapter_commands() -> Set[str]:
    """Get list of standard adapter commands (from mcp_proxy_adapter)."""
    return {
        "echo",
        "long_task",
        "job_status",
        "help",
        "health",
        "config",
        "reload",
        "settings",
        "load",
        "unload",
        "plugins",
        "transport_management",
        "proxy_registration",
        "roletest",
        "queue_add_job",
        "queue_start_job",
        "queue_stop_job",
        "queue_delete_job",
        "queue_get_job_status",
        "queue_get_job_logs",
        "queue_list_jobs",
        "queue_health",
    }


def find_command_files() -> Dict[str, List[Path]]:
    """Find all command files in the project."""
    commands_dir = project_root / "ai_editor" / "commands"
    command_files = defaultdict(list)

    # Find all Python files in commands directory
    for py_file in commands_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        # Skip test files
        if "test" in py_file.name.lower():
            continue

        # Determine group by directory structure
        rel_path = py_file.relative_to(commands_dir)
        if len(rel_path.parts) == 1:
            # Top-level command file
            group = "top_level"
        else:
            # Subdirectory
            group = rel_path.parts[0]

        command_files[group].append(py_file)

    return command_files


def map_category_to_display_name(category: str) -> str:
    """Map internal category to display name."""
    category_map = {
        "ast": "AST Commands",
        "cst": "CST Commands",
        "search": "Search Commands",
        "vector": "Vector Operations",
        "code_quality": "Code Quality",
        "refactoring": "Refactoring",
        "refactor": "Refactor Commands",
        "ai_editor": "AI Editor",
        "analysis": "Analysis Commands",
        "database": "Database Management",
        "project_management": "Project Management",
        "file_management": "File Management",
        "backup": "Backup Management",
        "worker": "Worker Management",
        "monitoring": "Monitoring Commands",
        "log": "Logging Commands",
        "custom": "Custom Commands",
    }
    return category_map.get(category, category.replace("_", " ").title() + " Commands")


def check_command_files(commands_to_check: Set[str] = None) -> Dict[str, bool]:
    """Check if command files exist."""
    results: Dict[str, bool] = {}
    commands_dir = project_root / "ai_editor" / "commands"

    # Map command names to expected file paths
    command_file_map = {
        "cst_load_file": commands_dir / "cst_load_file_command.py",
        "list_cst_blocks": commands_dir / "list_cst_blocks_command.py",
        "query_cst": commands_dir / "query_cst_command.py",
    }

    # If specific commands requested, check only those
    if commands_to_check:
        command_file_map = {
            k: v for k, v in command_file_map.items() if k in commands_to_check
        }

    for cmd_name, file_path in command_file_map.items():
        results[cmd_name] = file_path.exists()
        if not results[cmd_name]:
            print(f"  ❌ Missing file: {file_path}")

    return results


def check_command_imports(commands_to_check: Set[str] = None) -> Dict[str, bool]:
    """Check if commands can be imported."""
    results: Dict[str, bool] = {}

    import_map = {
        "cst_load_file": (
            "ai_editor.commands.cst_load_file_command",
            "CSTLoadFileCommand",
        ),
        "list_cst_blocks": (
            "ai_editor.commands.list_cst_blocks_command",
            "ListCSTBlocksCommand",
        ),
        "query_cst": (
            "ai_editor.commands.query_cst_command",
            "QueryCSTCommand",
        ),
    }

    # If specific commands requested, check only those
    if commands_to_check:
        import_map = {k: v for k, v in import_map.items() if k in commands_to_check}

    for cmd_name, (module_path, class_name) in import_map.items():
        try:
            module = __import__(module_path, fromlist=[class_name])
            getattr(module, class_name)
            results[cmd_name] = True
            print(f"  ✅ {cmd_name}: import successful")
        except (ImportError, AttributeError) as e:
            results[cmd_name] = False
            print(f"  ❌ {cmd_name}: import failed - {e}")

    return results


def check_hooks_registration(commands_to_check: Set[str] = None) -> Dict[str, bool]:
    """Check if commands are registered in hooks.py."""
    results: Dict[str, bool] = {}
    hooks_file = project_root / "ai_editor" / "hooks.py"

    if not hooks_file.exists():
        print(f"  ❌ hooks.py not found: {hooks_file}")
        return results

    content = hooks_file.read_text(encoding="utf-8")

    # Map command names to (display class, unique substring in hooks.py).
    registration_map = {
        "cst_load_file": (
            "CSTLoadFileCommand",
            'register_auto_import_module("ai_editor.commands.cst_load_file_command")',
        ),
        "list_cst_blocks": (
            "ListCSTBlocksCommand",
            'register_auto_import_module("ai_editor.commands.list_cst_blocks_command")',
        ),
        "query_cst": (
            "QueryCSTCommand",
            'register_auto_import_module("ai_editor.commands.query_cst_command")',
        ),
    }

    # If specific commands requested, check only those
    if commands_to_check:
        registration_map = {
            k: v for k, v in registration_map.items() if k in commands_to_check
        }

    for cmd_name, (class_name, register_pattern) in registration_map.items():
        found = register_pattern in content
        results[cmd_name] = found
        if found:
            print(f"  ✅ {cmd_name}: hooks.py ({class_name})")
        else:
            print(f"  ❌ {cmd_name}: NOT found in hooks.py ({class_name})")

    return results


def verify_mcp_commands(server_id: str = "ai-editor-server") -> Dict[str, Any]:
    """Verify commands via MCP interface."""
    try:
        from mcp_MCP_Proxy_2 import list_servers

        # Get server info
        servers_result = list_servers(page=1, page_size=10)
        if not servers_result.get("servers"):
            return {"error": "No servers found", "available_commands": set()}

        ai_editor_server = None
        for server in servers_result["servers"]:
            if server["server_id"] == server_id:
                ai_editor_server = server
                break

        if not ai_editor_server:
            return {"error": f"{server_id} not found", "available_commands": set()}

        available_commands = set(ai_editor_server["commands"].keys())
        return {
            "server": ai_editor_server,
            "available_commands": available_commands,
            "command_count": ai_editor_server["command_count"],
        }
    except ImportError:
        return {"error": "MCP Proxy not available", "available_commands": set()}
    except Exception as e:
        return {"error": str(e), "available_commands": set()}


def mode_discover(output_file: Path = None, verbose: bool = False) -> int:
    """Discover all commands and update documentation."""
    if verbose:
        print("🔍 Discovering all commands from registry...")

    # Get all registered commands from real registry
    all_commands = get_all_registered_commands()

    # Get standard adapter commands
    standard_commands = get_standard_adapter_commands()

    # Filter out standard commands
    custom_commands = {
        name: info
        for name, info in all_commands.items()
        if name not in standard_commands
    }

    # Group commands by category
    commands_by_category = defaultdict(list)
    for cmd_name, cmd_info in custom_commands.items():
        category = cmd_info.get("category", "uncategorized")
        display_category = map_category_to_display_name(category)
        commands_by_category[display_category].append(cmd_name)

    # Sort commands within each category
    for category in commands_by_category:
        commands_by_category[category].sort()

    # Find command files
    command_files = find_command_files()

    # Determine output file
    if output_file is None:
        output_file = project_root / "docs" / "COMMAND_INVENTORY.md"

    # Write inventory to file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Command Inventory\n\n")
        f.write("Author: Vasiliy Zdanovskiy\n")
        f.write("email: vasilyvz@gmail.com\n\n")
        f.write("## Overview\n\n")
        f.write(
            "This document lists all custom commands available in the ai-editor-server.\n"
        )
        f.write(
            "Standard adapter commands (echo, health, queue_*, etc.) are excluded.\n\n"
        )

        f.write(f"**Total custom commands**: {len(custom_commands)}\n\n")

        f.write("## Commands by Category\n\n")

        # Write categorized commands (sorted by category name)
        for category in sorted(commands_by_category.keys()):
            f.write(f"### {category}\n\n")
            for cmd_name in commands_by_category[category]:
                f.write(f"- `{cmd_name}`\n")
            f.write("\n")

        # Write command files by group
        f.write("## Command Files by Group\n\n")
        for group in sorted(command_files.keys()):
            f.write(f"### {group}\n\n")
            for file_path in sorted(command_files[group]):
                rel_path = file_path.relative_to(project_root)
                f.write(f"- `{rel_path}`\n")
            f.write("\n")

    print(f"✅ Inventory written to: {output_file}")
    print(f"   Total custom commands found: {len(custom_commands)}")
    print(f"   Standard adapter commands excluded: {len(standard_commands)}")
    print(f"   Categories: {len(commands_by_category)}")

    return 0


def mode_check(verbose: bool = False) -> int:
    """Check command files, imports, and registration."""
    print("=" * 80)
    print("Command Registration Check")
    print("=" * 80)
    print()

    # Get all registered commands to check
    all_commands = get_all_registered_commands()
    standard_commands = get_standard_adapter_commands()
    custom_commands = {
        name for name in all_commands.keys() if name not in standard_commands
    }

    print(f"Checking {len(custom_commands)} custom commands...")
    print()

    # Check files (limited to known CST commands for now)
    print("1. Checking command files...")
    file_results = check_command_files()
    print()

    # Check imports
    print("2. Checking command imports...")
    import_results = check_command_imports()
    print()

    # Check hooks registration
    print("3. Checking hooks.py registration...")
    hooks_results = check_hooks_registration()
    print()

    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)

    all_checked = (
        set(file_results.keys())
        | set(import_results.keys())
        | set(hooks_results.keys())
    )

    all_ok = True
    for cmd in sorted(all_checked):
        file_ok = file_results.get(cmd, True)  # Default True if not checked
        import_ok = import_results.get(cmd, True)
        hooks_ok = hooks_results.get(cmd, True)

        if not (file_ok and import_ok and hooks_ok):
            all_ok = False

        status = "✅" if (file_ok and import_ok and hooks_ok) else "❌"
        if verbose or not (file_ok and import_ok and hooks_ok):
            print(
                f"{status} {cmd}: file={file_ok}, import={import_ok}, hooks={hooks_ok}"
            )

    if all_ok:
        print("\n✅ All checked commands are properly registered")
        return 0
    else:
        print("\n⚠️  Some commands have issues")
        return 1


def mode_verify(server_id: str = "ai-editor-server", verbose: bool = False) -> int:
    """Verify commands via MCP interface."""
    print("=" * 80)
    print("MCP Commands Availability Check")
    print("=" * 80)
    print()

    result = verify_mcp_commands(server_id)

    if "error" in result:
        print(f"❌ {result['error']}")
        return 1

    server = result["server"]
    available_commands = result["available_commands"]
    command_count = result["command_count"]

    print(f"✅ Found server: {server['server_id']}")
    print(f"   Commands available: {command_count}")
    print()

    # Get expected commands from registry
    all_commands = get_all_registered_commands()
    standard_commands = get_standard_adapter_commands()
    expected_commands = {
        name for name in all_commands.keys() if name not in standard_commands
    }

    print(f"Checking {len(expected_commands)} expected custom commands...")
    print()

    missing = []
    found = []

    for cmd in sorted(expected_commands):
        if cmd in available_commands:
            found.append(cmd)
            if verbose:
                print(f"  ✅ {cmd}")
        else:
            missing.append(cmd)
            print(f"  ❌ {cmd} - NOT FOUND")

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total expected: {len(expected_commands)}")
    print(f"Found: {len(found)}")
    print(f"Missing: {len(missing)}")

    if missing:
        print()
        print("Missing commands:")
        for cmd in missing:
            print(f"  - {cmd}")
        return 1

    print()
    print("✅ All expected commands are available via MCP")
    return 0


def mode_full(
    output_file: Path = None,
    server_id: str = "ai-editor-server",
    verbose: bool = False,
) -> int:
    """Run all checks: discover, check, and verify."""
    print("=" * 80)
    print("Full Command Inventory")
    print("=" * 80)
    print()

    exit_code = 0

    # 1. Discover
    print("\n[1/3] Discovering commands from registry...")
    print("-" * 80)
    if mode_discover(output_file, verbose) != 0:
        exit_code = 1
    print()

    # 2. Check
    print("\n[2/3] Checking command registration...")
    print("-" * 80)
    if mode_check(verbose) != 0:
        exit_code = 1
    print()

    # 3. Verify
    print("\n[3/3] Verifying via MCP interface...")
    print("-" * 80)
    if mode_verify(server_id, verbose) != 0:
        exit_code = 1
    print()

    print("=" * 80)
    if exit_code == 0:
        print("✅ All checks passed")
    else:
        print("⚠️  Some checks failed")
    print("=" * 80)

    return exit_code


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Command Inventory Utility - Discover and verify MCP commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full inventory (discover + check + verify)
  %(prog)s

  # Only discover commands and update documentation
  %(prog)s --mode discover

  # Only check command registration
  %(prog)s --mode check

  # Only verify via MCP
  %(prog)s --mode verify

  # Custom output file
  %(prog)s --mode discover --output custom_inventory.md
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["discover", "check", "verify", "full"],
        default="full",
        help="Operation mode (default: full)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for discover mode (default: docs/COMMAND_INVENTORY.md)",
    )

    parser.add_argument(
        "--server-id",
        default="ai-editor-server",
        help="Server ID for verify mode (default: ai-editor-server)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    try:
        if args.mode == "discover":
            return mode_discover(args.output, args.verbose)
        elif args.mode == "check":
            return mode_check(args.verbose)
        elif args.mode == "verify":
            return mode_verify(args.server_id, args.verbose)
        elif args.mode == "full":
            return mode_full(args.output, args.server_id, args.verbose)
        else:
            parser.error(f"Unknown mode: {args.mode}")
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
