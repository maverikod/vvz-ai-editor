"""
Validation, file write, and apply logic for the CST replace-ops write path.

Temp file validation, file record update, rollback, and apply_changes.
Used by run_ops_mode (via these helpers).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.backup_manager import BackupManager
from .compose_cst_db import delete_file_data, restore_file_data

logger = logging.getLogger(__name__)


def validate_and_write_temp(
    source_code: str,
    target_path: Path,
    validate_syntax_only: bool = False,
    validate_docstrings: bool = True,
) -> tuple[
    Path,
    Optional[ErrorResult],
    Optional[Dict[str, Any]],
]:
    """
    Write source code to temporary file and validate it.

    Args:
        source_code: Source code to write
        target_path: Target file path
        validate_syntax_only: When True, skip linter and type checker. Docstring
            policy checks follow ``validate_docstrings``.
        validate_docstrings: When False, skip docstring policy checks (linter/mypy
            still run unless validate_syntax_only is True).

    Returns:
        Tuple of (temp_file_path, error_result or None, validation_results or None)
    """
    temp_fd, temp_path_str = tempfile.mkstemp(
        suffix=".py", prefix="cst_compose_", dir=target_path.parent
    )
    temp_file = Path(temp_path_str)

    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(source_code)
    except Exception as e:
        os.close(temp_fd)
        return (
            temp_file,
            ErrorResult(
                message=f"Failed to write temporary file: {e}",
                code="TEMP_FILE_ERROR",
                details={"error": str(e)},
            ),
            None,
        )

    from ..core.cst_module.validation import validate_file_in_temp

    validation_success, _validation_error, validation_results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=not validate_syntax_only,
        validate_type_checker=not validate_syntax_only,
        validate_docstrings=(not validate_syntax_only) and validate_docstrings,
    )

    if not validation_success:
        error_parts = []
        for validation_type, result in validation_results.items():
            if not result.success:
                if result.error_message:
                    error_parts.append(f"{validation_type}: {result.error_message}")
                elif result.errors:
                    error_parts.append(
                        f"{validation_type}: {len(result.errors)} error(s)"
                    )
        error_message = "; ".join(error_parts) if error_parts else "Validation failed"
        validation_details = {
            vt: {
                "success": result.success,
                "error_message": result.error_message,
                "errors": result.errors[:10],
            }
            for vt, result in validation_results.items()
        }
        temp_file.unlink()
        return (
            temp_file,
            ErrorResult(
                message=f"Validation failed: {error_message}",
                code="VALIDATION_ERROR",
                details={
                    "error": error_message,
                    "validation_results": validation_details,
                },
            ),
            validation_results,
        )

    return (temp_file, None, validation_results)


def update_file_record(
    database: Any,
    project_id: str,
    root_path: Path,
    target_path: Path,
    source_code: str,
    file_id: Optional[int],
    transaction_id: Optional[str] = None,
) -> int:
    """
    Add or update file record in database.

    Args:
        database: Database instance
        project_id: Project ID
        root_path: Project root path (unused, for API consistency)
        target_path: Target file path
        source_code: Source code
        file_id: Existing file ID or None

    Returns:
        File ID
    """
    _ = root_path
    lines = source_code.count("\n") + (1 if source_code else 0)
    stripped = source_code.lstrip()
    has_docstring = stripped.startswith('"""') or stripped.startswith("'''")

    if database is None:
        return file_id or 0

    if not file_id:
        from ..core.database_client.objects.file import File
        from ..core.path_normalization import normalize_path_simple

        normalized_path = normalize_path_simple(str(target_path))
        file_obj = File(
            project_id=project_id,
            path=normalized_path,
            lines=lines,
            last_modified=time.time(),
            has_docstring=has_docstring,
        )
        created_file = database.create_file(file_obj)
        return created_file.id

    from ..core.sql_portable import sql_julian_timestamp_now_expr

    now_sql = sql_julian_timestamp_now_expr(database)
    database.execute(
        f"""
        UPDATE files SET
            lines = ?, has_docstring = ?, updated_at = {now_sql}
        WHERE id = ?
        """,
        (lines, has_docstring, file_id),
        transaction_id=transaction_id,
    )
    return file_id


def handle_rollback(
    database: Any,
    file_id: Optional[int],
    file_data_backup: Optional[Dict[str, Any]],
    backup_uuid: Optional[str],
    backup_manager: Optional[BackupManager],
    root_path: Path,
    target_path: Path,
) -> None:
    """
    Handle rollback: restore file data and file from backup.

    Args:
        database: Database instance
        file_id: File ID
        file_data_backup: Backup of file data or None
        backup_uuid: Backup UUID or None
        backup_manager: BackupManager instance or None
        root_path: Project root path
        target_path: Target file path
    """
    if file_data_backup and file_id:
        transaction_id = None
        try:
            transaction_id = database.begin_transaction()
            restore_file_data(database, file_id, file_data_backup)
            database.commit_transaction(transaction_id)
            logger.info("File data restored from backup for file_id=%s", file_id)
        except Exception as restore_error:
            logger.error(
                "Failed to restore file data: %s",
                restore_error,
                exc_info=True,
            )
            if transaction_id:
                try:
                    database.rollback_transaction(transaction_id)
                except Exception:
                    pass

    if backup_uuid and backup_manager and target_path.exists():
        try:
            rel_path = str(target_path.relative_to(root_path))
        except ValueError:
            rel_path = str(target_path)
        restore_success, restore_message = backup_manager.restore_file(
            rel_path, backup_uuid
        )
        if restore_success:
            logger.info("File restored from backup: %s", restore_message)
        else:
            logger.error("Failed to restore file from backup: %s", restore_message)


