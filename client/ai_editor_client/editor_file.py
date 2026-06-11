"""
Five-step editor workflow over CA transfer + local session directory.

1. **checkout** — download file to baseline path and lock in CA DB.
2. **open_workspace** — create local ``{name}-{uuid}/`` session dir; edit inside it.
3. *(edit)* — application mutates :attr:`EditorFileHandle.working_path`.
4. **save_to_server** — upload working bytes; on success sync baseline outside session.
5. **close** — unlock on CA; on success delete session dir and baseline.

Distinct from ``UniversalFileClient`` (server-side in-memory agent sessions).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ai_editor_client.exceptions import ClientValidationError
from ai_editor_client.file_session import FileSessionClient
from ai_editor_client.local_edit_workspace import (
    EditorFileWorkflowError,
    LocalEditWorkspace,
)


def _require_non_empty(value: str, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ClientValidationError(f"{field_name} is required", field=field_name)
    return text


@dataclass
class EditorFileHandle:
    """State for one checked-out project file in the editor."""

    ca_session_id: str
    project_id: str
    file_id: str
    file_path: str
    baseline_path: Path
    workspace: Optional[LocalEditWorkspace] = None
    is_closed: bool = field(default=False, repr=False)

    @property
    def is_open(self) -> bool:
        return (
            not self.is_closed
            and self.workspace is not None
            and self.workspace.is_open
        )

    @property
    def working_path(self) -> Path:
        if not self.is_open or self.workspace is None:
            raise EditorFileWorkflowError(
                "workspace is not open; call open_workspace first",
                field="workspace",
            )
        return self.workspace.working_path

    def _assert_active(self) -> None:
        if self.is_closed:
            raise EditorFileWorkflowError(
                "handle is closed",
                field="handle",
            )


class EditorFileClient:
    """Orchestrates download → local session → upload → unlock for one file."""

    __slots__ = ("_fs",)

    def __init__(self, file_sessions: FileSessionClient) -> None:
        self._fs = file_sessions

    async def checkout(
        self,
        ca_session_id: str,
        baseline_path: Union[str, Path],
        file_id: str,
        *,
        project_id: Optional[str] = None,
        lock: bool = True,
        compression: str = "identity",
        include_backup_history: bool = True,
    ) -> EditorFileHandle:
        """Step 1: download to *baseline_path* (outside session) and lock on CA."""
        sid = _require_non_empty(ca_session_id, field_name="ca_session_id")
        fid = _require_non_empty(file_id, field_name="file_id")
        baseline = Path(baseline_path).resolve()
        baseline.parent.mkdir(parents=True, exist_ok=True)

        begin, _receipt = await self._fs.download(
            sid,
            baseline,
            fid,
            compression=compression,
            lock=lock,
            include_backup_history=include_backup_history,
            project_id=project_id,
        )
        if not baseline.is_file():
            raise EditorFileWorkflowError(
                "download did not create baseline file",
                field="baseline_path",
                details={"baseline_path": str(baseline), "begin": begin},
            )

        effective_pid = str(begin.get("project_id") or project_id or "").strip()
        if not effective_pid:
            raise EditorFileWorkflowError(
                "project_id missing from download response",
                field="project_id",
                details={"begin": begin},
            )
        rel_path = str(begin.get("file_path") or "").strip().replace("\\", "/")
        if not rel_path:
            rel_path = baseline.name

        return EditorFileHandle(
            ca_session_id=sid,
            project_id=effective_pid,
            file_id=str(begin.get("file_id") or fid).strip(),
            file_path=rel_path,
            baseline_path=baseline,
        )

    def open_workspace(self, handle: EditorFileHandle) -> Path:
        """Step 2: create local session directory; return path to edit inside."""
        handle._assert_active()
        if handle.workspace is not None:
            if handle.workspace.is_open:
                return handle.workspace.working_path
            raise EditorFileWorkflowError(
                "workspace was closed but handle is still active",
                field="workspace",
            )
        handle.workspace = LocalEditWorkspace.open(handle.baseline_path)
        return handle.workspace.working_path

    async def save_to_server(
        self,
        handle: EditorFileHandle,
        *,
        backup: bool = True,
        dry_run: bool = False,
        diff: bool = False,
        diff_context_lines: Optional[int] = None,
        commit_message: Optional[str] = None,
        validate_syntax_only: bool = False,
        tree_id: Optional[str] = None,
        lock_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Step 4: upload working copy; on success overwrite baseline (no unlock)."""
        handle._assert_active()
        if not handle.is_open or handle.workspace is None:
            raise EditorFileWorkflowError(
                "workspace is not open",
                field="workspace",
            )
        payload = handle.workspace.working_path.read_bytes()
        saved = await self._fs.upload(
            handle.ca_session_id,
            payload,
            handle.file_id,
            project_id=handle.project_id,
            filename=Path(handle.file_path).name,
            unlock=False,
            backup=backup,
            dry_run=dry_run,
            diff=diff,
            diff_context_lines=diff_context_lines,
            commit_message=commit_message,
            validate_syntax_only=validate_syntax_only,
            tree_id=tree_id,
            lock_mode=lock_mode,
        )
        if not dry_run:
            handle.workspace.sync_baseline()
        return saved

    async def close(self, handle: EditorFileHandle) -> Dict[str, Any]:
        """Step 5: unlock on CA; on success remove session dir and baseline."""
        handle._assert_active()
        unlock_result = await self._fs.unlock_file(
            handle.ca_session_id,
            handle.project_id,
            handle.file_id,
        )
        if handle.workspace is not None and handle.workspace.is_open:
            handle.workspace.close(delete_baseline=True)
            handle.workspace = None
        elif handle.baseline_path.is_file():
            handle.baseline_path.unlink()
        handle.is_closed = True
        return unlock_result
