"""
Git integration for automatic commits.

When ``ai_editor.git_commit_on_write`` is true, mutating commands should call
:func:`commit_after_write` after a successful write so changes are staged and committed.
When false, only filesystem history applies — callers must still use
:class:`ai_editor.core.backup_manager.BackupManager` before overwriting or deleting
files (see :mod:`ai_editor.core.file_write_history`).

Refactor commands may also commit *before* the operation (see command docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

CONFIG_KEY_GIT_COMMIT_ON_WRITE = "git_commit_on_write"


def get_git_commit_on_write_from_config(
    config_data: Optional[Mapping[str, Any]] = None,
) -> bool:
    """
    Read whether git commit on write is enabled from config.

    Looks at ai_editor.git_commit_on_write. If config_data is None or key
    is missing, returns False.

    Args:
        config_data: Full config dict (e.g. from load_raw_config). If None, returns False.

    Returns:
        True if git commit after (and before refactor) should be performed.
    """
    if not config_data:
        return False
    ca = config_data.get("ai_editor")
    if not isinstance(ca, Mapping):
        return False
    return bool(ca.get(CONFIG_KEY_GIT_COMMIT_ON_WRITE))


def is_git_repository(root_dir: Path) -> bool:
    """
    Check if directory is a git repository.

    Args:
        root_dir: Root directory to check

    Returns:
        True if directory is a git repository, False otherwise
    """
    git_dir = root_dir / ".git"
    return git_dir.exists() and git_dir.is_dir()


def is_git_available() -> bool:
    """
    Check if git command is available in system.

    Returns:
        True if git is available, False otherwise
    """
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


def create_git_commit(
    root_dir: Path,
    file_path: Path,
    commit_message: str,
) -> Tuple[bool, Optional[str]]:
    """
    Create git commit for file changes.

    Args:
        root_dir: Git repository root directory
        file_path: Path to file that was changed (relative to root_dir)
        commit_message: Commit message

    Returns:
        Tuple of (success, error_message)
    """
    if not is_git_available():
        return (False, "Git is not available in system")

    if not is_git_repository(root_dir):
        return (False, "Directory is not a git repository")

    try:
        # Get relative path from root_dir
        try:
            relative_path = str(file_path.relative_to(root_dir))
        except ValueError:
            # If not relative, use absolute path
            relative_path = str(file_path)

        # Stage file
        result = subprocess.run(
            ["git", "add", relative_path],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, f"Failed to stage file: {result.stderr}")

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # No changes to commit
            logger.info(f"No changes to commit for {relative_path}")
            return (True, None)

        # Create commit
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, f"Failed to create commit: {result.stderr}")

        logger.info(f"Git commit created: {commit_message}")
        return (True, None)
    except subprocess.TimeoutExpired:
        return (False, "Git command timed out")
    except Exception as e:
        logger.error(f"Error creating git commit: {e}")
        return (False, str(e))


def create_git_commit_paths(
    root_dir: Path,
    file_paths: List[Path],
    commit_message: str,
) -> Tuple[bool, Optional[str]]:
    """
    Stage multiple paths and create a single git commit.

    Args:
        root_dir: Git repository root directory
        file_paths: Paths to files/dirs that were changed (relative to root_dir or absolute)
        commit_message: Commit message

    Returns:
        Tuple of (success, error_message)
    """
    if not file_paths:
        return (True, None)
    if not is_git_available():
        return (False, "Git is not available in system")
    if not is_git_repository(root_dir):
        return (False, "Directory is not a git repository")

    try:
        rel_paths: List[str] = []
        for fp in file_paths:
            try:
                rel_paths.append(str(Path(fp).relative_to(root_dir)))
            except ValueError:
                rel_paths.append(str(Path(fp).resolve()))

        for rel in rel_paths:
            result = subprocess.run(
                ["git", "add", rel],
                cwd=root_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return (False, f"Failed to stage {rel}: {result.stderr}")

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info("No changes to commit")
            return (True, None)

        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, f"Failed to create commit: {result.stderr}")
        logger.info(f"Git commit created: {commit_message}")
        return (True, None)
    except subprocess.TimeoutExpired:
        return (False, "Git command timed out")
    except Exception as e:
        logger.error(f"Error creating git commit: {e}")
        return (False, str(e))


def commit_after_write(
    root_dir: Path,
    paths: List[Path],
    command_name: str,
    commit_message_override: Optional[str] = None,
    config_data: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    After a write command: create git commit if config has git_commit_on_write,
    otherwise do nothing (caller is responsible for backup/version).

    For refactor commands, call this also *before* the operation with
    commit_message_override like "Before split_class: path/to/file.py".

    Args:
        root_dir: Project root (git repo root)
        paths: One or more file/dir paths that were written
        command_name: Command name for default message (e.g. "cst_save_tree")
        commit_message_override: If provided, use as commit message
        config_data: Config dict to read ai_editor.git_commit_on_write. If None, no commit.

    Returns:
        Tuple of (success, error_message). (True, None) when no commit was requested.
    """
    if not get_git_commit_on_write_from_config(config_data):
        return (True, None)
    msg = (
        commit_message_override or f"{command_name}: {paths[0].name}"
        if paths
        else command_name
    )
    if len(paths) == 1:
        return create_git_commit(root_dir, paths[0], msg)
    return create_git_commit_paths(root_dir, paths, msg)
