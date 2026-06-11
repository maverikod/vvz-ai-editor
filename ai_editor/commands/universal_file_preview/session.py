"""
TreeSession (C-011) ownership and lifecycle for universal_file_preview.

The command supports two modes:
  Caller-owned: caller passes tree_id; command reads without creating.
  Command-owned: no tree_id supplied; command opens a transient session
               and returns its tree_id in the response for reuse.

The command never closes or invalidates a caller-owned session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base_handler import FileHandler
from .errors import PreviewError, INPUT_ERROR_CONFLICTING_PARAMETERS, input_error
from .handlers.markdown_handler import MarkdownFileHandler
from .handlers.python_marked_handler import PythonMarkedTreeHandler
from .handlers.text_handler import TextFileHandler

logger = logging.getLogger(__name__)


def _handler_uses_tree_session(handler: FileHandler) -> bool:
    """Return True when *handler* reads an in-memory CST/JSON/YAML tree session."""
    if isinstance(
        handler, (MarkdownFileHandler, TextFileHandler, PythonMarkedTreeHandler)
    ):
        return False
    return True


def merge_edit_session_into_preview_params(
    params: dict[str, Any],
) -> dict[str, Any] | PreviewError:
    """Bind preview to an active universal_file_edit session when session_id is set.

    Injects ``tree_id`` from the edit session so preview reads the same in-memory
    tree as ``universal_file_edit``. For text and tree-temp sessions (no
    registered ``tree_id``), sets ``_preview_abs_path`` to the draft file path
    so preview reflects uncommitted edits.

    Args:
        params: Validated preview parameters (project-relative ``file_path``).

    Returns:
        Updated params dict, or PreviewError on unknown session or mismatch.
    """
    session_id = params.get("session_id")
    if session_id is None:
        return params

    from ai_editor.commands.universal_file_edit.format_group import (
        FORMAT_SIDECAR,
        FORMAT_TEXT,
        FORMAT_TREE_TEMP,
    )
    from ai_editor.commands.universal_file_edit.session import get_session

    try:
        edit_sess = get_session(session_id)
    except ValueError:
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            f"session_id {session_id!r} not found in edit session registry.",
            details={"session_id": session_id},
        )

    rel_path = params.get("file_path")
    if rel_path is not None and Path(edit_sess.file_path) != Path(rel_path):
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            "session_id does not match file_path for this edit session.",
            details={
                "session_id": session_id,
                "file_path": rel_path,
                "session_file_path": edit_sess.file_path,
            },
        )

    explicit_tree_id = params.get("tree_id")
    if edit_sess.tree_id:
        if explicit_tree_id is not None and explicit_tree_id != edit_sess.tree_id:
            return input_error(
                INPUT_ERROR_CONFLICTING_PARAMETERS,
                "tree_id conflicts with the tree bound to session_id.",
                details={
                    "session_id": session_id,
                    "tree_id": explicit_tree_id,
                    "session_tree_id": edit_sess.tree_id,
                },
            )
        merged: dict[str, Any] = {**params, "tree_id": edit_sess.tree_id}
        if edit_sess.format_group == FORMAT_SIDECAR:
            merged["_preview_abs_path"] = str(edit_sess.draft_path)
        return merged

    if explicit_tree_id is not None:
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            "tree_id was supplied but the edit session has no in-memory tree.",
            details={"session_id": session_id, "tree_id": explicit_tree_id},
        )

    if edit_sess.format_group in (FORMAT_TEXT, FORMAT_TREE_TEMP):
        # Text and tree-temp sessions have no registered tree_id; preview draft text.
        merged = {k: v for k, v in params.items() if k != "tree_id"}
        merged["_preview_abs_path"] = str(edit_sess.draft_path)
        return merged

    return params


def resolve_session(
    handler: FileHandler,
    params: dict[str, Any],
) -> tuple[Any | None, str, str | None] | PreviewError:
    """
    Resolve the TreeSession (C-011) for the request.

    Returns a 3-tuple: (session, session_origin, tree_id).
      session: the in-memory session object (type depends on handler), or None
               when no session infrastructure is needed by the handler.
      session_origin: 'caller_owned' when tree_id was supplied by the caller;
                      'command_created' when the command opened the session;
                      'none' when no session is used.
      tree_id: the session UUID when session_origin=='command_created', else None.

    The command never closes a caller_owned session.

    Args:
        handler: The FileHandler that will use the session.
        params: Validated parameter dict, may contain 'tree_id'.

    Returns:
        3-tuple or PreviewError.
    """
    if not _handler_uses_tree_session(handler):
        # Markdown/text handlers read source from disk and honour PreviewBudget directly;
        # a stale tree_id from another preview must not bind a tree session here.
        return (None, "none", None)

    tree_id_param = params.get("tree_id")
    if tree_id_param is not None:
        # Caller-owned: CST session registry first, then YAML tree session.
        from ...core.cst_tree.tree_builder import (
            get_tree as cst_get_tree,
        )  # noqa: PLC0415
        from ...core.yaml_tree.tree_builder import (
            get_tree as yaml_get_tree,
        )  # noqa: PLC0415

        session: Any = cst_get_tree(tree_id_param)
        if session is None:
            from ...core.json_tree.tree_builder import (  # noqa: PLC0415
                get_tree as json_get_tree,
            )

            session = json_get_tree(tree_id_param)
        if session is None:
            session = yaml_get_tree(tree_id_param)
        if session is None:
            # Unknown tree_id — treat as CONFLICTING_PARAMETERS
            from .errors import (
                INPUT_ERROR_CONFLICTING_PARAMETERS,
                input_error,
            )

            return input_error(
                INPUT_ERROR_CONFLICTING_PARAMETERS,
                f"tree_id {tree_id_param!r} not found in session registry.",
                details={"tree_id": tree_id_param},
            )
        return (session, "caller_owned", None)
    # Command-owned transient session: defer to handler's open_root; no pre-open.
    # The handler is responsible for opening its own session internally if needed.
    return (None, "none", None)
