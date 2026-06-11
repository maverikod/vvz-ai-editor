"""
Save JSON tree to file with backup and DB file_data update (non-CST path).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..backup_manager import BackupManager
from ..file_lock import file_lock
from ..path_normalization import normalize_path_simple
from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def _serialize_document(root_data: Any) -> str:
    return json.dumps(root_data, indent=2, ensure_ascii=False) + "\n"


def save_json_tree_to_file(
    tree_id: str,
    file_path: str,
    root_dir: Path,
    project_id: str,
    database: Any,
    backup: bool = True,
    create_parent_dirs: bool = True,
) -> Dict[str, Any]:
    """
    Atomic write (.tmp + replace), optional backup, File row + update_file_data_atomic_batch.

    Mirrors write_project_text_lines DB path (AST batch over file contents), not sync_file_to_db_atomic.
    Git commits are handled by the MCP command layer (commit_after_write / config).
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    target_path = Path(file_path)
    if not target_path.is_absolute():
        target_path = (root_dir / target_path).resolve()
    else:
        target_path = target_path.resolve()
    root_dir = root_dir.resolve()

    try:
        target_path.relative_to(root_dir)
    except ValueError:
        return {
            "success": False,
            "file_path": str(target_path),
            "backup_uuid": None,
            "error": "Resolved path escapes project root",
            "error_code": "INVALID_FILE_PATH",
        }

    if target_path.suffix.lower() != ".json":
        raise ValueError(f"Target must be .json: {target_path}")

    if create_parent_dirs:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    elif not target_path.parent.exists():
        return {
            "success": False,
            "file_path": str(target_path),
            "backup_uuid": None,
            "error": f"Parent directory does not exist: {target_path.parent}",
            "error_code": "PARENT_DIR_MISSING",
        }

    source_code = _serialize_document(tree.root_data)
    backup_uuid: Optional[str] = None
    backup_manager: Optional[BackupManager] = None
    temp_file: Optional[Path] = None

    rel_lock_path = str(target_path.relative_to(root_dir))
    with file_lock(
        target_path,
        mode="full",
        database=database,
        project_id=project_id,
        file_path=rel_lock_path,
    ):
        try:
            if backup and target_path.exists():
                backup_manager = BackupManager(root_dir)
                try:
                    rel_path = str(target_path.relative_to(root_dir))
                except ValueError:
                    rel_path = str(target_path)
                backup_uuid = backup_manager.create_backup(
                    target_path,
                    command="json_save_tree",
                    comment=f"Before saving JSON tree {tree_id}",
                )
                if not backup_uuid:
                    raise RuntimeError(
                        "Backup to old_code (versions) is mandatory before write; "
                        "create_backup failed. Aborting json_save_tree."
                    )
            temp_file = Path(str(target_path) + ".tmp")
            temp_file.write_text(source_code, encoding="utf-8")
            os.replace(str(temp_file), str(target_path))
            temp_file = None

            if database is None:
                return {
                    "success": True,
                    "file_path": str(target_path),
                    "backup_uuid": backup_uuid,
                    "skipped_db": True,
                }

            from ..database_client.file_data_batch import update_file_data_atomic_batch
            from ..database_client.objects.base import BaseObject
            from ..database_client.objects.file import File
            from ..database.file_edit_lock import (
                acquire_file_edit_lock_with_retry,
                release_file_edit_lock,
            )

            normalized_path = normalize_path_simple(str(target_path))
            lines_count = len(source_code.splitlines()) if source_code else 0
            stripped = source_code.lstrip()
            has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
            last_modified_timestamp = target_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(last_modified_timestamp)

            existing = database.select(
                "files",
                where={
                    "path": normalized_path,
                    "project_id": project_id,
                },
            )

            transaction_id = database.begin_transaction()
            try:
                if existing:
                    file_record = existing[0]
                    file_obj = File(
                        id=file_record["id"],
                        project_id=project_id,
                        path=normalized_path,
                        lines=lines_count,
                        last_modified=last_modified,
                        has_docstring=has_docstring,
                    )
                    database.update_file(file_obj)
                    file_id = file_obj.id
                    if not acquire_file_edit_lock_with_retry(
                        database, file_id, transaction_id=transaction_id
                    ):
                        database.rollback_transaction(transaction_id)
                        return {
                            "success": False,
                            "file_path": str(target_path),
                            "backup_uuid": backup_uuid,
                            "error": (
                                "File is being edited by another live process (file edit lock). "
                                "Try again shortly."
                            ),
                            "error_code": "FILE_EDIT_LOCKED",
                        }
                else:
                    file_obj = File(
                        project_id=project_id,
                        path=normalized_path,
                        lines=lines_count,
                        last_modified=last_modified,
                        has_docstring=has_docstring,
                    )
                    created = database.create_file(file_obj)
                    file_id = created.id
                    if not acquire_file_edit_lock_with_retry(
                        database, file_id, transaction_id=transaction_id
                    ):
                        database.rollback_transaction(transaction_id)
                        return {
                            "success": False,
                            "file_path": str(target_path),
                            "backup_uuid": backup_uuid,
                            "error": (
                                "File is being edited by another live process (file edit lock). "
                                "Try again shortly."
                            ),
                            "error_code": "FILE_EDIT_LOCKED",
                        }

                if file_id is None:
                    raise RuntimeError(
                        "file_id missing after create/update file record"
                    )
                assert isinstance(file_id, int)

                file_mtime = BaseObject._to_timestamp(last_modified) or 0.0
                update_result = update_file_data_atomic_batch(
                    database=database,
                    file_id=str(file_id),
                    project_id=project_id,
                    source_code=source_code,
                    file_path=str(target_path),
                    file_mtime=file_mtime,
                    transaction_id=transaction_id,
                    skip_file_edit_lock=True,
                )
                if not update_result.get("success"):
                    database.rollback_transaction(transaction_id)
                    return {
                        "success": False,
                        "file_path": str(target_path),
                        "backup_uuid": backup_uuid,
                        "error": update_result.get(
                            "error", "update_file_data_atomic_batch failed"
                        ),
                        "error_code": "UPDATE_FILE_DATA_ERROR",
                    }

                release_file_edit_lock(database, file_id, transaction_id=transaction_id)
                database.commit_transaction(transaction_id)

                tree.file_path = str(target_path)

                return {
                    "success": True,
                    "file_path": str(target_path),
                    "file_id": file_id,
                    "backup_uuid": backup_uuid,
                    "update_result": update_result,
                }
            except Exception:
                database.rollback_transaction(transaction_id)
                raise

        except Exception as e:
            if backup_uuid and backup_manager and target_path.exists():
                try:
                    rel_path = str(target_path.relative_to(root_dir))
                except ValueError:
                    rel_path = str(target_path)
                restore_success, restore_message = backup_manager.restore_file(
                    rel_path, backup_uuid
                )
                if restore_success:
                    logger.info(
                        "json_save_tree restored from backup: %s", restore_message
                    )
                else:
                    logger.error(
                        "json_save_tree backup restore failed: %s",
                        restore_message,
                    )
            logger.exception("json_save_tree failed: %s", e)
            return {
                "success": False,
                "file_path": str(target_path),
                "backup_uuid": backup_uuid,
                "error": str(e),
                "error_code": "JSON_SAVE_ERROR",
            }
        finally:
            if temp_file is not None and temp_file.exists():
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError as ex:
                    logger.warning("Failed to remove temp file: %s", ex)
