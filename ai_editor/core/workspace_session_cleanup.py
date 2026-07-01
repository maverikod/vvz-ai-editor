"""Zombie CA session workspace cleanup (C-025).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ai_editor.core.host_filesystem import host_file_operation

logger = logging.getLogger(__name__)


def _purge_bundle(ca_session_id: str) -> None:
    """Drop all command-layer facades for a CA session id."""
    from ai_editor.commands.universal_file_edit.session import (
        get_session,
        release_session,
    )

    while True:
        try:
            session = get_session(ca_session_id)
        except ValueError:
            break
        release_session(ca_session_id, session.file_path)


def cleanup_zombie_ca_session(
    ca_session_id: str,
    *,
    workspace_root: Path,
) -> bool:
    """Remove ``{workspace_root}/{ca_session_id}/`` and in-memory bundle (C-025)."""
    sid = str(ca_session_id or "").strip()
    if not sid:
        return False
    root = workspace_root.resolve()
    session_dir = (root / sid).resolve()
    try:
        session_dir.relative_to(root)
    except ValueError:
        logger.warning("cleanup path outside workspace: %s", session_dir)
        return False
    _purge_bundle(sid)
    if session_dir.is_dir():
        with host_file_operation(
            file_name=session_dir,
            caller_file=__file__,
            method_name="cleanup_zombie_ca_session:rmtree",
            logger=logger,
        ):
            shutil.rmtree(session_dir)
    return True
