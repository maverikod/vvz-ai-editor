"""Project-scope enforcement for the session-scoped ``universal_file_*`` commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``universal_file_edit``, ``universal_file_write``, ``universal_file_search``,
``universal_file_node_at_line`` and ``universal_file_move_nodes`` all declare
``project_id`` as a REQUIRED string, but each of them resolves its target from
``session_id`` (plus ``file_path``) alone. Until this module existed the
parameter was discarded outright — ``del project_id`` / ``_ = project_id`` — so
an empty string and a well-formed-but-wrong project UUID both produced full,
correct results for a file belonging to a different project. That is a
cross-project isolation hole, not a cosmetic one: a caller that passes the wrong
project id gets no error and operates on another project's file.

Two commands already got this right and are the reference behaviour here; this
module reuses their mechanism rather than inventing a second one.

* ``universal_file_open`` rejects an empty ``project_id`` with the stable
  ``VALIDATION_ERROR`` (raised by the Code Analysis client's ``session_id,
  project_id, and file_path are required`` guard), and it is genuinely
  project-scoped: a wrong project id cannot reach another project's file,
  because the file is looked up in that project's index.
* ``universal_file_preview`` already refuses the exact mismatch this module
  enforces -- ``if str(edit_session.project_id) != project_id`` ->
  ``VALIDATION_ERROR`` with the message ``session_id does not match
  project_id`` (``universal_file_preview_runtime.py``).

So both conditions map to the SAME stable code the surface already uses for
them, and the message distinguishes which one fired. Emitting some other code
here would mean one condition answering with two different codes depending on
which command the caller happened to use. ``VALIDATION_ERROR`` is declared in
the ``error_cases`` of ``universal_file_open`` and ``universal_file_write``, and
is added to those of ``universal_file_search`` and
``universal_file_node_at_line`` alongside this change.

The session's owning project is recorded on the ``EditSession`` at open time
(``EditSession.project_id``), so the check is a local comparison and costs no
Code Analysis round-trip.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from ai_editor.commands.universal_file_edit.errors import error_result_for_edit
from ai_editor.commands.universal_file_edit.session import get_session

VALIDATION_ERROR = "VALIDATION_ERROR"
PROJECT_ID_REQUIRED_MESSAGE = (
    "project_id is required and must be the project the session's file was "
    "opened from"
)
# Verbatim from universal_file_preview_runtime, so one condition keeps one
# message across the whole command surface.
PROJECT_ID_MISMATCH_MESSAGE = "session_id does not match project_id"


def normalized_project_id(project_id: Any) -> str:
    """Return ``project_id`` as a trimmed string; non-strings normalize to ''."""
    if not isinstance(project_id, str):
        return ""
    return project_id.strip()


def project_scope_error(
    project_id: Any,
    session_id: Any,
    file_path: Any = "",
) -> Optional[ErrorResult]:
    """Reject a missing or foreign ``project_id`` for a session-scoped command.

    Args:
        project_id: The caller's declared project UUID.
        session_id: The CA session id the command was addressed to.
        file_path: Project-relative path, required only when the session bundle
            holds more than one open file.

    Returns:
        ``None`` when the call may proceed, otherwise an ``ErrorResult``
        carrying the stable ``VALIDATION_ERROR`` code -- with
        :data:`PROJECT_ID_REQUIRED_MESSAGE` when ``project_id`` is empty or
        blank, and :data:`PROJECT_ID_MISMATCH_MESSAGE` when the session's file
        belongs to a different project.

    An unresolvable session yields ``None`` on purpose: session resolution is
    the calling command's own responsibility and it already reports
    ``SESSION_NOT_FOUND`` / ``SESSION_FILE_PATH_REQUIRED`` with the details that
    command documents. This guard never masks those.
    """
    requested = normalized_project_id(project_id)
    if requested == "":
        return error_result_for_edit(
            message=PROJECT_ID_REQUIRED_MESSAGE,
            code=VALIDATION_ERROR,
            details={"project_id": project_id},
        )
    try:
        session = get_session(
            str(session_id or "").strip(),
            file_path=str(file_path or "") or None,
        )
    except ValueError:
        return None
    owner = normalized_project_id(session.project_id)
    if owner == "" or owner == requested:
        # ``owner == ''`` can only happen for a session built in-process without
        # a project id; ``universal_file_open`` rejects an empty ``project_id``
        # on both its create and its non-create path, so no session reachable
        # over the API carries an empty owner.
        return None
    return error_result_for_edit(
        message=PROJECT_ID_MISMATCH_MESSAGE,
        code=VALIDATION_ERROR,
        details={
            "session_id": str(session_id or "").strip(),
            "file_path": session.file_path,
            "project_id": requested,
            "session_project_id": owner,
        },
    )
