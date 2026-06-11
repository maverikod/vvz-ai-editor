"""
CST tree saver - save tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ..backup_manager import BackupManager
from ..file_lock import file_lock
from .models import CSTTree, TreeNodeMetadata, TreeOperation
from .tree_builder import (
    _attach_disk_snapshot,
    _read_logical_py_source_sync_disk,
    create_tree_from_code,
    get_tree,
    reload_tree_from_file,
    remove_tree,
)
from .node_stable_id import strip_inline_node_id_lines_from_source
from .tree_sidecar import write_sidecar_atomic
from .tree_save_verification import (
    FILE_CHANGED_SINCE_LOAD,
    WRITE_VERIFY_FAILED,
    SaveVerificationError,
    assert_file_bytes_match,
    assert_replay_matches,
    assert_tree_module_integrity,
    disk_matches_tree_snapshot,
)

logger = logging.getLogger(__name__)


def save_tree_to_file(
    tree_id: str,
    file_path: str,
    root_dir: Path,
    project_id: str,
    database,
    validate: bool = True,
    backup: bool = True,
    commit_message: Optional[str] = None,
    tree_operations: Optional[Sequence[TreeOperation]] = None,
    pre_modify_metadata_map: Optional[Dict[str, TreeNodeMetadata]] = None,
) -> Dict[str, Any]:
    """
    Save tree to file with atomic operations.

    Process:
    1. Validate entire file through compile() (before any changes)
    2. Create backup via BackupManager (mandatory if file exists)
    3. Generate source code from CST tree (clean ``.py``; sidecar ``<source>.py.tree``
       next to the source holds node ids.)
    4. Write to temporary file
    5. Validate temporary file (compile, linter, type checker)
    6. Atomically replace file via os.replace()
    7. Ensure file record exists (create or update in files table)
    8. Sync file to DB via shared file-level pipeline (sync_file_to_db_atomic)
    9. Git commit (if commit_message provided)
    10. On any error: restore from backup and re-raise

    Args:
        tree_id: Tree ID
        file_path: Target file path (absolute or relative to root_dir)
        root_dir: Project root directory
        project_id: Project ID
        database: Database instance
        validate: Whether to validate file before saving
        backup: Whether to create backup
        commit_message: Optional git commit message
        tree_operations: When non-empty and not None, run replay verification before writing.
        pre_modify_metadata_map: Snapshot of ``metadata_map`` before ``modify_tree`` (combined
            save). Used so replay can remap operation ``node_id`` values removed from the
            post-modify tree.

    Returns:
        Dictionary with result:
        {
            "success": bool,
            "file_path": str,
            "backup_uuid": Optional[str],
            "error": Optional[str]
        }

    Raises:
        ValueError: If tree not found or validation fails
        RuntimeError: If file operations fail
        SaveVerificationError: If disk snapshot, replay, or post-write verification fails
    """
    timings: Dict[str, float] = {}
    t0 = time.perf_counter()
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")
    assert_tree_module_integrity(tree)
    timings["get_tree"] = time.perf_counter() - t0

    # Resolve file path
    t0 = time.perf_counter()
    target_path = Path(file_path)
    if not target_path.is_absolute():
        target_path = (root_dir / target_path).resolve()
    else:
        target_path = target_path.resolve()

    # Ensure directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)
    timings["resolve_path"] = time.perf_counter() - t0

    backup_uuid: Optional[str] = None
    backup_manager: Optional[BackupManager] = None
    temp_file: Optional[Path] = None

    rel_lock_path = (
        str(target_path.relative_to(root_dir))
        if target_path.is_relative_to(root_dir)
        else file_path
    )
    with file_lock(
        target_path,
        mode="full",
        database=database,
        project_id=project_id,
        file_path=rel_lock_path,
    ):
        if target_path.exists():
            suf = target_path.suffix
            if suf == ".py" or (suf == ".tmp" and target_path.stem.endswith(".py")):
                _read_logical_py_source_sync_disk(target_path)

        def try_restore_from_backup() -> None:
            if backup_uuid and backup_manager and target_path.exists():
                try:
                    rel_path = str(target_path.relative_to(root_dir))
                except ValueError:
                    rel_path = str(target_path)
                restore_success, restore_message = backup_manager.restore_file(
                    rel_path, backup_uuid
                )
                if restore_success:
                    logger.info("File restored from backup: %s", restore_message)
                    try:
                        logical_disk, _ = _read_logical_py_source_sync_disk(target_path)
                        _attach_disk_snapshot(tree, logical_disk)
                    except OSError:
                        logger.warning(
                            "Could not refresh disk snapshot after backup restore (%s)",
                            target_path,
                        )
                else:
                    logger.error(
                        "Failed to restore file from backup: %s",
                        restore_message,
                    )

        try:
            # Step 1: Disk snapshot vs on-disk UTF-8 (before backup); capture text for replay
            t0 = time.perf_counter()
            disk_source_for_replay = ""
            if target_path.exists():
                if tree.disk_source_sha256_hex is not None:
                    if not disk_matches_tree_snapshot(target_path, tree):
                        logger.warning(
                            "CST save: %s no longer matches snapshot on tree %s; "
                            "reloading from disk and aborting save.",
                            target_path,
                            tree_id,
                        )
                        if reload_tree_from_file(tree_id) is None:
                            raise SaveVerificationError(
                                code=FILE_CHANGED_SINCE_LOAD,
                                details={
                                    "target_path": str(target_path),
                                    "tree_id": tree_id,
                                    "reason": "disk_drift_reload_failed_tree_missing",
                                },
                            )
                        raise SaveVerificationError(
                            code=FILE_CHANGED_SINCE_LOAD,
                            details={
                                "target_path": str(target_path),
                                "tree_id": tree_id,
                                "resynced_tree_from_disk": True,
                            },
                        )
                disk_source_for_replay = target_path.read_text(encoding="utf-8")
                if validate:
                    try:
                        compile(disk_source_for_replay, str(target_path), "exec")
                    except SyntaxError as e:
                        logger.warning(f"Original file has syntax errors: {e}")
            timings["validate_original"] = time.perf_counter() - t0

            from ..path_normalization import normalize_path_simple

            normalized_path = normalize_path_simple(str(target_path))
            existing_files_early = []
            file_id = None
            sync_result: dict[str, Any] = {"success": True, "skipped_db": True}
            if database is not None:
                from ..database_client.objects.file import File

                existing_files_early = database.select(
                    "files",
                    where={
                        "path": normalized_path,
                        "project_id": project_id,
                    },
                )
            # Step 2: Create backup (mandatory before overwriting existing file)
            t0 = time.perf_counter()
            if target_path.exists():
                backup_manager = BackupManager(root_dir)
                try:
                    rel_path = str(target_path.relative_to(root_dir))
                except ValueError:
                    rel_path = str(target_path)
                backup_uuid = backup_manager.create_backup(
                    target_path,
                    command="cst_save_tree",
                    comment=f"Before saving CST tree {tree_id}",
                )
                if not backup_uuid:
                    raise RuntimeError(
                        "Backup to old_code (versions) is mandatory before write; "
                        "create_backup failed. Aborting cst_save_tree."
                    )
            timings["backup"] = time.perf_counter() - t0

            # Step 3: Generate source code from CST tree (clean .py; sidecar holds ids).
            t0 = time.perf_counter()
            clean_source_code = strip_inline_node_id_lines_from_source(tree.module.code)
            persisted_source = clean_source_code
            prebuilt_cst_tree_for_sync = tree
            timings["code_gen"] = time.perf_counter() - t0

            ops_list = list(tree_operations) if tree_operations is not None else None
            if ops_list:
                lookup_stub: Optional[CSTTree] = None
                if pre_modify_metadata_map is not None:
                    lookup_stub = create_tree_from_code(
                        str(target_path),
                        disk_source_for_replay,
                        persist_sidecar=False,
                        register_in_memory=True,
                    )
                    lookup_stub.metadata_map.update(pre_modify_metadata_map)
                try:
                    assert_replay_matches(
                        original_source=disk_source_for_replay,
                        target_path=target_path,
                        tree=tree,
                        tree_operations=ops_list,
                        id_lookup_tree=lookup_stub,
                    )
                finally:
                    if lookup_stub is not None:
                        remove_tree(lookup_stub.tree_id)

            # Step 4: Write to target.tmp (same directory as target)
            t0 = time.perf_counter()
            temp_file = Path(str(target_path) + ".tmp")
            try:
                temp_file.write_text(persisted_source, encoding="utf-8")
            except Exception as e:
                raise RuntimeError(f"Failed to write temporary file: {e}") from e
            timings["write_temp"] = time.perf_counter() - t0

            # Step 5: Validate temporary file
            t0 = time.perf_counter()
            if validate:
                try:
                    compile(persisted_source, str(temp_file), "exec")
                except SyntaxError as e:
                    raise ValueError(f"Generated code has syntax errors: {e}") from e
            timings["validate_temp"] = time.perf_counter() - t0

            # Step 6: Atomically replace file
            t0 = time.perf_counter()
            os.replace(str(temp_file), str(target_path))
            temp_file = None  # File was moved, don't delete it
            timings["replace"] = time.perf_counter() - t0

            assert_file_bytes_match(target_path=target_path, expected=persisted_source)

            _attach_disk_snapshot(tree, persisted_source)

            # Step 7–8: Optional DB sync (skipped when database is None)
            t0 = time.perf_counter()
            if database is not None:
                from ..database_client.objects.file import File

                lines = clean_source_code.count("\n") + (1 if clean_source_code else 0)
                stripped = clean_source_code.lstrip()
                has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
                last_modified_timestamp = target_path.stat().st_mtime
                last_modified = datetime.fromtimestamp(last_modified_timestamp)

                if existing_files_early:
                    file_record = existing_files_early[0]
                    file_obj = File(
                        id=file_record["id"],
                        project_id=project_id,
                        path=normalized_path,
                        lines=lines,
                        last_modified=last_modified,
                        has_docstring=has_docstring,
                    )
                    updated_file = database.update_file(file_obj)
                    file_id = updated_file.id
                else:
                    file_obj = File(
                        project_id=project_id,
                        path=normalized_path,
                        lines=lines,
                        last_modified=last_modified,
                        has_docstring=has_docstring,
                    )
                    created_file = database.create_file(file_obj)
                    file_id = created_file.id
                timings["db_file_record"] = time.perf_counter() - t0

                t0 = time.perf_counter()
                from ..database.file_tree_sync import sync_file_to_db_atomic

                sync_result = sync_file_to_db_atomic(
                    database=database,
                    project_id=project_id,
                    absolute_path=normalized_path,
                    source_code=persisted_source,
                    file_mtime=last_modified_timestamp,
                    file_id=file_id,
                    skip_file_edit_lock=False,
                    prebuilt_cst_tree=prebuilt_cst_tree_for_sync,
                )
                timings["sync_file_to_db"] = time.perf_counter() - t0

                if not sync_result.get("success"):
                    raise RuntimeError(
                        "Failed to sync file to DB: " f"{sync_result.get('error')}"
                    )
            else:
                timings["db_file_record"] = 0.0
                timings["sync_file_to_db"] = 0.0

            if prebuilt_cst_tree_for_sync is not None:
                try:
                    write_sidecar_atomic(target_path, tree)
                except OSError as exc:
                    logger.warning(
                        "CST sidecar write after save failed for %s: %s",
                        target_path,
                        exc,
                    )

            if database is not None and not sync_result.get("success"):
                raise RuntimeError(
                    "Failed to sync file to DB: " f"{sync_result.get('error')}"
                )

            # Step 9: Git commit (if requested)
            if commit_message:
                from ..git_integration import create_git_commit

                git_success, git_error = create_git_commit(
                    root_dir, target_path, commit_message
                )
                if not git_success:
                    logger.warning(f"Failed to create git commit: {git_error}")

            return {
                "success": True,
                "file_path": str(target_path),
                "file_id": file_id,
                "backup_uuid": backup_uuid,
                "sync_result": sync_result,
                "timings": timings,
            }

        except SaveVerificationError as exc:
            if exc.code == WRITE_VERIFY_FAILED:
                logger.critical(
                    "CST save_tree_to_file post-write byte verification failed: %s",
                    exc.details,
                    exc_info=True,
                )
                try_restore_from_backup()
            raise

        except Exception as e:
            try_restore_from_backup()
            logger.error(f"Error saving tree to file: {e}", exc_info=True)
            return {
                "success": False,
                "file_path": str(target_path),
                "backup_uuid": backup_uuid,
                "error": str(e),
            }

        finally:
            # Clean up .tmp if we did not replace (e.g. on failure)
            if temp_file is not None and temp_file.exists():
                try:
                    temp_file.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("Failed to delete temporary file: %s", e)
