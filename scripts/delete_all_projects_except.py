"""
Delete all projects from the watched directory except one (e.g. vast_srv).

Run with the ai-editor SERVER RUNNING (driver must be up).
Uses the same config and driver socket as the server.

Usage (from project root, with .venv activated):
  python scripts/delete_all_projects_except.py vast_srv
  python scripts/delete_all_projects_except.py vast_srv --config /path/to/config.json

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Project root must be on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete all projects except the one given by name (server must be running)."
    )
    parser.add_argument(
        "keep_name",
        type=str,
        help="Project name to keep (e.g. vast_srv). All others will be deleted.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to config.json (default: config.json in cwd).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list projects that would be deleted; do not delete.",
    )
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        logger.error("Config not found: %s", config_path)
        return 1

    async def run() -> int:
        from ai_editor.commands.base_mcp_command import (
            BaseMCPCommand,
            _get_socket_path_from_db_path,
        )
        from ai_editor.commands.base_mcp_command_open_db import (
            open_database_from_config_impl,
        )
        from ai_editor.commands.project_deletion import DeleteProjectCommand
        from ai_editor.core.storage_paths import (
            load_raw_config,
            resolve_storage_paths,
        )

        def resolve_config() -> Path:
            return config_path

        db = open_database_from_config_impl(
            resolve_config_path_fn=resolve_config,
            get_socket_path_fn=_get_socket_path_from_db_path,
        )
        try:
            projects = db.list_projects()
            to_keep = args.keep_name.strip()
            to_delete = [p for p in projects if (p.name or "").strip() != to_keep]
            if not to_delete:
                logger.info("No projects to delete (only %s present).", to_keep)
                return 0
            logger.info(
                "Keeping %r. Will delete %s project(s): %s",
                to_keep,
                len(to_delete),
                [p.name for p in to_delete[:5]]
                + (["..."] if len(to_delete) > 5 else []),
            )
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            version_dir = (
                config_data.get("ai_editor", {})
                .get("file_watcher", {})
                .get("version_dir")
            )
            if not version_dir:
                version_dir = str(config_path.parent / "data" / "versions")
            trash_dir = str(storage.trash_dir)

            if args.dry_run:
                for p in to_delete:
                    logger.info("  [dry-run] would delete: %s (%s)", p.name, p.id)
                return 0

            for i, p in enumerate(to_delete, 1):
                logger.info("[%s/%s] Deleting %s (%s)...", i, len(to_delete), p.name, p.id)
                cmd = DeleteProjectCommand(
                    database=db,
                    project_id=p.id,
                    dry_run=False,
                    delete_from_disk=True,
                    version_dir=version_dir,
                    trash_dir=trash_dir,
                    config_path=str(config_path),
                )
                result = await cmd.execute()
                if result.get("success"):
                    logger.info("  Deleted: %s", result.get("message", "OK"))
                else:
                    logger.error(
                        "  Failed: %s",
                        result.get("message", result.get("error", "unknown")),
                    )
            logger.info("Done. Remaining project: %s", to_keep)
            return 0
        finally:
            db.disconnect()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
