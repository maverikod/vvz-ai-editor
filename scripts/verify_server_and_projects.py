"""
Verify server connectivity, workers, and project cleanup/recreate via server commands.

Uses the same command classes as the server (list_projects, project_set_mark_del, create_project).
Does NOT create or edit .py code in test_data (per project rules: only via server via MCP).
Console app creation/editing in test_data must be done via MCP Proxy once server is registered.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


async def main() -> int:
    """Run verification: list projects, delete those in test_data, create proj1 and proj2."""
    _setup_logging()
    logger = logging.getLogger(__name__)

    try:
        from ai_editor.commands.project_management_mcp_commands import (
            CreateProjectMCPCommand,
            DeleteProjectMCPCommand,
            ListProjectsMCPCommand,
        )
    except ImportError as e:
        logger.error("Import failed: %s", e)
        return 1

    root_dir = str(PROJECT_ROOT)
    test_data_path = PROJECT_ROOT / "test_data"

    # 1. List projects
    logger.info("Listing projects...")
    list_cmd = ListProjectsMCPCommand()
    list_result = await list_cmd.execute()
    if hasattr(list_result, "error") and list_result.error:
        logger.error("list_projects failed: %s", list_result.error)
        return 1
    projects = (
        list_result.data.get("projects", []) if hasattr(list_result, "data") else []
    )
    count = list_result.data.get("count", 0) if hasattr(list_result, "data") else 0
    logger.info("Found %d projects", count)

    # Get watch_dir_id from any project under test_data (needed for create_project)
    watch_dir_id = None
    for p in projects:
        root_path = p.get("root_path") or p.get("root_path", "")
        if str(test_data_path) in root_path or root_path.startswith(
            str(test_data_path)
        ):
            watch_dir_id = p.get("watch_dir_id")
            if watch_dir_id:
                break
    if not watch_dir_id and projects:
        watch_dir_id = projects[0].get("watch_dir_id")
    if not watch_dir_id:
        # From config.json worker.watch_dirs[0].id
        watch_dir_id = "550e8400-e29b-41d4-a716-446655440001"
        logger.info("Using watch_dir_id from config: %s", watch_dir_id)

    # 2. Delete all projects whose root_path is under test_data
    to_delete = [
        p
        for p in projects
        if (p.get("root_path") or "").startswith(str(test_data_path))
        or str(test_data_path) in (p.get("root_path") or "")
    ]
    delete_cmd = DeleteProjectMCPCommand()
    for p in to_delete:
        pid = p.get("id")
        if not pid:
            continue
        logger.info(
            "Deleting project %s (%s)", pid, p.get("name", p.get("root_path", ""))
        )
        del_result = await delete_cmd.execute(project_id=pid, delete_files=False)
        if hasattr(del_result, "error") and del_result.error:
            logger.warning("project_set_mark_del %s failed: %s", pid, del_result.error)
        else:
            logger.info("Deleted project %s", pid)

    # 3. Create proj1 and proj2
    create_cmd = CreateProjectMCPCommand()
    for name, desc in [("proj1", "Test project 1"), ("proj2", "Test project 2")]:
        logger.info("Creating project %s...", name)
        create_result = await create_cmd.execute(
            root_dir=root_dir,
            watch_dir_id=watch_dir_id,
            project_name=name,
            description=desc,
        )
        if hasattr(create_result, "error") and create_result.error:
            logger.error("create_project %s failed: %s", name, create_result.error)
        else:
            pid = (
                create_result.data.get("project_id")
                if hasattr(create_result, "data")
                else None
            )
            logger.info("Created project %s -> %s", name, pid)

    logger.info(
        "Verification done. Creating/editing .py console apps in test_data "
        "must be done via MCP Proxy (ai-editor-server); register the server in the proxy first."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
