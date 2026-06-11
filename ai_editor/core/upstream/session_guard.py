"""Session Guard — single validation entry for universal_file_* (C-024)."""

from __future__ import annotations

import enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .code_analysis_client import CodeAnalysisClient


class OperationKind(str, enum.Enum):
    OPEN = "open"
    EDIT = "edit"
    PREVIEW = "preview"
    WRITE = "write"
    CLOSE = "close"


class GuardDecision(str, enum.Enum):
    ALLOW = "allow"
    REJECT = "reject"
    ALLOW_TERMINATING = "allow_terminating"


class SessionGuard:
    """C-024: wraps C-014 validation and C-015 terminating policy."""

    def __init__(self, client: "CodeAnalysisClient") -> None:
        self._client = client

    def check(
        self,
        kind: OperationKind,
        ca_session_id: str,
        *,
        workspace_root: Path | None = None,
    ) -> GuardDecision:
        if not str(ca_session_id or "").strip():
            return GuardDecision.REJECT

        from .code_analysis_client import CaSessionStatus

        if kind in (OperationKind.WRITE, OperationKind.CLOSE):
            status = self._client.validate_ca_session(ca_session_id)
            if status == CaSessionStatus.NOT_FOUND:
                from ai_editor.core.editor_workspace_paths import resolve_workspace_root
                from ai_editor.core.workspace_session_cleanup import (
                    cleanup_zombie_ca_session,
                )

                root = workspace_root or resolve_workspace_root()
                cleanup_zombie_ca_session(ca_session_id, workspace_root=root)
            return GuardDecision.ALLOW_TERMINATING

        status = self._client.validate_ca_session(ca_session_id)
        if status == CaSessionStatus.VALID:
            return GuardDecision.ALLOW
        return GuardDecision.REJECT
