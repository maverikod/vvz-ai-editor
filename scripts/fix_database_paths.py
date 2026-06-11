"""
Script to check and fix file paths in database.

This script:
1. Reads watch_dirs from config
2. Checks all file paths in database
3. Normalizes paths to absolute resolved paths (relative to project root)
4. Updates paths in database if they need fixing

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_editor.core.database import CodeDatabase
from ai_editor.core.database.base import create_driver_config_for_worker
from ai_editor.core.path_normalization import normalize_path_simple
from ai_editor.core.project_resolution import normalize_root_dir
from ai_editor.core.project_discovery import find_project_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_watch_dirs(config: Dict[str, Any]) -> List[Path]:
    """Extract watch_dirs from config (ai_editor.worker.watch_dirs only)."""
    ai_editor_config = config.get("ai_editor", {})
    worker_config = ai_editor_config.get("worker", {})
    watch_dirs = worker_config.get("watch_dirs", [])

    # Resolve all paths
    resolved_dirs = []
    for watch_dir in watch_dirs:
        if watch_dir:
            try:
                resolved = Path(watch_dir).resolve()
                if resolved.exists():
                    resolved_dirs.append(resolved)
                else:
                    logger.warning(f"Watch dir does not exist: {watch_dir}")
            except Exception as e:
                logger.warning(f"Failed to resolve watch dir {watch_dir}: {e}")

    return resolved_dirs


def check_file_path(
    file_path: str,
    project_id: str,
    project_root: Path,
    watch_dirs: List[Path],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if file path is correctly normalized.

    Args:
        file_path: Current file path from database
        project_id: Project ID
        project_root: Project root directory (from database)
        watch_dirs: List of watched directories

    Returns:
        Tuple of (is_correct, normalized_path, error_message)
    """
    try:
        # Normalize current path
        current_path = Path(file_path)
        normalized_path = normalize_path_simple(file_path)

        # Check if path exists
        path_obj = Path(normalized_path)
        if not path_obj.exists():
            return False, normalized_path, f"File does not exist: {normalized_path}"

        # Verify path is within project root
        try:
            path_obj.relative_to(project_root)
        except ValueError:
            # Path is outside project root - try to find correct project root
            try:
                # Try to find project root for this file
                project_root_obj = find_project_root(path_obj, watch_dirs)
                if project_root_obj:
                    # File belongs to a different project root
                    return (
                        False,
                        normalized_path,
                        f"File is outside project root. Correct root: {project_root_obj.root_path}",
                    )
                else:
                    return (
                        False,
                        normalized_path,
                        f"File is outside project root and no project found",
                    )
            except Exception as e:
                return False, normalized_path, f"Error finding project root: {e}"

        # Check if normalized path matches current path
        # Also check if path uses symlinks (resolve() resolves symlinks)
        current_resolved = str(Path(file_path).resolve())
        if normalized_path != file_path:
            return (
                False,
                normalized_path,
                f"Path needs normalization: {file_path} -> {normalized_path}",
            )

        # Check if path uses symlinks (if original path != resolved path)
        if str(current_path) != str(current_path.resolve()):
            # Path contains symlinks - this is OK, but log it
            logger.debug(f"Path contains symlinks: {file_path} -> {normalized_path}")

        return True, normalized_path, None

    except Exception as e:
        return False, None, f"Error checking path: {e}"


