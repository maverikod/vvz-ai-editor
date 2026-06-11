"""
Sync command-layer EditSession state after core history navigation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    parse_source_bytes_to_roots,
)
from ai_editor.core.cst_tree.tree_builder import load_file_to_tree
from ai_editor.core.edit_session import SessionTreeValidity


def sync_command_session_after_history(session: EditSession) -> None:
    """Refresh draft paths and format-specific caches after undo/redo."""
    session.draft_path = session.core.session_source_path
    session.dirty = True

    if session.format_group == FORMAT_TREE_TEMP and session.tree_temp_roots is not None:
        raw = session.core.session_source_path.read_bytes()
        session.tree_temp_roots = parse_source_bytes_to_roots(
            session.handler_id,
            raw,
        )

    if session.format_group == FORMAT_SIDECAR:
        if session.core.tree_validity == SessionTreeValidity.VALID:
            try:
                from ai_editor.core.cst_tree.tree_sidecar import write_sidecar_atomic

                tree = load_file_to_tree(str(session.core.session_source_path))
                session.tree_id = str(tree.tree_id)
                write_sidecar_atomic(session.abs_path, tree)
            except Exception:
                session.tree_id = None
        elif session.core.tree_validity == SessionTreeValidity.INVALID:
            try:
                tree = load_file_to_tree(str(session.core.session_source_path))
                session.tree_id = str(tree.tree_id)
            except Exception:
                session.tree_id = None
