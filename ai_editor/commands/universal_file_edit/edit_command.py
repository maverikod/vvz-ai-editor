"""
UniversalFileEditCommand: applies a batch of mutations to the draft.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.edit_command_metadata import (
    get_universal_file_edit_metadata,
)
from ai_editor.commands.universal_file_edit.errors import (
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
                        "node_ref/short_id or json_pointer; text node_ref or line ranges."
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

        fg = session.format_group
        if fg == FORMAT_SIDECAR:
            validation = validate_sidecar_nested_batch(operations, session.tree_id)
            if validation is not None:
                return error_result_from_make_error(validation)
            result = await self._apply_sidecar(session, operations)
        elif fg == FORMAT_TREE_TEMP:
            result = await self._apply_tree_temp(session, operations)
        else:
            result = await self._apply_text(session, operations)

        if session.is_invalid and isinstance(result, SuccessResult):
            payload = dict(result.data)
            payload["warning"] = invalid_session_warning(session)
            return SuccessResult(data=payload)
        return result

    async def _apply_sidecar(
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
        return await asyncio.to_thread(run_sidecar_cst_edit_batch, session, operations)

    async def _apply_tree_temp(
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
        return await asyncio.to_thread(
            tree_temp_edit_batch.apply_tree_temp_mutations,
            session,
            operations,
        )

    async def _apply_text(
        self, session: EditSession, operations: List[Dict[str, Any]]
    ) -> SuccessResult | ErrorResult:
        """Apply text edits to ``session.draft_path`` sorted bottom-up."""

        return await asyncio.to_thread(run_text_draft_apply, session, operations)