def fix_database_paths(
    database: CodeDatabase,
    config: Dict[str, Any],
    dry_run: bool = True,
    verbose: bool = False,
    show_examples: int = 10,
) -> Dict[str, Any]:
    """
    Check and fix all file paths in database.

    Args:
        database: Database instance
        config: Configuration dict
        dry_run: If True, only check without updating

    Returns:
        Statistics dictionary
    """
    stats = {
        "total_files": 0,
        "correct_paths": 0,
        "incorrect_paths": 0,
        "fixed_paths": 0,
        "errors": 0,
        "files_outside_project": 0,
        "files_not_found": 0,
        "example_paths": [],
    }

    # Get watch_dirs
    watch_dirs = get_watch_dirs(config)
    logger.info(f"Watch directories: {[str(d) for d in watch_dirs]}")

    # Get all projects
    projects = database._fetchall("SELECT id, root_path FROM projects")
    logger.info(f"Found {len(projects)} projects in database")

    # Process each project
    for project_row in projects:
        project_id = project_row["id"]
        project_root_str = project_row["root_path"]

        try:
            project_root = normalize_root_dir(project_root_str)
        except (FileNotFoundError, NotADirectoryError) as e:
            logger.warning(f"Project root does not exist: {project_root_str} ({e})")
            continue

        logger.info(f"\nProcessing project {project_id} (root: {project_root})")

        # Get all files for this project
        files = database.get_project_files(project_id, include_deleted=False)
        logger.info(f"  Found {len(files)} files in project")

        for file_record in files:
            stats["total_files"] += 1
            file_id = file_record["id"]
            file_path = file_record["path"]

            try:
                # Check if path is correct
                is_correct, normalized_path, error_msg = check_file_path(
                    file_path, project_id, project_root, watch_dirs
                )

                if is_correct:
                    stats["correct_paths"] += 1
                    if verbose:
                        logger.info(f"  ✓ {file_path}")
                    elif len(stats["example_paths"]) < show_examples:
                        stats["example_paths"].append(file_path)
                    logger.debug(f"  ✓ {file_path}")
                else:
                    stats["incorrect_paths"] += 1

                    if error_msg:
                        if "does not exist" in error_msg:
                            stats["files_not_found"] += 1
                        elif "outside project root" in error_msg:
                            stats["files_outside_project"] += 1

                    logger.warning(f"  ✗ {file_path}")
                    logger.warning(f"    Error: {error_msg}")

                    if normalized_path and normalized_path != file_path:
                        logger.info(f"    Should be: {normalized_path}")

                        if not dry_run:
                            try:
                                # Update path in database
                                database._execute(
                                    "UPDATE files SET path = ?, updated_at = julianday('now') WHERE id = ?",
                                    (normalized_path, file_id),
                                )
                                database._commit()
                                stats["fixed_paths"] += 1
                                logger.info(f"    ✓ Fixed: {file_id}")
                            except Exception as e:
                                stats["errors"] += 1
                                logger.error(f"    ✗ Failed to fix: {e}")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"  ✗ Error processing file {file_id} ({file_path}): {e}")

    return stats


def main() -> None:
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Check and fix file paths in database")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to config.json file",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to database file (overrides config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Only check, don't update (default: True)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply fixes (overrides --dry-run)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed information about each file",
    )
    parser.add_argument(
        "--show-examples",
        type=int,
        default=10,
        help="Show N examples of correct paths (default: 10)",
    )

    args = parser.parse_args()

    # Load config
    if not args.config.exists():
        logger.error(f"Config file not found: {args.config}")
        sys.exit(1)

    config = load_config(args.config)

    # Get database path
    if args.db_path:
        db_path = args.db_path
    else:
        ai_editor_config = config.get("ai_editor", {})
        db_path = Path(ai_editor_config.get("db_path", "data/ai_editor.db"))

    if not db_path.exists():
        logger.error(f"Database file not found: {db_path}")
        sys.exit(1)

    logger.info(f"Using database: {db_path}")

    # Determine if dry run
    dry_run = not args.apply if args.apply else args.dry_run

    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    else:
        logger.warning("APPLY MODE - Changes will be written to database!")
        response = input("Are you sure? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Aborted by user")
            sys.exit(0)

    # Connect to database
    driver_config = create_driver_config_for_worker(db_path, "sqlite_proxy")
    database = CodeDatabase(driver_config)

    # Fix paths
    stats = fix_database_paths(
        database,
        config,
        dry_run=dry_run,
        verbose=args.verbose,
        show_examples=args.show_examples,
    )

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total files checked: {stats['total_files']}")
    logger.info(f"Correct paths: {stats['correct_paths']}")
    logger.info(f"Incorrect paths: {stats['incorrect_paths']}")
    logger.info(f"  - Files not found: {stats['files_not_found']}")
    logger.info(f"  - Files outside project: {stats['files_outside_project']}")
    if not dry_run:
        logger.info(f"Fixed paths: {stats['fixed_paths']}")
    else:
        logger.info(
            f"Paths that would be fixed: {stats['incorrect_paths'] - stats['errors']}"
        )
    logger.info(f"Errors: {stats['errors']}")

    # Show example paths
    if stats["example_paths"]:
        logger.info("\nExample correct paths:")
        for example_path in stats["example_paths"]:
            logger.info(f"  {example_path}")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
