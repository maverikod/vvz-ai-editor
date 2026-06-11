"""
Migration script to convert projectid files from old format to JSON format.

Old format: plain UUID4 string
New format: JSON with id and description fields

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import sys
import uuid
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path to import ai_editor
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_editor.core.exceptions import InvalidProjectIdFormatError, ProjectIdError
from ai_editor.core.project_resolution import load_project_info


def migrate_projectid_file(projectid_path: Path, description: str = "") -> bool:
    """
    Migrate a single projectid file from old format to JSON format.

    Args:
        projectid_path: Path to projectid file
        description: Optional description for the project

    Returns:
        True if migration was successful, False if file is already in JSON format

    Raises:
        ProjectIdError: If file is missing or empty
        InvalidProjectIdFormatError: If file format is invalid
    """
    if not projectid_path.exists():
        raise ProjectIdError(
            message=f"Missing projectid file: {projectid_path}",
            projectid_path=str(projectid_path),
        )

    raw = projectid_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ProjectIdError(
            message=f"Empty projectid file: {projectid_path}",
            projectid_path=str(projectid_path),
        )

    # Check if already in JSON format
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "id" in data:
            # Already in JSON format
            return False
    except json.JSONDecodeError:
        # Not JSON, need to migrate
        pass

    # Parse old format (plain UUID4 string)
    try:
        project_id = raw.strip()
        uuid.UUID(project_id)  # Validate UUID format
    except Exception as e:
        raise InvalidProjectIdFormatError(
            message=f"Invalid projectid format: {project_id}",
            projectid_path=str(projectid_path),
        ) from e

    # Create backup
    backup_path = projectid_path.with_suffix(".projectid.backup")
    if not backup_path.exists():
        backup_path.write_text(raw, encoding="utf-8")

    # Write new JSON format
    new_data = {
        "id": project_id,
        "description": description or f"Project {project_id}",
    }
    projectid_path.write_text(
        json.dumps(new_data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return True


def find_all_projectid_files(root_dir: Path) -> List[Path]:
    """
    Find all projectid files in directory tree.

    Args:
        root_dir: Root directory to search

    Returns:
        List of paths to projectid files
    """
    projectid_files = []
    for item in root_dir.rglob("projectid"):
        if item.is_file():
            projectid_files.append(item)
    return projectid_files


def migrate_all_projectid_files(
    root_dirs: List[Path], description: str = "", dry_run: bool = False
) -> Tuple[int, int, int]:
    """
    Migrate all projectid files in given directories.

    Args:
        root_dirs: List of root directories to search
        description: Optional description for projects (if not provided, will use default)
        dry_run: If True, only report what would be migrated without making changes

    Returns:
        Tuple of (migrated_count, already_json_count, error_count)
    """
    migrated_count = 0
    already_json_count = 0
    error_count = 0

    all_projectid_files = []
    for root_dir in root_dirs:
        root_path = Path(root_dir).resolve()
        if not root_path.exists():
            print(f"Warning: Directory does not exist: {root_path}")
            continue
        all_projectid_files.extend(find_all_projectid_files(root_path))

    print(f"Found {len(all_projectid_files)} projectid files")

    for projectid_path in all_projectid_files:
        try:
            if dry_run:
                # Check if needs migration
                raw = projectid_path.read_text(encoding="utf-8").strip()
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict) and "id" in data:
                        print(f"  [SKIP] {projectid_path} - already in JSON format")
                        already_json_count += 1
                    else:
                        print(f"  [WOULD MIGRATE] {projectid_path}")
                        migrated_count += 1
                except json.JSONDecodeError:
                    print(f"  [WOULD MIGRATE] {projectid_path}")
                    migrated_count += 1
            else:
                migrated = migrate_projectid_file(projectid_path, description)
                if migrated:
                    print(f"  [MIGRATED] {projectid_path}")
                    migrated_count += 1
                else:
                    print(f"  [SKIP] {projectid_path} - already in JSON format")
                    already_json_count += 1
        except Exception as e:
            print(f"  [ERROR] {projectid_path}: {e}")
            error_count += 1

    return migrated_count, already_json_count, error_count


def main():
    """Main entry point for migration script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate projectid files from old format to JSON format"
    )
    parser.add_argument(
        "directories",
        nargs="*",
        default=["."],
        help="Directories to search for projectid files (default: current directory)",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Default description for projects (if not provided, will use default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )

    args = parser.parse_args()

    root_dirs = [Path(d).resolve() for d in args.directories]

    print("Project ID Migration Script")
    print("=" * 50)
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    print()

    migrated, already_json, errors = migrate_all_projectid_files(
        root_dirs, args.description, args.dry_run
    )

    print()
    print("=" * 50)
    print(f"Summary:")
    print(f"  Migrated: {migrated}")
    print(f"  Already JSON: {already_json}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
