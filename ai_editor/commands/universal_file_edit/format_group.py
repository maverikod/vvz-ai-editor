"""
FormatGroup resolution and DraftFile/WriteLockfile path helpers.
Workspace edit uses resolve_format_group_for_edit_source with edit_source_path inside Edit Subdirectory.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import os

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ai_editor.core.file_handlers.registry import RegistryError, resolve_handler

FORMAT_SIDECAR = "sidecar"
FORMAT_TREE_TEMP = "tree-temp"
FORMAT_TEXT = "text"

# Third lockfile line: universal_file_write preview completed (sidecar two-phase).
LOCKFILE_WRITE_PREVIEW_READY = "write_preview"

_HANDLER_TO_FORMAT = {
    "python": FORMAT_SIDECAR,
    "json": FORMAT_TREE_TEMP,
    "yaml": FORMAT_TREE_TEMP,
    "text": FORMAT_TEXT,
}

_SIX_EDIT_OPERATIONS = [
    "insert",
    "delete",
    "replace",
    "move",
    "edit_attributes",
    "edit_content",
]

_FORMAT_AVAILABLE_OPERATIONS = {
    FORMAT_SIDECAR: list(_SIX_EDIT_OPERATIONS),
    FORMAT_TREE_TEMP: list(_SIX_EDIT_OPERATIONS),
    FORMAT_TEXT: list(_SIX_EDIT_OPERATIONS),
}

# Default handler when building a descriptor from an explicit format_group hint
# (used only for files with unknown/absent extensions).
_FORMAT_TO_DEFAULT_HANDLER: dict = {
    FORMAT_SIDECAR: "python",
    FORMAT_TREE_TEMP: "json",
    FORMAT_TEXT: "text",
}


@dataclass
class FormatDescriptor:
    """Resolved format group descriptor for one file.

    Attributes:
        format_group: One of sidecar, tree-temp, or text.
        handler_id: Handler id from the file handler registry.
        draft_path: Absolute path to the draft file.
        lockfile_path: Absolute path to the write lockfile.
        available_operations: List of operation type strings valid for this group.
    """

    format_group: str
    handler_id: str
    draft_path: Path
    lockfile_path: Path
    available_operations: List[str] = field(default_factory=list)


def resolve_format_group(abs_path: Path) -> FormatDescriptor:
    """Resolve the FormatGroup and return a FormatDescriptor for abs_path.

    Args:
        abs_path: Absolute path to the file being opened for editing.

    Returns:
        FormatDescriptor with resolved group, draft path, lockfile path,
        and available operations.

    Raises:
        ValueError: with code UNKNOWN_FORMAT when the file extension is not
            supported by any handler.
    """
    try:
        handler_id = resolve_handler(str(abs_path), "read")
    except RegistryError as exc:
        raise ValueError("UNKNOWN_FORMAT") from exc
    format_group = _HANDLER_TO_FORMAT[handler_id]
    draft_path = draft_path_for(abs_path, format_group)
    lockfile_path = lockfile_path_for(abs_path)
    available_ops = list(_FORMAT_AVAILABLE_OPERATIONS[format_group])
    return FormatDescriptor(
        format_group=format_group,
        handler_id=handler_id,
        draft_path=draft_path,
        lockfile_path=lockfile_path,
        available_operations=available_ops,
    )


def draft_path_for(abs_path: Path, format_group: str) -> Path:
    """Return the draft file path for abs_path given its format group.

    Args:
        abs_path: Absolute path to the original file.
        format_group: One of sidecar, tree-temp, or text.

    Returns:
        Absolute path to the draft file.
    """
    if format_group == FORMAT_SIDECAR:
        return abs_path.with_suffix(abs_path.suffix + ".cst_sidecar")
    return abs_path.with_suffix(abs_path.suffix + ".draft")


def lockfile_path_for(abs_path: Path) -> Path:
    """Return the write lockfile path for abs_path.

    Args:
        abs_path: Absolute path to the original file.

    Returns:
        Absolute path to the lockfile (<file>.write).
    """
    return abs_path.with_suffix(abs_path.suffix + ".write")


def draft_path_for_edit_source(edit_source_path: Path) -> Path:
    """Return draft path as sibling of edit_source_path inside Edit Subdirectory."""
    return edit_source_path.with_suffix(edit_source_path.suffix + ".draft")


def lockfile_path_for_edit_source(edit_source_path: Path) -> Path:
    """Return in-session write lockfile path as sibling of edit_source_path inside Edit Subdirectory."""
    return edit_source_path.with_suffix(edit_source_path.suffix + ".write")


def resolve_format_group_for_edit_source(edit_source_path: Path) -> FormatDescriptor:
    """Resolve format group where draft_path and lockfile_path are siblings of edit_source_path
    inside Edit Subdirectory (C-008), not beside canonical project file on CA host.
    """
    try:
        handler_id = resolve_handler(str(edit_source_path), "read")
    except RegistryError as exc:
        raise ValueError("UNKNOWN_FORMAT") from exc
    format_group = _HANDLER_TO_FORMAT[handler_id]
    draft_path = draft_path_for_edit_source(edit_source_path)
    lockfile_path = lockfile_path_for_edit_source(edit_source_path)
    available_ops = list(_FORMAT_AVAILABLE_OPERATIONS[format_group])
    return FormatDescriptor(
        format_group=format_group,
        handler_id=handler_id,
        draft_path=draft_path,
        lockfile_path=lockfile_path,
        available_operations=available_ops,
    )


def format_descriptor_from_hint(hint: str, edit_source_path: Path) -> FormatDescriptor:
    """Build a FormatDescriptor from an explicit format_group hint.

    Used only when the file extension is unknown or absent and the caller
    passes an explicit format_group to universal_file_open.

    Raises:
        ValueError: with code UNKNOWN_FORMAT_HINT when hint is not a valid group.
    """
    handler_id = _FORMAT_TO_DEFAULT_HANDLER.get(hint)
    if handler_id is None:
        raise ValueError(f"UNKNOWN_FORMAT_HINT: {hint!r}")
    draft_path = draft_path_for_edit_source(edit_source_path)
    lockfile_path = lockfile_path_for_edit_source(edit_source_path)
    available_ops = list(_FORMAT_AVAILABLE_OPERATIONS[hint])
    return FormatDescriptor(
        format_group=hint,
        handler_id=handler_id,
        draft_path=draft_path,
        lockfile_path=lockfile_path,
        available_operations=available_ops,
    )


def read_lockfile_pid(abs_path: Path) -> Optional[Tuple[int, str]]:
    """Read PID and session_id from the write lockfile.

    Returns:
        ``(pid, session_id)`` when the lockfile exists and is valid.
        ``None`` when the lockfile is absent, unreadable, or malformed.
    """
    lf = lockfile_path_for(abs_path)
    try:
        parts = lf.read_text().strip().splitlines()
        if len(parts) < 2:
            return None
        return int(parts[0]), parts[1].strip()
    except (OSError, ValueError):
        return None


def lockfile_write_preview_ready(abs_path: Path) -> bool:
    """Return True when the lockfile marks a completed universal_file_write preview.

    Open writes only PID and session_id (session lock). The first sidecar write
    preview adds a third line ``write_preview``; the second write call commits.
    """
    lf = lockfile_path_for(abs_path)
    try:
        parts = lf.read_text().strip().splitlines()
        return len(parts) >= 3 and parts[2].strip() == LOCKFILE_WRITE_PREVIEW_READY
    except OSError:
        return False


def write_lockfile_pid(
    abs_path: Path,
    pid: int,
    session_id: str,
    *,
    write_preview_ready: bool = False,
) -> None:
    """Write PID and session_id to the write lockfile atomically.

    Format: first line is the integer PID, second line is the session UUID.
    Optional third line ``write_preview`` after the first sidecar write preview.
    """
    lf = lockfile_path_for(abs_path)
    tmp = lf.with_suffix(".write.tmp")
    body = f"{pid}\n{session_id}"
    if write_preview_ready:
        body = f"{body}\n{LOCKFILE_WRITE_PREVIEW_READY}"
    tmp.write_text(body)
    tmp.rename(lf)


def delete_lockfile(abs_path: Path) -> None:
    """Delete the write lockfile if it exists; silent if absent.

    Args:
        abs_path: Absolute path to the original file.
    """
    lockfile_path_for(abs_path).unlink(missing_ok=True)


def check_lock(abs_path: Path, caller_session_id: str) -> Optional[str]:
    """Return None if the file is free, or the locking session_id if locked.

    Free when any of:
      - lockfile absent
      - lockfile has no session_id (legacy / corrupt)
      - owning process is dead (os.kill raises OSError with ESRCH)
      - session_id in lockfile equals caller_session_id
    Locked when: lockfile present, process alive, session_id != caller.
    """
    lock = read_lockfile_pid(abs_path)
    if lock is None:
        return None
    pid, lock_session_id = lock
    if not lock_session_id:
        return None
    if lock_session_id == caller_session_id:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        # Process does not exist (ESRCH) or we lack permission (EPERM).
        # EPERM means the process exists but belongs to another user;
        # treat conservatively as alive only when errno is EPERM.
        import errno as _errno
        import sys

        exc = sys.exc_info()[1]
        if getattr(exc, "errno", None) == _errno.ESRCH:
            return None  # process dead — lock is stale
        # EPERM or anything else: process alive, file locked
        return lock_session_id
    return lock_session_id
