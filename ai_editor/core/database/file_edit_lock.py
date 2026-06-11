"""
File-level write lock via ``files.editing_pid`` column.

Prevents concurrent writes and worker indexing while a CST operation
is in progress. Uses the OS process ID as the lock owner identifier.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import errno
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

_LOCK_RETRIES = 5
_LOCK_RETRY_DELAY = 0.5


def editing_lock_holder_is_alive(holder: Any) -> bool:
    """
    Return True if ``holder`` is a PID that refers to a running process.

    ``None`` or invalid values are not alive. Uses ``os.kill(pid, 0)`` (Unix);
    ``PermissionError`` means the process exists but cannot be signalled.
    """
    if holder is None:
        return False
    try:
        pid = int(holder)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False
        return True
    return True


def _execute_with_optional_tid(
    database: Any,
    sql: str,
    params: tuple,
    *,
    transaction_id: Optional[str] = None,
) -> Any:
    """Call ``database.execute``; pass ``transaction_id`` when supported."""
    ex = getattr(database, "execute", None)
    if not callable(ex):
        raise TypeError("database must have execute()")
    if transaction_id is not None:
        try:
            return ex(sql, params, transaction_id=transaction_id)
        except TypeError:
            return ex(sql, params)
    return ex(sql, params)


def _project_root_path_str(database: Any, project_id: str) -> Optional[str]:
    from ai_editor.core.project_root_path import (
        resolve_projects_root_path_row_to_absolute_str,
    )

    gp = getattr(database, "get_project", None)
    if callable(gp):
        p = gp(project_id)
        if isinstance(p, dict):
            s = str(p.get("root_path") or "").strip()
            return s or None
        if p is not None:
            rp = getattr(p, "root_path", None)
            s = str(rp).strip() if rp else ""
            return s or None
    row = None
    if hasattr(database, "_fetchone"):
        row = database._fetchone(
            "SELECT root_path, watch_dir_id FROM projects WHERE id = ?",
            (project_id,),
        )
    if row is None:
        ex = getattr(database, "execute", None)
        if callable(ex):
            r = ex(
                "SELECT root_path, watch_dir_id FROM projects WHERE id = ?",
                (project_id,),
            )
            if isinstance(r, dict):
                rows = r.get("data") or []
                if rows and isinstance(rows[0], dict):
                    row = rows[0]
    if isinstance(row, dict) and row.get("root_path"):
        resolved = resolve_projects_root_path_row_to_absolute_str(
            root_path_stored=str(row.get("root_path") or ""),
            watch_dir_id=(
                str(row["watch_dir_id"])
                if row.get("watch_dir_id") is not None
                else None
            ),
            database=database,
        )
        return resolved or None
    return None


def _select_scalar_editing_pid(
    database: Any,
    sql: str,
    params: tuple,
    *,
    transaction_id: Optional[str] = None,
) -> Any:
    """Run a single-row SELECT editing_pid; return value or None."""
    if hasattr(database, "execute"):
        result = _execute_with_optional_tid(
            database, sql, params, transaction_id=transaction_id
        )
        if isinstance(result, dict):
            rows = result.get("data") or []
            if rows and isinstance(rows[0], dict):
                return rows[0].get("editing_pid")
        return None
    if hasattr(database, "_fetchone"):
        row = database._fetchone(sql, params)
        if isinstance(row, dict):
            return row.get("editing_pid")
    return None


def file_row_has_live_edit_lock(
    database: Any,
    *,
    project_id: str,
    path: str,
) -> bool:
    """True if the file row exists and ``editing_pid`` is a live process."""
    from code_analysis.core.file_identity import (
        FILE_ROW_PATH_MATCH_SQL,
        file_row_path_match_values,
    )
    from code_analysis.core.path_normalization import normalize_path_simple

    root_str = _project_root_path_str(database, project_id)
    abs_path = normalize_path_simple(path)
    if root_str:
        try:
            r1, r2, r3 = file_row_path_match_values(
                project_root=root_str, absolute_path=abs_path
            )
        except ValueError:
            sql = "SELECT editing_pid FROM files WHERE project_id = ? AND path = ? LIMIT 1"
            params: tuple[Any, ...] = (project_id, abs_path)
        else:
            sql = (
                "SELECT editing_pid FROM files WHERE project_id = ? AND "
                f"{FILE_ROW_PATH_MATCH_SQL} LIMIT 1"
            )
            params = (project_id, r1, r2, r3)
    else:
        sql = "SELECT editing_pid FROM files WHERE project_id = ? AND path = ? LIMIT 1"
        params = (project_id, abs_path)
    ep = _select_scalar_editing_pid(
        database,
        sql,
        params,
        transaction_id=None,
    )
    return editing_lock_holder_is_alive(ep)


def _dml_affected_rows(result: Any) -> int:
    """Extract affected row count from :meth:`CodeDatabase.execute` / client result."""
    if not isinstance(result, dict):
        return 0
    v = result.get("affected_rows")
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def try_acquire_file_edit_lock(
    database: Any,
    file_id: Any,
    *,
    transaction_id: Optional[str] = None,
) -> bool:
    """
    Attempt to set editing_pid on the given file row to the current PID.

    Succeeds when the row is unowned, re-entrant (same PID), or the stored
    ``editing_pid`` is stale (process no longer exists) — stale locks are
    cleared first.

    Args:
        database: Database driver instance with ``execute`` returning
            ``affected_rows`` for DML.
        file_id: Primary key of the file row in ``files``.
        transaction_id: When set, run statements on that open transaction so the
            same PostgreSQL backend connection holds both the row lock and the
            writer transaction (avoids deadlocks with a second pool connection).

    Returns:
        True if the lock was acquired, False if another live process holds it.
    """
    pid = os.getpid()
    holder = _select_scalar_editing_pid(
        database,
        "SELECT editing_pid FROM files WHERE id = ?",
        (file_id,),
        transaction_id=transaction_id,
    )
    if holder is not None:
        try:
            hid = int(holder)
        except (TypeError, ValueError):
            hid = None
        if hid is not None and hid != pid and not editing_lock_holder_is_alive(holder):
            _execute_with_optional_tid(
                database,
                "UPDATE files SET editing_pid = NULL WHERE id = ? AND editing_pid = ?",
                (file_id, hid),
                transaction_id=transaction_id,
            )
    sql = (
        "UPDATE files SET editing_pid = ? "
        "WHERE id = ? AND (editing_pid IS NULL OR editing_pid = ?)"
    )
    result = _execute_with_optional_tid(
        database, sql, (pid, file_id, pid), transaction_id=transaction_id
    )
    return _dml_affected_rows(result) > 0


def release_file_edit_lock(
    database: Any,
    file_id: Any,
    *,
    transaction_id: Optional[str] = None,
) -> None:
    """
    Clear editing_pid for the given file row.

    Safe to call when the lock is already NULL (no-op update).

    Args:
        database: Database instance.
        file_id: Primary key of the file row in ``files``.
    """
    pid = os.getpid()
    sql = "UPDATE files SET editing_pid = NULL WHERE id = ? AND editing_pid = ?"
    _execute_with_optional_tid(
        database, sql, (file_id, pid), transaction_id=transaction_id
    )


def acquire_file_edit_lock_with_retry(
    database: Any,
    file_id: Any,
    retries: int = _LOCK_RETRIES,
    retry_delay: float = _LOCK_RETRY_DELAY,
    *,
    transaction_id: Optional[str] = None,
) -> bool:
    """
    Try to acquire the file edit lock, retrying on contention.

    Args:
        database: Database instance.
        file_id: Primary key of the file row in ``files``.
        retries: Maximum number of acquisition attempts.
        retry_delay: Seconds to wait between retries.
        transaction_id: Optional open transaction (same connection as the write path).

    Returns:
        True if the lock was acquired within the retry budget, False otherwise.
    """
    for attempt in range(retries):
        if try_acquire_file_edit_lock(database, file_id, transaction_id=transaction_id):
            return True
        logger.debug(
            "File edit lock held by another process for file_id=%s, "
            "retry %d/%d in %.1fs",
            file_id,
            attempt + 1,
            retries,
            retry_delay,
        )
        time.sleep(retry_delay)
    return False


@contextmanager
def file_edit_lock(
    database: Any,
    file_id: Any,
    *,
    transaction_id: Optional[str] = None,
) -> Generator[None, None, None]:
    """
    Context manager: acquire file edit lock on entry, release on exit.

    Raises:
        RuntimeError: If the lock cannot be acquired within the retry budget.

    Args:
        database: Database instance.
        file_id: Primary key of the file row in ``files``.
        transaction_id: Optional transaction scoped to the same connection as writes.
    """
    if not acquire_file_edit_lock_with_retry(
        database, file_id, transaction_id=transaction_id
    ):
        raise RuntimeError(
            f"File edit lock is held by another process for file_id={file_id}. "
            "Another write operation is in progress. Try again later."
        )
    try:
        yield
    finally:
        try:
            release_file_edit_lock(database, file_id, transaction_id=transaction_id)
        except Exception as exc:
            logger.warning(
                "Failed to release file edit lock for file_id=%s: %s",
                file_id,
                exc,
            )
