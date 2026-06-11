"""
CLI commands for backup management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import json
import sys
from pathlib import Path

from ..core.backup_manager import BackupManager


def list_files_cmd(args: argparse.Namespace) -> int:
    """List all backed up files."""
    try:
        root_dir = Path(args.root_dir).resolve()
        manager = BackupManager(root_dir)

        files = manager.list_files()

        # Get additional info from index
        index = manager._load_index()
        files_with_info = []
        for file_info in files:
            file_path = file_info["file_path"]
            # Find latest backup for this file
            versions = manager.list_versions(file_path)
            if versions:
                latest = versions[0]
                backup_uuid = latest["uuid"]
                backup_info = index.get(backup_uuid, {})
                file_info_with_details: dict = file_info.copy()
                file_info_with_details["command"] = backup_info.get("command", "")
                file_info_with_details["related_files"] = (
                    backup_info.get("related_files", "").split(",")
                    if backup_info.get("related_files")
                    else []
                )
                files_with_info.append(file_info_with_details)
            else:
                files_with_info.append(file_info)

        if args.json:
            print(
                json.dumps(
                    {"files": files_with_info, "count": len(files_with_info)}, indent=2
                )
            )
        else:
            print(f"Backed up files ({len(files_with_info)}):")
            for file_info in files_with_info:
                print(f"  {file_info['file_path']}")
                if file_info.get("command"):
                    print(f"    Command: {file_info['command']}")
                if file_info.get("related_files"):
                    print(f"    Related files: {', '.join(file_info['related_files'])}")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def list_versions_cmd(args: argparse.Namespace) -> int:
    """List all versions of a backed up file."""
    try:
        root_dir = Path(args.root_dir).resolve()
        manager = BackupManager(root_dir)

        versions = manager.list_versions(args.file_path)

        # list_versions now returns versions with command and related_files
        # No need to add them again, they're already included

        if args.json:
            print(
                json.dumps(
                    {
                        "file_path": args.file_path,
                        "versions": versions,
                        "count": len(versions),
                    },
                    indent=2,
                )
            )
        else:
            print(f"Versions of {args.file_path} ({len(versions)}):")
            for version in versions:
                print(f"  UUID: {version['uuid']}")
                print(f"    Timestamp: {version['timestamp']}")
                print(
                    f"    Size: {version['size_bytes']} bytes, "
                    f"{version['size_lines']} lines"
                )
                if version.get("command"):
                    print(f"    Command: {version['command']}")
                if version.get("related_files"):
                    print(f"    Related files: {', '.join(version['related_files'])}")
                print()

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def restore_cmd(args: argparse.Namespace) -> int:
    """Restore file from backup."""
    try:
        root_dir = Path(args.root_dir).resolve()
        manager = BackupManager(root_dir)

        success, message = manager.restore_file(args.file_path, args.backup_uuid)

        if success:
            print(f"Success: {message}")
            return 0
        else:
            print(f"Error: {message}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def delete_cmd(args: argparse.Namespace) -> int:
    """Delete backup from history."""
    try:
        root_dir = Path(args.root_dir).resolve()
        manager = BackupManager(root_dir)

        success, message = manager.delete_backup(args.backup_uuid)

        if success:
            print(f"Success: {message}")
            return 0
        else:
            print(f"Error: {message}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def clear_all_cmd(args: argparse.Namespace) -> int:
    """Clear all backups and history."""
    try:
        root_dir = Path(args.root_dir).resolve()
        manager = BackupManager(root_dir)

        if not args.force:
            response = input("Are you sure you want to clear all backups? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled.")
                return 0

        success, message = manager.clear_all()

        if success:
            print(f"Success: {message}")
            return 0
        else:
            print(f"Error: {message}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Backup management CLI")
    parser.add_argument(
        "--root-dir",
        type=str,
        default=".",
        help="Project root directory (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list-files command
    list_files_parser = subparsers.add_parser(
        "list-files", help="List all backed up files"
    )
    list_files_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # list-versions command
    list_versions_parser = subparsers.add_parser(
        "list-versions", help="List all versions of a backed up file"
    )
    list_versions_parser.add_argument("file_path", type=str, help="Original file path")
    list_versions_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # restore command
    restore_parser = subparsers.add_parser("restore", help="Restore file from backup")
    restore_parser.add_argument("file_path", type=str, help="Original file path")
    restore_parser.add_argument(
        "--backup-uuid",
        type=str,
        help="UUID of backup to restore (optional, uses latest)",
    )

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete backup from history")
    delete_parser.add_argument("backup_uuid", type=str, help="UUID of backup to delete")

    # clear-all command
    clear_all_parser = subparsers.add_parser(
        "clear-all", help="Clear all backups and history"
    )
    clear_all_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "list-files":
        return list_files_cmd(args)
    elif args.command == "list-versions":
        return list_versions_cmd(args)
    elif args.command == "restore":
        return restore_cmd(args)
    elif args.command == "delete":
        return delete_cmd(args)
    elif args.command == "clear-all":
        return clear_all_cmd(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
