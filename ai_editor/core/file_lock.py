"""
Advisory file lock to block other processes/threads from opening the same file.

Uses a .lock file next to the target path. On Unix uses fcntl.flock;
on Windows locking is not implemented (no-op) to avoid extra dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]


def normalize_lock_mode(lock_mode: str) -> str:
    raw = str(lock_mode or "").strip().lower()
    if raw in ("full", "exclusive", "ex", "lock_ex"):
        return "exclusive"
    if raw in ("block_write", "read_only", "shared", "sh", "lock_sh"):
        return "shared"
    if raw == "none":
        return "none"
    raise ValueError("lock_mode must be one of: none, block_write, full")


@dataclass(frozen=True)
class RuntimeLockSession:
    session_id: str
    pid: int
    role: str
    listener_url: Optional[str] = None
    hostname: Optional[str] = None


_runtime_session_lock = threading.Lock()
_runtime_session_by_pid: dict[int, str] = {}
_known_runtime_sessions: set[str] = set()


def register_runtime_session(
    _database: Any = None,
    *,
    role: str,
    listener_url: Optional[str] = None,
    session_id: Optional[str] = None,
) -> RuntimeLockSession:
    pid = os.getpid()
    sid = str(session_id or uuid.uuid4()).strip()
    with _runtime_session_lock:
        _runtime_session_by_pid[pid] = sid
        _known_runtime_sessions.add(sid)
    return RuntimeLockSession(
        session_id=sid,
        pid=pid,
        role=str(role or "unknown").strip() or "unknown",
        listener_url=listener_url,
    )


def runtime_session_exists(_database: Any = None, session_id: str = "") -> bool:
    sid = str(session_id).strip()
    with _runtime_session_lock:
        return sid in _known_runtime_sessions


def get_session_id_for_current_pid(
    _database: Any = None, *, role: str = "command"
) -> str:
    pid = os.getpid()
    with _runtime_session_lock:
        sid = _runtime_session_by_pid.get(pid)
        if sid:
            return sid
    return register_runtime_session(None, role=role).session_id


def ensure_client_lock_session(_database: Any, client_session_id: str) -> str:
    sid = str(client_session_id).strip()
    if not sid:
        raise ValueError("client session_id is required")
    with _runtime_session_lock:
        _known_runtime_sessions.add(sid)
    return sid


def acquire_file_advisory_lease(
    _database: Any,
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    lock_mode: str,
) -> Dict[str, Any]:
    mode = normalize_lock_mode(lock_mode)
    if mode == "none":
        return {"success": True, "acquired": False, "lock_mode": "none"}
    return {
        "success": True,
        "acquired": True,
        "session_id": str(session_id).strip(),
        "project_id": str(project_id).strip(),
        "file_path": str(file_path).strip().replace("\\", "/"),
        "lock_mode": lock_mode,
        "refcount": 1,
    }


def release_file_advisory_lease(
    _database: Any,
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    lock_mode: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    return {
        "success": True,
        "released": True,
        "session_id": str(session_id).strip(),
        "project_id": str(project_id).strip(),
        "file_path": str(file_path).strip().replace("\\", "/"),
    }


def get_file_advisory_lock_status(
    _database: Any,
    *,
    project_id: str,
    file_path: str,
) -> Dict[str, Any]:
    return {
        "success": True,
        "project_id": str(project_id).strip(),
        "file_path": str(file_path).strip().replace("\\", "/"),
        "lock_status": "free",
        "leases": {
            "exclusive_total_refcount": 0,
            "shared_total_refcount": 0,
            "exclusive_sessions": [],
            "shared_sessions": [],
        },
    }


def _database_supports_lock_leases(database: Any) -> bool:
    """Legacy DB advisory leases removed; sidecar flock only."""
    return False


class FileLockTimeoutError(TimeoutError):
    """Raised when an advisory sidecar lock cannot be acquired before timeout."""


class FileLockHandle:
    """Held sidecar flock plus optional DB advisory lease."""

    def __init__(
        self,
        *,
        path: Path,
        lock_file: Any,
        lock_path: Path,
        mode: str,
        database: Any = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> None:
        self.path = path
        self.lock_file = lock_file
        self.lock_path = lock_path
        self.mode = normalize_lock_mode(mode)
        self.database = database
        self.session_id = session_id
        self.project_id = project_id
        self.file_path = file_path
        self.released = False

    def release(self, *, force_lease: bool = False) -> None:
        """Release the OS flock and best-effort DB lease."""
        if self.released:
            return
        self.released = True
        if (
            self.database is not None
            and self.session_id
            and self.project_id
            and self.file_path
            and self.mode != "none"
        ):
            try:
                release_file_advisory_lease(
                    self.database,
                    session_id=self.session_id,
                    project_id=self.project_id,
                    file_path=self.file_path,
                    lock_mode=self.mode,
                    force=force_lease,
                )
            except Exception as e:
                logger.warning("Lease release failed for %s: %s", self.path, e)
        if self.lock_file is not None and fcntl is not None:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            except OSError as e:
                logger.warning("Unlock failed for %s: %s", self.lock_path, e)
        if self.lock_file is not None:
            self.lock_file.close()
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError as e:
            logger.debug("Remove lock file %s: %s", self.lock_path, e)

    def __enter__(self) -> "FileLockHandle":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()


class PersistentFileLock:
    """Backward-compatible process-held advisory lock for a target file."""

    def __init__(self, path: Path, *, shared: bool = False) -> None:
        self.path = Path(path)
        self.shared = bool(shared)
        self._handle: Optional[FileLockHandle] = None

    @property
    def is_held(self) -> bool:
        return self._handle is not None and not self._handle.released

    def acquire(self) -> "PersistentFileLock":
        if self.is_held:
            return self
        self._handle = acquire_file_lock(
            self.path,
            mode="block_write" if self.shared else "full",
        )
        return self

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is not None:
            handle.release()

    def __enter__(self) -> "PersistentFileLock":
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()


_persistent_guard = threading.Lock()
_persistent_locks: Dict[Tuple[str, str, str], FileLockHandle] = {}


def _fcntl_flag_for_mode(mode: str) -> int:
    normalized = normalize_lock_mode(mode)
    if normalized == "shared":
        return fcntl.LOCK_SH if fcntl is not None else 0
    return fcntl.LOCK_EX if fcntl is not None else 0


def acquire_file_lock(
    path: Path,
    *,
    mode: str = "full",
    shared: Optional[bool] = None,
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    database: Any = None,
    project_id: Optional[str] = None,
    file_path: Optional[str] = None,
    session_id: Optional[str] = None,
    register_role: str = "command",
) -> FileLockHandle:
    """Acquire a sidecar flock and optional DB advisory lease."""
    target = Path(path)
    normalized_mode = "shared" if shared else normalize_lock_mode(mode)
    lock_path = Path(str(target) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w", encoding="utf-8")
    try:
        if fcntl is not None:
            flag = _fcntl_flag_for_mode(normalized_mode)
            if timeout is None:
                fcntl.flock(lock_file.fileno(), flag)
            else:
                deadline = time.monotonic() + max(0.0, float(timeout))
                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), flag | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as e:
                        if time.monotonic() >= deadline:
                            raise FileLockTimeoutError(
                                f"Timed out acquiring {normalized_mode} lock for {target}"
                            ) from e
                        time.sleep(max(0.001, float(poll_interval)))
        sid = session_id
        if (
            _database_supports_lock_leases(database)
            and project_id
            and file_path
            and normalized_mode != "none"
        ):
            sid = sid or get_session_id_for_current_pid(database, role=register_role)
            acquire_file_advisory_lease(
                database,
                session_id=sid,
                project_id=project_id,
                file_path=file_path,
                lock_mode=normalized_mode,
            )
        return FileLockHandle(
            path=target,
            lock_file=lock_file,
            lock_path=lock_path,
            mode=normalized_mode,
            database=database,
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
    except Exception:
        try:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock_file.close()
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass
        raise


def acquire_persistent_file_lock(
    path: Path,
    *,
    mode: str,
    database: Any,
    project_id: str,
    file_path: str,
    session_id: Optional[str] = None,
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    register_role: str = "command",
) -> FileLockHandle:
    """Acquire and retain a lock outside a context manager in this process."""
    sid = session_id or get_session_id_for_current_pid(database, role=register_role)
    key = (sid, str(project_id), str(file_path).replace("\\", "/"))
    with _persistent_guard:
        existing = _persistent_locks.get(key)
        if existing and not existing.released:
            acquire_file_advisory_lease(
                database,
                session_id=sid,
                project_id=project_id,
                file_path=file_path,
                lock_mode=mode,
            )
            return existing
        handle = acquire_file_lock(
            path,
            mode=mode,
            timeout=timeout,
            poll_interval=poll_interval,
            database=database,
            project_id=project_id,
            file_path=file_path,
            session_id=sid,
            register_role=register_role,
        )
        _persistent_locks[key] = handle
        return handle


def release_persistent_file_lock(
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    database: Any = None,
    lock_mode: Optional[str] = None,
    force: bool = True,
) -> bool:
    """Release a retained in-process lock and/or its DB lease."""
    key = (str(session_id), str(project_id), str(file_path).replace("\\", "/"))
    released = False
    with _persistent_guard:
        handle = _persistent_locks.pop(key, None)
    if handle is not None:
        handle.release(force_lease=force)
        released = True
    elif database is not None:
        release_file_advisory_lease(
            database,
            session_id=session_id,
            project_id=project_id,
            file_path=file_path,
            lock_mode=lock_mode,
            force=force,
        )
    return released


@contextmanager
def file_lock(
    path: Path,
    *,
    shared: bool = False,
    mode: str = "full",
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    database: Any = None,
    project_id: Optional[str] = None,
    file_path: Optional[str] = None,
    session_id: Optional[str] = None,
    register_role: str = "command",
) -> Generator[None, None, None]:
    """
    Hold an exclusive advisory lock for the given file path.

    Creates path.lock (in the same directory) and locks it. Other processes
    using the same convention will block until the lock is released.
    path can be the actual file or its .tmp (lock is taken on path.lock).

    Args:
        path: File path to lock (e.g. /dir/file.py or /dir/file.py.tmp).

    Yields:
        None; lock is held for the duration of the context.
    """
    handle: Optional[FileLockHandle] = None
    try:
        handle = acquire_file_lock(
            Path(path),
            shared=shared,
            mode=mode,
            timeout=timeout,
            poll_interval=poll_interval,
            database=database,
            project_id=project_id,
            file_path=file_path,
            session_id=session_id,
            register_role=register_role,
        )
        yield
    finally:
        if handle is not None:
            handle.release()