def apply_changes(
    database: Any,
    transaction_id: str,
    project_id: str,
    root_path: Path,
    target_path: Path,
    source_code: str,
    file_id: Optional[int],
    file_data_backup: Optional[Dict[str, Any]],
    backup_uuid: Optional[str],
    backup_manager: Optional[BackupManager],
    temp_file: Path,
    _commit_message: Optional[str],
    *,
    skip_file_edit_lock: bool = False,
) -> SuccessResult | ErrorResult:
    """
    Apply changes to file and database within transaction.

    Args:
        database: Database instance
        transaction_id: Transaction ID from begin_transaction()
        project_id: Project ID
        root_path: Project root path
        target_path: Target file path
        source_code: Source code to write
        file_id: Existing file ID or None
        file_data_backup: Backup of file data or None
        backup_uuid: Backup UUID or None
        backup_manager: BackupManager instance or None
        temp_file: Temporary file path
        _commit_message: Reserved for API compatibility; git is handled in compose_cst_ops_flow.
        skip_file_edit_lock: When True, caller holds ``files.editing_pid`` for this file.

    Returns:
        SuccessResult or ErrorResult
    """
    if database is None:
        raise RuntimeError("apply_changes requires a database connection")

    from ..core.database.file_edit_lock import release_file_edit_lock
    from ..core.database_client.file_data_batch import update_file_data_atomic_batch
    from ..core.database_client.objects.base import BaseObject

    t_apply = time.perf_counter()
    t_prev = t_apply
    logger.debug(
        "[CHAIN] run_ops_mode _apply_changes entry transaction_id=%s",
        (
            (transaction_id[:8] + "...")
            if transaction_id and len(transaction_id) > 8
            else transaction_id
        ),
    )
    try:
        if file_id:
            delete_file_data(database, file_id, transaction_id)
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] _apply_changes delete_file_data elapsed=%.3fs",
            _t - t_prev,
        )
        t_prev = _t

        file_id = update_file_record(
            database,
            project_id,
            root_path,
            target_path,
            source_code,
            file_id,
            transaction_id=transaction_id,
        )
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] _apply_changes update_file_record elapsed=%.3fs",
            _t - t_prev,
        )
        t_prev = _t

        file_mtime = (
            BaseObject._to_timestamp(datetime.fromtimestamp(temp_file.stat().st_mtime))
            or 0.0
        )
        update_result = update_file_data_atomic_batch(
            database=database,
            file_id=file_id,
            project_id=project_id,
            source_code=source_code,
            file_path=str(target_path),
            file_mtime=file_mtime,
            transaction_id=transaction_id,
            skip_file_edit_lock=skip_file_edit_lock,
        )
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] _apply_changes update_file_data_atomic elapsed=%.3fs",
            _t - t_prev,
        )
        t_prev = _t

        if not update_result.get("success"):
            raise RuntimeError(
                f"Failed to update file data: {update_result.get('error')}"
            )

        os.replace(str(temp_file), str(target_path))
        _t = time.perf_counter()
        logger.info("[PROFILE] _apply_changes os_replace elapsed=%.3fs", _t - t_prev)
        t_prev = _t

        if skip_file_edit_lock and file_id:
            try:
                release_file_edit_lock(database, file_id, transaction_id=transaction_id)
            except Exception as exc:
                logger.warning(
                    "release_file_edit_lock before commit failed file_id=%s: %s",
                    file_id,
                    exc,
                    exc_info=True,
                )
                raise

        logger.debug("[CHAIN] run_ops_mode calling database.commit_transaction")
        database.commit_transaction(transaction_id)
        _t = time.perf_counter()
        logger.info(
            "[PROFILE] _apply_changes commit_transaction elapsed=%.3fs",
            _t - t_prev,
        )
        t_prev = _t

        _t = time.perf_counter()
        logger.info(
            "[PROFILE] _apply_changes post_commit_transaction elapsed=%.3fs (total_apply=%.3fs)",
            _t - t_prev,
            _t - t_apply,
        )
        data: Dict[str, Any] = {
            "success": True,
            "file_written": True,
            "preview_only": False,
            "file_path": str(target_path),
            "file_id": file_id,
            "backup_uuid": backup_uuid,
            "update_result": update_result,
        }
        if target_path.exists():
            data["file_size_bytes"] = target_path.stat().st_size
            data["file_lines"] = len(
                target_path.read_text(encoding="utf-8").splitlines()
            )
        return SuccessResult(data=data)

    except Exception as error:
        logger.warning(
            "[CHAIN] run_ops_mode _apply_changes failed: %s; attempting rollback",
            type(error).__name__,
        )
        try:
            database.rollback_transaction(transaction_id)
        except Exception as rollback_error:
            logger.error(
                "[CHAIN] run_ops_mode rollback_transaction failed: %s",
                rollback_error,
            )

        handle_rollback(
            database,
            file_id,
            file_data_backup,
            backup_uuid,
            backup_manager,
            root_path,
            target_path,
        )

        raise error
