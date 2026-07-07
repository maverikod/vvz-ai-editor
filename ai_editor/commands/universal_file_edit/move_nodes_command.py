"""
universal_file_move_nodes: move a block of sibling CST nodes within a session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    READ_ONLY_SESSION,
    SESSION_NOT_FOUND,
    WRITE_FAILED,
    error_result_for_edit,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import FORMAT_SIDECAR
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    apply_tree_operation,
    get_session,
)
from ai_editor.core.edit_session.edit_operations_adapter import (
    command_op_to_edit_operation,
    resolve_node_ref_to_short_id,
    session_has_map_tree,
    session_has_valid_tree,
)
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.edit_operations import EditOperationError
from ai_editor.commands.universal_file_edit.sidecar_cst_apply import (
    _preview_short_id_to_stable_id,
    run_sidecar_cst_edit_batch,
)
from ai_editor.commands.universal_file_edit.move_nodes_command_metadata import (
    get_universal_file_move_nodes_metadata,
)
from ai_editor.core.cst_tree.models import CSTTree, ROOT_NODE_ID_SENTINEL
from ai_editor.core.cst_tree.node_stable_id import logical_source_from_module
from ai_editor.core.cst_tree.tree_builder import get_tree, load_file_to_tree
from ai_editor.tree.sibling_convention import sibling_tree_path


def _resolve_cst_node_span_id(tree: CSTTree, node_ref: str) -> Optional[str]:
    """Map preview stable_id or span node_id to current metadata_map key."""
    if node_ref in tree.metadata_map:
        return node_ref
    meta = tree.find_by_stable_id(node_ref)
    if meta is not None:
        return meta.node_id
    return None


def _sorted_node_ids_by_tree_order(tree: CSTTree, node_ids: List[str]) -> List[str]:
    """Return node_ids sorted by start_line in the tree (source order)."""

    def _line(nid: str) -> int:
        span_id = _resolve_cst_node_span_id(tree, nid) or nid
        meta = tree.metadata_map.get(span_id)
        return meta.start_line if meta else 0

    return sorted(node_ids, key=_line)


def _ordered_short_ids(session: EditSession, node_refs: List[str]) -> List[int]:
    """Return short_ids sorted by source line order using session MAP + source parse."""
    sections = parse_tree_file(
        session.core.session_tree_path.read_text(encoding="utf-8")
    )
    short_ids = [resolve_node_ref_to_short_id(ref, sections) for ref in node_refs]
    from ai_editor.tree.handler_registry import HandlerRegistry

    handler = HandlerRegistry.default_registry().resolve(session.abs_path)
    source = session.core.session_source_path.read_text(encoding="utf-8")
    nodes = handler.parse_content(Path(session.file_path), source)
    line_by_sid = {int(node.short_id): idx for idx, node in enumerate(nodes)}
    return sorted(short_ids, key=lambda sid: line_by_sid.get(sid, sid))


def _run_valid_session_move_batch(
    session: EditSession,
    source_node_ids: List[str],
    target_node_id: Optional[str],
    parent_node_id: Optional[str],
    position: str,
) -> SuccessResult | ErrorResult:
    """Move sibling blocks via MOVE EditOperation on the in-session unified tree."""
    from ai_editor.core.backup_manager import BackupManager

    try:
        bm = BackupManager(root_dir=session.core.project_root)
        bm.create_backup(
            session.core.session_source_path, command="universal_file_move_nodes"
        )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before move failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.core.session_source_path)},
        )

    tree_snapshot = session.core.session_tree_path.read_text(encoding="utf-8")
    source_snapshot = session.core.session_source_path.read_text(encoding="utf-8")

    def _rollback() -> None:
        session.core.session_tree_path.write_text(tree_snapshot, encoding="utf-8")
        session.core.session_source_path.write_text(source_snapshot, encoding="utf-8")

    try:
        ordered_sids = _ordered_short_ids(session, source_node_ids)
        if target_node_id is not None:
            anchor_ref: str | int = target_node_id
            move_pos = position
        else:
            anchor_ref = parent_node_id or ROOT_NODE_ID_SENTINEL
            move_pos = position

        anchor_sid: Optional[int] = None
        for sid in ordered_sids:
            sections = parse_tree_file(
                session.core.session_tree_path.read_text(encoding="utf-8")
            )
            if anchor_sid is None:
                op_dict: Dict[str, Any] = {
                    "type": "move",
                    "node_id": str(sid),
                    "target_node_id": target_node_id,
                    "parent_node_id": parent_node_id,
                    "position": move_pos,
                }
            else:
                op_dict = {
                    "type": "move",
                    "node_id": str(sid),
                    "target_node_id": str(anchor_sid),
                    "position": "after",
                }
            edit_op = command_op_to_edit_operation(op_dict, sections)
            apply_tree_operation(session, edit_op)
            anchor_sid = sid
    except (EditOperationError, ValueError) as exc:
        _rollback()
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"source_node_ids": source_node_ids},
        )
    except Exception as exc:
        _rollback()
        return error_result_for_edit(
            str(exc), WRITE_FAILED, {"path": str(session.abs_path)}
        )

    return SuccessResult(
        data={"success": True, "updated": True, "moved": len(source_node_ids)}
    )


def _resolve_sidecar_stable_id(session: EditSession, node_ref: str) -> Optional[str]:
    """Map preview short_id to CST stable_id when ref is numeric."""
    raw = str(node_ref).strip()
    if not raw.isdigit():
        return raw
    return _preview_short_id_to_stable_id(session, raw)


def _run_sidecar_move_batch(
    session: EditSession,
    source_node_ids: List[str],
    target_node_id: Optional[str],
    parent_node_id: Optional[str],
    position: str,
) -> SuccessResult | ErrorResult:
    """Move source nodes to a new position using a copy of the source file.

    All mutations happen on a .py.tmp copy. The original file is only
    replaced after successful validation via compile(). On failure the
    temp files are deleted and the original session is untouched.
    """
    if session_has_map_tree(session.core):
        return _run_valid_session_move_batch(
            session,
            source_node_ids,
            target_node_id,
            parent_node_id,
            position,
        )

    resolved_sources: List[str] = []
    for ref in source_node_ids:
        stable = _resolve_sidecar_stable_id(session, ref)
        if stable is None:
            return error_result_for_edit(
                f"Unknown short_id: {ref}",
                "UNKNOWN_NODE_REF",
                {"node_ref": ref},
            )
        resolved_sources.append(stable)
    source_node_ids = resolved_sources
    if target_node_id is not None:
        stable_target = _resolve_sidecar_stable_id(session, target_node_id)
        if stable_target is None:
            return error_result_for_edit(
                f"Unknown short_id: {target_node_id}",
                "UNKNOWN_NODE_REF",
                {"node_ref": target_node_id},
            )
        target_node_id = stable_target
    if parent_node_id is not None and parent_node_id != ROOT_NODE_ID_SENTINEL:
        stable_parent = _resolve_sidecar_stable_id(session, parent_node_id)
        if stable_parent is None:
            return error_result_for_edit(
                f"Unknown short_id: {parent_node_id}",
                "UNKNOWN_NODE_REF",
                {"node_ref": parent_node_id},
            )
        parent_node_id = stable_parent

    # --- Resolve original tree ---
    tid = session.tree_id
    tree = get_tree(tid) if tid else None
    if tree is None:
        try:
            tree = load_file_to_tree(str(session.abs_path))
        except FileNotFoundError as exc:
            return error_result_for_edit(
                str(exc), "FILE_NOT_FOUND", {"path": str(session.abs_path)}
            )
        except Exception as exc:
            return error_result_for_edit(
                str(exc), PARSE_ERROR, {"path": str(session.abs_path)}
            )
    session.tree_id = tree.tree_id

    # --- Predcheck: all source_node_ids exist ---
    for nid in source_node_ids:
        if _resolve_cst_node_span_id(tree, nid) is None:
            return error_result_for_edit(
                f"Node not found: {nid}",
                "STALE_NODE_ID",
                {
                    "stable_id": nid,
                    "hint": "Re-call universal_file_preview with session_id.",
                },
            )

    # --- Step 1: remember source text for each node (before any mutation) ---
    ordered_ids = _sorted_node_ids_by_tree_order(tree, source_node_ids)
    node_codes: List[str] = []
    for nid in ordered_ids:
        span_id = _resolve_cst_node_span_id(tree, nid)
        if span_id is None:
            return error_result_for_edit(
                f"Node not found: {nid}",
                "STALE_NODE_ID",
                {"stable_id": nid},
            )
        node = tree.node_map.get(span_id)
        if node is None:
            return error_result_for_edit(
                f"Node object missing for id: {nid}",
                "STALE_NODE_ID",
                {"stable_id": nid},
            )
        node_codes.append(tree.module.code_for_node(node))

    combined_code = "".join(node_codes)

    # --- Step 2: copy the source file to .py.tmp ---
    orig_path = session.abs_path
    tmp_path = orig_path.with_suffix(".py.tmp")
    tmp_sidecar = sibling_tree_path(tmp_path.resolve())
    orig_sidecar = sibling_tree_path(orig_path.resolve())

    def _cleanup_tmp() -> None:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            tmp_sidecar.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        import shutil

        shutil.copy2(str(orig_path), str(tmp_path))
    except Exception as exc:
        return error_result_for_edit(str(exc), WRITE_FAILED, {"path": str(tmp_path)})

    # --- Step 3: load tree from the copy ---
    try:
        tmp_tree = load_file_to_tree(str(tmp_path))
    except Exception as exc:
        _cleanup_tmp()
        return error_result_for_edit(str(exc), PARSE_ERROR, {"path": str(tmp_path)})

    # --- Step 4: build a temporary session pointing at the copy ---
    # replace() is dataclasses.replace — creates a copy with abs_path = tmp_path.
    # tree_id is updated to the tmp tree.
    tmp_session = replace(session, abs_path=tmp_path, tree_id=tmp_tree.tree_id)

    # --- Step 5: apply DELETE ops then INSERT via run_sidecar_cst_edit_batch ---
    # DELETE all source nodes (bottom-up order is handled inside the batch).
    delete_ops: List[Dict[str, Any]] = [
        {"type": "delete", "node_id": nid} for nid in ordered_ids
    ]
    result = run_sidecar_cst_edit_batch(tmp_session, delete_ops)
    if isinstance(result, ErrorResult):
        _cleanup_tmp()
        return result

    # INSERT combined code at the target position.
    if target_node_id is not None:
        insert_op: Dict[str, Any] = {
            "type": "insert",
            "target_node_id": target_node_id,
            "position": position,
            "code": combined_code,
        }
    else:
        insert_op = {
            "type": "insert",
            "parent_node_id": parent_node_id or ROOT_NODE_ID_SENTINEL,
            "position": position,
            "code": combined_code,
        }
    result = run_sidecar_cst_edit_batch(tmp_session, [insert_op])
    if isinstance(result, ErrorResult):
        _cleanup_tmp()
        return result

    # --- Step 6: validate via compile() ---
    tmp_tree_id = tmp_session.tree_id
    if tmp_tree_id is None:
        _cleanup_tmp()
        return error_result_for_edit(
            "Tmp session has no tree_id after operations", "INVALID_OPERATION", {}
        )
    assert tmp_tree_id is not None  # noqa: S101  # narrows Optional[str] → str for mypy
    tmp_tree_after = get_tree(tmp_tree_id)
    if tmp_tree_after is None:
        _cleanup_tmp()
        return error_result_for_edit(
            "Tmp tree lost after operations", "INVALID_OPERATION", {}
        )
    source_after = logical_source_from_module(tmp_tree_after.module)
    try:
        compile(source_after, str(tmp_path), "exec")
    except SyntaxError as exc:
        _cleanup_tmp()
        return error_result_for_edit(
            f"Move produced invalid Python: SyntaxError at line {exc.lineno}: {exc.msg}",
            "INVALID_OPERATION",
            {"syntax_error": str(exc), "source_node_ids": source_node_ids},
        )

    # --- Step 7: commit --- atomic rename of file and sidecar ---
    try:
        os.replace(str(tmp_path), str(orig_path))
        if tmp_sidecar.exists():
            tmp_sidecar.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(tmp_sidecar), str(orig_sidecar))
    except Exception as exc:
        _cleanup_tmp()
        return error_result_for_edit(str(exc), WRITE_FAILED, {"path": str(orig_path)})

    # --- Step 8: reload original session tree from updated file ---
    try:
        new_tree = load_file_to_tree(str(orig_path))
        session.tree_id = new_tree.tree_id
    except Exception:
        pass  # session will reload on next access

    return SuccessResult(
        data={"success": True, "updated": True, "moved": len(ordered_ids)}
    )


class UniversalFileMoveNodesCommand(BaseMCPCommand):
    """MCP command that moves a block of sibling CST nodes to a new position.

    Works within an open universal_file_edit session (Python/sidecar only).
    All mutations happen on a temporary .py.tmp copy. The original file is
    replaced atomically only after compile() validation succeeds.
    """

    name = "universal_file_move_nodes"

    version = "1.0.0"

    descr = (
        "Move a block of sibling CST nodes to a new position in the same file session."
    )

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
        return "universal_file_move_nodes"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id, session_id, source_node_ids,
            target_node_id, parent_node_id, position.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid project_id values.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Active session UUID returned by universal_file_open.",
                },
                "source_node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": (
                        "node_ref values from universal_file_preview (short_id string, "
                        "JSON Pointer, or MAP UUID). All formats with a valid marked-tree "
                        "session. Caller order is ignored; nodes move in source line order."
                    ),
                },
                "target_node_id": {
                    "type": "string",
                    "description": (
                        "Sibling anchor: insert block before or after this node. "
                        "Mutually exclusive with parent_node_id."
                    ),
                },
                "parent_node_id": {
                    "type": "string",
                    "description": (
                        "Container anchor: insert block as first or last child. "
                        "Use __root__ for module level. "
                        "Mutually exclusive with target_node_id."
                    ),
                },
                "position": {
                    "type": "string",
                    "enum": ["before", "after", "first", "last"],
                    "description": (
                        "With target_node_id: before|after. "
                        "With parent_node_id: first|last."
                    ),
                    "default": "after",
                },
            },
            "required": ["project_id", "session_id", "source_node_ids"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileMoveNodesCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_move_nodes.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_move_nodes_metadata(cls))

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters semantically beyond JSON schema constraints.

        Args:
            params: Raw parameter dict from the MCP adapter.

        Returns:
            Validated and normalised parameter dict.
        """
        params = super().validate_params(params)
        target = params.get("target_node_id")
        parent = params.get("parent_node_id")
        if target is not None and parent is not None:
            raise ValueError(
                "Provide either target_node_id or parent_node_id, not both."
            )
        return params

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        source_node_ids: List[str],
        target_node_id: Optional[str] = None,
        parent_node_id: Optional[str] = None,
        position: str = "after",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute move_nodes on the session draft.

        Args:
            project_id: Project UUID (reserved for future validation).
            session_id: Active session identifier.
            source_node_ids: Stable UUIDs of nodes to move.
            target_node_id: Sibling anchor node UUID (before|after).
            parent_node_id: Container node UUID (first|last).
            position: Insertion position (before|after|first|last).
            **kwargs: Adapter context.

        Returns:
            SuccessResult with moved count, or ErrorResult on failure.
        """
        del project_id, kwargs

        if target_node_id is None and parent_node_id is None:
            parent_node_id = ROOT_NODE_ID_SENTINEL
            position = "last"

        try:
            session = get_session(session_id)
        except ValueError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )
        if session.read_only:
            return error_result_from_make_error(
                make_error(
                    READ_ONLY_SESSION,
                    session.read_only_reason
                    or "Session is read-only; editing commands are blocked.",
                    details={"session_id": session_id, "file_path": session.file_path},
                )
            )

        if session.format_group != FORMAT_SIDECAR:
            if not session_has_map_tree(session.core):
                return error_result_from_make_error(
                    make_error(
                        "INVALID_OPERATION",
                        "universal_file_move_nodes requires a valid marked-tree session "
                        "(re-open the file or fix parse errors before moving nodes).",
                    )
                )
            return await asyncio.to_thread(
                _run_valid_session_move_batch,
                session,
                source_node_ids,
                target_node_id,
                parent_node_id,
                position,
            )

        return await asyncio.to_thread(
            _run_sidecar_move_batch,
            session,
            source_node_ids,
            target_node_id,
            parent_node_id,
            position,
        )
