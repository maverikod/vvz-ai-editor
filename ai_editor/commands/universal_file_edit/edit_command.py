"""
UniversalFileEditCommand: applies a batch of mutations to the draft.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.edit_command_metadata import (
    get_universal_file_edit_metadata,
)
from ai_editor.commands.universal_file_edit.errors import (
    READ_ONLY_SESSION,
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.invalid_write_support import (
    invalid_session_warning,
)
from ai_editor.commands.universal_file_edit.session import EditSession, get_session
from ai_editor.commands.universal_file_edit.sidecar_cst_apply import (
    run_sidecar_cst_edit_batch,
    validate_sidecar_nested_batch,
)
from ai_editor.commands.universal_file_edit.text_draft_apply import (
    run_text_draft_apply,
)
from ai_editor.commands.universal_file_edit import tree_temp_edit_batch
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)


def _draft_sha256(session: EditSession) -> Optional[str]:
    """Return the SHA-256 of the session draft, or None when it is absent.

    All format groups serialize the edited content to ``session.draft_path``
    (sidecar writes the source draft, tree-temp serializes its tree, text writes
    the draft directly), so comparing this digest before and after an edit batch
    detects whether the batch changed anything (R6 modified-flag semantics).

    Args:
        session: The EditSession whose draft file is hashed.

    Returns:
        Hex SHA-256 of the draft bytes, or None when the draft file is missing.
    """
    draft_path = session.draft_path
    try:
        return hashlib.sha256(draft_path.read_bytes()).hexdigest()
    except (FileNotFoundError, OSError):
        return None


class UniversalFileEditCommand(BaseMCPCommand):
    """MCP command that applies a batch of mutation operations to the draft.

    The original file is never touched. For sidecar group, a batch that targets
    both a parent node and its descendant is rejected with NESTED_BATCH_FORBIDDEN;
    sibling batches (e.g. class methods, nested functions under the same outer def)
    are allowed and preserve stable_id across ops.
    """

    name = "universal_file_edit"

    version = "1.0.0"

    descr = "Apply a batch of universal file edit operations to the session draft."

    category = "file_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name.

        Returns:
            MCP command name string.
        """
        return "universal_file_edit"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, session_id, operations.
        """
        return {
            "type": "object",
            "x-use-queue": False,
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "CA session id from session_create; same id on all "
                        "universal_file_* calls."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path. Required when the CA session has "
                        "more than one open file (see multi_file_bundle from open). "
                        "Optional when exactly one file is open."
                    ),
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "Batch of edit operations. Identifier fields must match preview/search: "
                        "Python node_id (int short_id string from preview or search); JSON/YAML "
                        "node_ref/short_id or json_pointer; text node_ref or line ranges. "
                        "structured types are replace, insert, delete, move. "
                        "text range types are replace, insert, delete, move."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["project_id", "session_id", "operations"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileEditCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_edit.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_edit_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        operations: List[Dict[str, Any]],
        file_path: str = "",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the edit command.

        Args:
            project_id: Project UUID (validated by handler; reserved for future checks).
            session_id: Active session identifier.
            operations: Batch of edit operation dicts.
            file_path: Project-relative path when the session holds multiple files.
            **kwargs: Adapter context.

        Returns:
            SuccessResult with payload, or ErrorResult on failure.
        """
        del project_id, kwargs
        ca_session_id = str(session_id).strip()
        guard = SessionGuard(get_code_analysis_client())
        decision = guard.check(OperationKind.EDIT, ca_session_id)
        if decision in (GuardDecision.REJECT, GuardDecision.ALLOW_TERMINATING):
            return error_result_from_make_error(
                make_error(
                    SESSION_NOT_FOUND,
                    f"CA session not found or invalid: {ca_session_id}",
                )
            )
        try:
            session = get_session(ca_session_id, file_path=file_path or None)
        except ValueError as exc:
            msg = str(exc)
            if msg == "SESSION_FILE_PATH_REQUIRED":
                return error_result_from_make_error(
                    make_error(
                        SESSION_FILE_PATH_REQUIRED,
                        "file_path is required when the session has multiple open files",
                        details={"session_id": session_id},
                    )
                )
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )
        if session.read_only:
            return error_result_from_make_error(
                make_error(
                    READ_ONLY_SESSION,
                    session.read_only_reason
                    or "Session is read-only; editing commands are blocked.",
                    details={
                        "session_id": ca_session_id,
                        "file_path": session.file_path,
                    },
                )
            )

        fg = session.format_group
        draft_sha_before = _draft_sha256(session)
        if fg == FORMAT_SIDECAR:
            validation = validate_sidecar_nested_batch(operations, session.tree_id)
            if validation is not None:
                return error_result_from_make_error(validation)
            result = self._apply_sidecar(session, operations)
        elif fg == FORMAT_TREE_TEMP:
            # Tree-temp mutation updates the live session facade and its git-backed
            # history synchronously. Running it in the default executor can leave
            # the command future waiting after the worker has completed.
            result = self._apply_tree_temp(session, operations)
        else:
            result = self._apply_text(session, operations)

        # R6: mark the file modified only when the edit produced a non-empty diff.
        # An edit that leaves the draft byte-identical (e.g. a no-op operation)
        # does not change the flag, so close (R5) is not triggered by no-ops.
        if isinstance(result, SuccessResult):
            if _draft_sha256(session) != draft_sha_before:
                session.modified = True

        if session.is_invalid and isinstance(result, SuccessResult):
            payload = dict(result.data)
            payload["warning"] = invalid_session_warning(session)
            return SuccessResult(data=payload)
        return result

    def _apply_sidecar(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply sidecar group operations via CST ``modify_tree`` and refresh sidecar.

        Each operation runs in isolation: resolve ``stable_id`` against the current
        tree, ``modify_tree`` with one op (stable_id transfer via ``_build_tree_index``),
        then ``write_sidecar_atomic``. On any failure the batch rolls back to the
        pre-batch tree and sidecar snapshot.

        Args:
            session: Active EditSession.
            operations: List of validated edit operation dicts.

        Returns:
            SuccessResult with success/update flags, or ErrorResult on failure.
        """
        # Sidecar mutation updates the live session facade and its git-backed
        # history synchronously; dispatching it to the default executor can
        # leave the command future waiting after the worker has returned.
        return run_sidecar_cst_edit_batch(session, operations)

    def _apply_tree_temp(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply tree-temp group operations to the draft via JSON/YAML pipelines.

        For each operation, updates the registered in-memory tree, then serializes
        the tree to ``session.draft_path``.

        Args:
            session: Active EditSession with tree_id and draft_path.
            operations: Edit operation dicts (``type``/``action``, addresses, values).

        Returns:
            SuccessResult with ``success``/``updated`` flags, or ErrorResult on failure.
        """
        return tree_temp_edit_batch.apply_tree_temp_mutations(session, operations)

    def _apply_text(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply text edits to ``session.draft_path`` sorted bottom-up."""

        # Text mutation updates the live session facade and its git-backed
        # history synchronously; dispatching it to the default executor can
        # leave the command future waiting after the worker has returned.
        return run_text_draft_apply(session, operations)
