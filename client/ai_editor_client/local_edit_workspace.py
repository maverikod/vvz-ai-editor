"""
On-disk edit workspace: baseline file outside session dir, working copy inside.

Mirrors the server ``EditSession`` layout without CST/sidecar dependencies.
Used by :class:`EditorFileClient` for the five-step editor workflow.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ai_editor_client.exceptions import ClientValidationError


class EditorFileWorkflowError(ClientValidationError):
    """Invalid state or I/O failure in the editor file workflow."""


@dataclass
class LocalEditWorkspace:
    """Local session directory with a working copy of a baseline file."""

    workspace_id: str
    baseline_path: Path
    session_dir: Path
    working_path: Path
    is_open: bool = True

    @classmethod
    def open(
        cls,
        baseline_path: Path,
        *,
        workspace_id: Optional[str] = None,
    ) -> LocalEditWorkspace:
        """Create ``{baseline.name}-{uuid}/`` and copy baseline into it."""
        baseline = baseline_path.resolve()
        if not baseline.is_file():
            raise EditorFileWorkflowError(
                "baseline file does not exist",
                field="baseline_path",
                details={"baseline_path": str(baseline)},
            )
        wid = (workspace_id or str(uuid.uuid4())).strip()
        if not wid:
            raise EditorFileWorkflowError(
                "workspace_id is empty",
                field="workspace_id",
            )
        session_dir = baseline.parent / f"{baseline.name}-{wid}"
        if session_dir.exists():
            raise EditorFileWorkflowError(
                "session directory already exists",
                field="session_dir",
                details={"session_dir": str(session_dir)},
            )
        session_dir.mkdir(exist_ok=False)
        working_path = session_dir / baseline.name
        shutil.copy2(baseline, working_path)
        return cls(
            workspace_id=wid,
            baseline_path=baseline,
            session_dir=session_dir,
            working_path=working_path,
            is_open=True,
        )

    def sync_baseline(self) -> None:
        """Atomically overwrite the baseline file from the working copy."""
        if not self.is_open:
            raise EditorFileWorkflowError(
                "workspace is not open",
                field="workspace",
            )
        if not self.working_path.is_file():
            raise EditorFileWorkflowError(
                "working copy is missing",
                field="working_path",
                details={"working_path": str(self.working_path)},
            )
        tmp = self.baseline_path.with_suffix(self.baseline_path.suffix + ".tmp")
        try:
            shutil.copy2(self.working_path, tmp)
            tmp.replace(self.baseline_path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def close(self, *, delete_baseline: bool = True) -> None:
        """Remove session directory and optionally the baseline file."""
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)
        self.is_open = False
        if delete_baseline and self.baseline_path.is_file():
            self.baseline_path.unlink()
