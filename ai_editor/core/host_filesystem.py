"""Host filesystem error normalization and logging.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import errno
import logging
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from ai_editor.core.exceptions import AIEditorError

HOST_FILE_OPERATION_ERROR = "HOST_FILE_OPERATION_ERROR"

_T = TypeVar("_T")


class HostFileOperationError(AIEditorError):
    """Raised when a host filesystem operation fails with normalized context."""

    def __init__(
        self,
        *,
        file_name: str,
        caller_file: str,
        method_name: str,
        reason: str,
        cause: BaseException,
        details: dict[str, Any],
    ) -> None:
        message = (
            "Host filesystem operation failed: "
            f"{method_name} on {file_name!r} in {caller_file} "
            f"({reason}): {cause}"
        )
        super().__init__(
            message,
            code=HOST_FILE_OPERATION_ERROR,
            details=details,
        )
        self.file_name = file_name
        self.caller_file = caller_file
        self.method_name = method_name
        self.reason = reason
        self.cause = cause


def classify_host_file_error(exc: BaseException) -> str:
    """Return a stable reason string for a host filesystem exception."""
    err_no = getattr(exc, "errno", None)
    if isinstance(exc, PermissionError) or err_no in (errno.EACCES, errno.EPERM):
        return "permission_denied"
    if isinstance(exc, FileNotFoundError) or err_no == errno.ENOENT:
        return "not_found"
    if isinstance(exc, IsADirectoryError) or err_no == errno.EISDIR:
        return "is_directory"
    if isinstance(exc, NotADirectoryError) or err_no == errno.ENOTDIR:
        return "not_a_directory"
    if err_no == errno.ENOSPC:
        return "no_space_left"
    if err_no == errno.EROFS:
        return "read_only_filesystem"
    if err_no == errno.EEXIST:
        return "already_exists"
    if err_no == errno.EXDEV:
        return "cross_device_link"
    if isinstance(exc, OSError):
        return "os_error"
    return "unexpected_error"


def _path_probe(file_name: str) -> dict[str, Any]:
    path = Path(file_name)
    data: dict[str, Any] = {"path": file_name}
    try:
        resolved = path.resolve(strict=False)
        data["resolved_path"] = str(resolved)
    except OSError as exc:
        data["resolve_error"] = str(exc)
    try:
        st = path.lstat()
    except OSError as exc:
        data["stat_error"] = str(exc)
        return data
    data.update(
        {
            "exists": True,
            "is_file": stat.S_ISREG(st.st_mode),
            "is_dir": stat.S_ISDIR(st.st_mode),
            "mode": oct(stat.S_IMODE(st.st_mode)),
            "owner_uid": st.st_uid,
            "owner_gid": st.st_gid,
            "size": st.st_size,
        }
    )
    return data


def host_file_error_details(
    *,
    file_name: str,
    caller_file: str,
    method_name: str,
    exc: BaseException,
) -> dict[str, Any]:
    """Build structured details for logs and API errors."""
    return {
        "file_name": file_name,
        "caller_file": caller_file,
        "method_name": method_name,
        "reason": classify_host_file_error(exc),
        "exception_type": type(exc).__name__,
        "exception": str(exc),
        "errno": getattr(exc, "errno", None),
        "process_uid": os.getuid() if hasattr(os, "getuid") else None,
        "process_gid": os.getgid() if hasattr(os, "getgid") else None,
        "path_probe": _path_probe(file_name),
    }


def handle_host_file_error(
    *,
    file_name: str,
    caller_file: str,
    method_name: str,
    exc: BaseException,
    logger: logging.Logger | None = None,
) -> HostFileOperationError:
    """Log and return a normalized host filesystem exception."""
    details = host_file_error_details(
        file_name=file_name,
        caller_file=caller_file,
        method_name=method_name,
        exc=exc,
    )
    reason = str(details["reason"])
    log = logger or logging.getLogger(caller_file)
    log.error(
        "host filesystem operation failed",
        extra={"host_file_error": details},
        exc_info=True,
    )
    return HostFileOperationError(
        file_name=file_name,
        caller_file=caller_file,
        method_name=method_name,
        reason=reason,
        cause=exc,
        details=details,
    )


def guard_host_file_operation(
    *,
    file_name: str | Path,
    caller_file: str,
    method_name: str,
    operation: Callable[[], _T],
    logger: logging.Logger | None = None,
) -> _T:
    """Run a filesystem operation and normalize host filesystem failures."""
    try:
        return operation()
    except OSError as exc:
        raise handle_host_file_error(
            file_name=str(file_name),
            caller_file=caller_file,
            method_name=method_name,
            exc=exc,
            logger=logger,
        ) from exc


@contextmanager
def host_file_operation(
    *,
    file_name: str | Path,
    caller_file: str,
    method_name: str,
    logger: logging.Logger | None = None,
) -> Iterator[None]:
    """Context manager form for multi-step host filesystem operations."""
    try:
        yield
    except OSError as exc:
        raise handle_host_file_error(
            file_name=str(file_name),
            caller_file=caller_file,
            method_name=method_name,
            exc=exc,
            logger=logger,
        ) from exc
