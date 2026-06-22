"""
UniversalFileCloseCommand: ends an editing session with group-specific cleanup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    list_bundle_file_paths,
    release_session,
    resolve_session_for_command,
)
from ai_editor.commands.universal_file_edit.close_command_metadata import (
    get_universal_file_close_metadata,
)
from ai_editor.core.edit_session.workspace_layout import remove_file_subtree
from ai_editor.core.editor_workspace_paths import (
    file_workspace_layout,
    resolve_workspace_root,
)
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)

logger = logging.getLogger(__name__)


class UniversalFileCloseCommand(BaseMCPCommand):
    """MCP command that ends a session with Close Stage workspace cleanup.

    Sidecar: verify checksum; rebuild on mismatch; never delete sidecar.
    Tree-temp: sha256 compare draft vs original; delete or rebuild draft; free tree.
    Text: delete draft unconditionally.
    Multi-file: requires file_path when N>1; response includes remaining_open_files.
    """

    name = "universal_file_close"

    version = "1.0.0"

    descr = "End a universal file edit session with format-group-specific cleanup."

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
        return "universal_file_close"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and session_id.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Required for CA unlock (C-023) and "
                        "workspace path resolution."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "CA session id (required; same id as session_create on "
                        "Code Analysis Server)."
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
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileCloseCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_close.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_close_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        file_path: str = "",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the close command.

        Args:
            project_id: Required by schema; used for CA unlock and workspace paths.
            session_id: CA session identifier.
            file_path: Project-relative path when the session holds multiple files.
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with cleanup details, or ErrorResult on session not found.
        """
        _ = kwargs
        ca_session_id = str(session_id or "").strip()
        pid = str(project_id or "").strip()
        guard = SessionGuard(get_code_analysis_client())
        decision = guard.check(OperationKind.CLOSE, ca_session_id)
        if decision == GuardDecision.REJECT:
            return ErrorResult(
                message="session_id is required for universal_file_close",
                code=cast(Any, "SESSION_REJECTED"),
            )
        try:
            session = resolve_session_for_command(
                ca_session_id,
                file_path or None,
            )
        except ValueError as exc:
            msg = str(exc)
            if msg == "SESSION_FILE_PATH_REQUIRED":
                return error_result_from_make_error(
                    make_error(
                        SESSION_FILE_PATH_REQUIRED,
                        "file_path is required when the session has multiple open files",
                        details={"session_id": ca_session_id},
                    )
                )
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {ca_session_id}")
            )
        is_last_file = len(list_bundle_file_paths(ca_session_id)) == 1
        client = get_code_analysis_client()
        unlock_ok = client.unlock_session_file(
            session_id=ca_session_id,
            project_id=pid,
            file_path=session.file_path,
        )
        if not unlock_ok:
            logger.info(
                "close unlock best-effort failed for %s/%s",
                ca_session_id,
                session.file_path,
            )
        fg = session.format_group
        payload: Dict[str, Any] = {"success": True, "draft_rebuilt": False}
        try:
            if fg == FORMAT_SIDECAR:
                payload = self._close_sidecar(session)
            else:
                payload = self._close_tree_temp_or_text(session)
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "close format cleanup skipped for %s/%s: %s",
                ca_session_id,
                session.file_path,
                exc,
            )
        try:
            session.core.close()
        finally:
            release_session(ca_session_id, session.file_path)
        remaining = list_bundle_file_paths(ca_session_id)
        payload["closed_file_path"] = session.file_path
        payload["remaining_open_files"] = remaining
        payload["session_retained"] = len(remaining) > 0
        workspace_root = resolve_workspace_root()
        layout = file_workspace_layout(
            workspace_root,
            ca_session_id,
            pid,
            session.file_path,
        )
        workspace_subtree_removed = False
        if layout.file_subtree_dir.is_dir():
            remove_file_subtree(file_subtree_dir=layout.file_subtree_dir)
            workspace_subtree_removed = True
        session_dir_removed = False
        if is_last_file and layout.session_dir.is_dir():
            shutil.rmtree(layout.session_dir)
            session_dir_removed = True
        payload["session_id"] = ca_session_id
        payload["project_id"] = pid
        payload["file_path"] = session.file_path
        payload["unlock_ok"] = unlock_ok
        payload["workspace_subtree_removed"] = workspace_subtree_removed
        payload["session_dir_removed"] = session_dir_removed
        return SuccessResult(data=payload)

    def _close_sidecar(self, session: EditSession) -> Dict[str, Any]:
        """Close a sidecar group session.

        Verifies sidecar checksum. On mismatch rebuilds sidecar from source.
        Sidecar is never deleted.

        Args:
            session: Active sidecar group EditSession.

        Returns:
            Dict with success=True and draft_rebuilt flag.
        """
        from ai_editor.core.cst_tree import tree_builder as cst_builder
        from ai_editor.core.cst_tree.tree_sidecar import (
            read_sidecar_payload,
            verify_sidecar_against_source,
            write_sidecar_atomic,
        )

        tree = cst_builder.load_file_to_tree(str(session.abs_path))
        payload = read_sidecar_payload(session.abs_path)
        if payload is not None and verify_sidecar_against_source(
            tree.module.code, payload
        ):
            return {"success": True, "draft_rebuilt": False}
        write_sidecar_atomic(session.abs_path, tree)
        return {"success": True, "draft_rebuilt": True}

    def _close_tree_temp_or_text(self, session: EditSession) -> Dict[str, Any]:
        """Close a tree-temp or text group session.

        Args:
            session: Active tree-temp or text group EditSession.

        Returns:
            Dict with success=True and draft_rebuilt flag.
        """
        fg = session.format_group
        abs_path = session.abs_path

        if fg == FORMAT_TEXT:
            session.draft_path.unlink(missing_ok=True)
            return {"success": True, "draft_rebuilt": False}

        if fg == FORMAT_TREE_TEMP and session.tree_temp_roots is not None:
            session.draft_path.unlink(missing_ok=True)
            session.tree_temp_roots = None
            draft_rebuilt = False
        else:
            draft_rebuilt = False
            if session.draft_path.exists():
                draft_sha = hashlib.sha256(session.draft_path.read_bytes()).hexdigest()
                orig_sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
                if draft_sha == orig_sha:
                    session.draft_path.unlink(missing_ok=True)
                else:
                    if session.handler_id == "json":
                        import json

                        from ai_editor.core.json_tree import (
                            tree_builder as json_builder,
                        )

                        loaded_json = json_builder.load_file_to_tree(str(abs_path))
                        draft_text = (
                            json.dumps(
                                loaded_json.root_data,
                                indent=2,
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        session.draft_path.write_text(draft_text, encoding="utf-8")
                        json_builder.remove_tree(loaded_json.tree_id)
                    else:
                        import yaml

                        from ai_editor.core.yaml_tree import (
                            tree_builder as yaml_builder,
                        )

                        loaded_yaml = yaml_builder.load_file_to_tree(str(abs_path))
                        draft_text = yaml.safe_dump(
                            loaded_yaml.root_data,
                            default_flow_style=False,
                            allow_unicode=True,
                            sort_keys=False,
                        )
                        session.draft_path.write_text(draft_text, encoding="utf-8")
                        yaml_builder.remove_tree(loaded_yaml.tree_id)
                    draft_rebuilt = True

        if session.tree_id:
            if session.handler_id == "json":
                from ai_editor.core.json_tree import tree_builder as json_builder

                json_builder.remove_tree(session.tree_id)
            else:
                from ai_editor.core.yaml_tree import tree_builder as yaml_builder

                yaml_builder.remove_tree(session.tree_id)

        return {"success": True, "draft_rebuilt": draft_rebuilt}
