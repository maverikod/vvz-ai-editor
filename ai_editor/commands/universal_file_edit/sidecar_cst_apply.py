"""
Apply CST edit batches inside universal_file_edit sidecar sessions.

Persists trees via write_sidecar_atomic at the sibling path <source>.py.tree (C-003).
Does not resolve .cst/ or pending sidecar paths.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import libcst as cst

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.cst_modify_tree_ops_build import build_tree_operations
from ai_editor.core.cst_tree.tree_modifier_ops_parse import join_code_lines
from ai_editor.commands.universal_file_edit.errors import (
    NESTED_BATCH_FORBIDDEN,
    PARSE_ERROR,
    UNKNOWN_NODE_REF,
    error_result_for_edit,
    make_error,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.core.edit_session.edit_operations_adapter import (
    _normalize_action,
    apply_command_ops_on_session_tree,
    _operation_uses_node_address,
    session_has_map_tree,
    session_has_valid_tree,
    sidecar_ops_use_unified_tree,
)
from ai_editor.core.cst_tree.models import CSTTree, ROOT_NODE_ID_SENTINEL
from ai_editor.core.cst_tree.node_stable_id import logical_source_from_module
from ai_editor.core.cst_tree.tree_builder import (
    get_tree,
    load_file_to_tree,
    rollback_tree_to_code,
)
from ai_editor.core.cst_tree.tree_modifier import modify_tree
from ai_editor.core.cst_tree.tree_sidecar import write_sidecar_atomic


def _edit_source_path(session: EditSession) -> Path:
    """Workspace draft source inside the edit subdir (not project origin path)."""
    return session.core.session_source_path


class StaleNodeIdError(ValueError):
    """Raised when a stable_id is not found in the current CST tree.

    Attributes:
        field: Name of the op field containing the stale id.
        stable_id: The stale stable_id value.
    """

    def __init__(self, message: str, *, field: str, stable_id: str) -> None:
        """Initialise StaleNodeIdError.

        Args:
            message: Human-readable error message.
            field: Name of the op dict field (node_id / parent_node_id / target_node_id).
            stable_id: The stale stable_id value that was not found.
        """
        super().__init__(message)
        self.field = field
        self.stable_id = stable_id


def _promote_leaf_ref_to_statement_line(tree: CSTTree, node_id: str) -> str:
    """Map preview leaf refs (Name, Integer, …) to enclosing ``SimpleStatementLine``.

    Annotated full-text and structured preview can surface inner-node stable_ids.
    ``universal_file_edit`` replace/delete must target the statement line, not a
    fine-grained leaf (see ``FINE_GRAINED_REPLACE_NODE_TYPES`` in CST modifier).
    """
    meta = tree.metadata_map.get(node_id)
    if meta is None:
        return node_id
    if meta.type in (
        "SimpleStatementLine",
        "FunctionDef",
        "AsyncFunctionDef",
        "ClassDef",
    ):
        return node_id
    if (meta.kind or "") in ("function", "method", "class", "import"):
        return node_id

    current = node_id
    stmt_line_id: Optional[str] = None
    while True:
        row = tree.metadata_map.get(current)
        if row is None:
            break
        if row.type == "SimpleStatementLine" and (row.kind or "") == "stmt":
            stmt_line_id = current
            break
        parent_id = row.parent_id
        if not parent_id:
            break
        current = parent_id
    return stmt_line_id if stmt_line_id else node_id


def _coalesce_node_ref_keys(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal_file_preview ``node_ref`` aliases onto CST op field names."""
    m = dict(op)
    for ref_key, id_key in (
        ("node_ref", "node_id"),
        ("parent_node_ref", "parent_node_id"),
        ("target_node_ref", "target_node_id"),
    ):
        if ref_key in m and not m.get(id_key):
            m[id_key] = m[ref_key]
    if m.get("type") == "insert" or str(m.get("action") or "").lower() == "insert":
        if m.get("before_node_id") and not m.get("target_node_id"):
            m["target_node_id"] = m["before_node_id"]
            if m.get("position") in (None, "after"):
                m["position"] = "before"
        elif m.get("after_node_id") and not m.get("target_node_id"):
            m["target_node_id"] = m["after_node_id"]
            if m.get("position") in (None, "after"):
                m["position"] = "after"
    return m


def _preview_short_id_to_stable_id(
    session: EditSession, short_id: Any
) -> Optional[str]:
    """Map marked-tree preview short_id to CST stable_id for Python sidecar edits."""
    raw = str(short_id).strip()
    if not raw.isdigit():
        return None
    sid = int(raw)
    if sid < 1:
        return None
    from ai_editor.commands.universal_file_preview.marked_tree_loader import (
        resolve_format_handler,
    )

    source_abs = session.core.source_abs
    if source_abs.suffix.lower() not in (".py", ".pyi", ".pyw"):
        return None
    handler = resolve_format_handler(source_abs)
    content = session.core.session_source_path.read_text(encoding="utf-8")
    internal_id: Optional[str] = None
    for node in handler.parse_content(source_abs, content):
        if int(node.short_id) == sid:
            raw_internal = node.attributes.get("internal_node_id")
            if isinstance(raw_internal, str) and raw_internal:
                internal_id = raw_internal
            break
    if internal_id is None:
        return None
    tid = session.tree_id
    tree = get_tree(tid) if tid else None
    if tree is None:
        try:
            tree = load_file_to_tree(str(_edit_source_path(session)))
        except Exception:
            tree = None
    if tree is not None:
        meta = tree.metadata_map.get(internal_id)
        if meta is not None and meta.stable_id:
            return meta.stable_id
    return internal_id


def _translate_sidecar_preview_short_ids(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], bool]:
    """Rewrite numeric preview short_ids to CST stable_ids when session tree is sidecar."""
    if session.handler_id != "python":
        return operations, False
    translated: List[Dict[str, Any]] = []
    ref_fields = (
        "node_id",
        "node_ref",
        "parent_node_id",
        "parent_node_ref",
        "target_node_id",
        "target_node_ref",
        "before_node_id",
        "after_node_id",
    )
    for op in operations:
        m = _coalesce_node_ref_keys(dict(op))
        for field in ref_fields:
            raw = m.get(field)
            if raw in (None, "", ROOT_NODE_ID_SENTINEL):
                continue
            if isinstance(raw, str) and ":" in raw:
                continue
            if not str(raw).strip().isdigit():
                continue
            stable = _preview_short_id_to_stable_id(session, raw)
            if stable is None:
                return operations, False
            if field in ("node_ref", "before_node_id", "after_node_id"):
                if field == "node_ref":
                    m["node_id"] = stable
                elif field == "before_node_id":
                    m["target_node_id"] = stable
                    if m.get("position") in (None, "after"):
                        m["position"] = "before"
                else:
                    m["target_node_id"] = stable
                    if m.get("position") in (None, "after"):
                        m["position"] = "after"
            else:
                m[field] = stable
        translated.append(m)
    return translated, True


def _expand_cst_move_operations(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult | List[Dict[str, Any]]:
    """Expand move ops into delete-then-insert using buffered node source."""
    expanded: List[Dict[str, Any]] = []
    for op in operations:
        m = _coalesce_node_ref_keys(dict(op))
        if _normalize_action(m) != "move":
            expanded.append(op)
            continue
        src = m.get("node_id") or m.get("node_ref")
        if src in (None, ""):
            return error_result_for_edit(
                "move requires node_id or node_ref for the source block.",
                "INVALID_OPERATION",
                {"operation": op},
            )
        tid = session.tree_id
        tree = get_tree(tid) if tid else None
        if tree is None:
            try:
                tree = load_file_to_tree(str(_edit_source_path(session)))
            except Exception as exc:
                return error_result_for_edit(
                    str(exc),
                    PARSE_ERROR,
                    {"path": str(_edit_source_path(session))},
                )
            session.tree_id = tree.tree_id
        try:
            resolved = _resolve_stable_to_span({"type": "delete", "node_id": src}, tree)
        except StaleNodeIdError as stale:
            return error_result_for_edit(
                str(stale),
                "STALE_NODE_ID",
                {"field": stale.field, "stable_id": stale.stable_id},
            )
        delete_id = resolved.get("node_id")
        node = tree.node_map.get(str(delete_id)) if delete_id else None
        if node is None:
            return error_result_for_edit(
                f"Node not found for move source: {src}",
                "STALE_NODE_ID",
                {"stable_id": src},
            )
        payload = tree.module.code_for_node(node)
        expanded.append({"type": "delete", "node_id": src})
        insert_op: Dict[str, Any] = {"type": "insert", "code": payload}
        target = m.get("target_node_id") or m.get("target_node_ref")
        parent = m.get("parent_node_id") or m.get("parent_node_ref")
        position = str(m.get("position") or "after")
        if target not in (None, ""):
            insert_op["target_node_id"] = target
            insert_op["position"] = position
        else:
            insert_op["parent_node_id"] = parent or ROOT_NODE_ID_SENTINEL
            insert_op["position"] = position
        expanded.append(insert_op)
    return expanded


def _resolve_stable_to_span(op: Dict[str, Any], tree: CSTTree) -> Dict[str, Any]:
    """Replace stable_id in node refs with span-based node_id for modify_tree."""
    from ai_editor.core.cst_tree.tree_metadata import _resolve_node_id

    m = _coalesce_node_ref_keys(op)
    raw_action = m.get("action") or m.get("type") or ""
    action = str(raw_action).strip().lower()
    for field in ("node_id", "parent_node_id", "target_node_id"):
        raw = m.get(field)
        if not isinstance(raw, str) or not raw:
            continue
        if ":" not in raw:
            if raw == ROOT_NODE_ID_SENTINEL:
                m[field] = raw
                continue
            meta = tree.find_by_stable_id(raw)
            if meta is None:
                meta = tree.metadata_map.get(raw)
            if meta is None:
                raise StaleNodeIdError(
                    f"stable_id '{raw}' not found in current CST tree metadata.",
                    field=field,
                    stable_id=raw,
                )
            raw = meta.node_id
        resolved = _resolve_node_id(tree, raw)
        if field == "node_id" and action in ("replace", "delete"):
            resolved = _promote_leaf_ref_to_statement_line(tree, resolved)
        m[field] = resolved
    return m


_COMPOUND_CLAUSE_HEADER_PREFIXES = ("elif ", "else:", "except ", "finally:")


def _validate_replace_snippet_via_module(m: Dict[str, Any]) -> None:
    """Validate replace snippets as module statements (not bare expressions).

    Simple assignments such as ``DEFAULT_TIMEOUT = 60`` must parse as statements.
    ``tree_modifier_validate`` may otherwise treat inner ``Name`` targets as
    expressions and reject valid statement replacements.
    """
    action = str(m.get("action") or "").lower()
    if action != "replace":
        return
    raw_code = m.get("code")
    raw_lines = m.get("code_lines")
    if raw_lines is not None:
        if raw_code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        text = join_code_lines([str(line) for line in raw_lines])
    elif isinstance(raw_code, str):
        text = raw_code
    else:
        return
    if not text.strip():
        return
    dedented = textwrap.dedent(text)
    stripped_leading = dedented.lstrip()
    if stripped_leading:
        first_line = stripped_leading.splitlines()[0].strip()
        for prefix in _COMPOUND_CLAUSE_HEADER_PREFIXES:
            if first_line.startswith(prefix):
                header_token = first_line.split()[0]
                raise ValueError(
                    "Replace code_lines must contain only the body statement(s) "
                    "of the target branch, not a compound clause header "
                    f"({header_token!r}). Target the SimpleStatementLine inside "
                    "the branch and supply only the statement line(s) to insert."
                )
    source = dedented if dedented.endswith("\n") else dedented + "\n"
    try:
        mod = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        raise ValueError(f"Invalid code syntax for replace: {exc}") from exc
    if not mod.body:
        raise ValueError("Invalid code syntax for replace: empty module body")
    normalized = mod.code
    if not normalized.endswith("\n"):
        normalized += "\n"
    m["code"] = normalized
    m.pop("code_lines", None)


def _normalized_cst_modify_operation(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal-edit op keys into ``build_tree_operations`` / CST shape."""
    m = dict(op)
    raw_action = op.get("action")
    raw_type = op.get("type")
    if isinstance(raw_action, str) and raw_action.strip():
        m["action"] = raw_action.strip().lower()
    elif isinstance(raw_type, str) and raw_type.strip():
        m["action"] = raw_type.strip().lower()

    action = str(m.get("action") or "").lower()
    if "code" not in m and "code_lines" not in m:
        for alt_key in ("new_content", "content"):
            alt_val = m.get(alt_key)
            if isinstance(alt_val, str):
                m["code"] = alt_val
                break
    if action == "insert":
        target_nid = m.get("target_node_id")
        parent_nid = m.get("parent_node_id")
        pos_raw = m.get("position")
        pos_str = pos_raw.strip().lower() if isinstance(pos_raw, str) else None
        if target_nid and parent_nid:
            if pos_str in ("before", "after"):
                m.pop("parent_node_id", None)
            elif parent_nid == ROOT_NODE_ID_SENTINEL and pos_str in ("first", "last"):
                m.pop("target_node_id", None)
            else:
                raise ValueError(
                    "insert: provide either target_node_id with position before|after "
                    "or parent_node_id with position first|last|{after:N}, not both"
                )
        if target_nid and pos_str in ("before", "after"):
            pass
        elif parent_nid and isinstance(pos_raw, dict) and "after" in pos_raw:
            pass
        elif target_nid and pos_str in ("first", "last"):
            raise ValueError(
                "insert: position first|last requires parent_node_id; "
                "use target_node_id with position before|after for sibling-relative insert"
            )
        elif pos_str in ("before", "after") and not target_nid:
            raise ValueError(
                "insert: position before|after requires target_node_id "
                "(sibling node_ref from universal_file_preview)"
            )

    _validate_replace_snippet_via_module(m)
    return m


def _is_ancestor(
    tree: CSTTree, ancestor_stable_id: str, descendant_stable_id: str
) -> bool:
    """Return True if ancestor_stable_id is an ancestor of descendant_stable_id in tree.

    Args:
        tree: In-memory CST tree object.
        ancestor_stable_id: Stable ID of the potential ancestor node.
        descendant_stable_id: Stable ID of the potential descendant node.

    Returns:
        True if ancestor_stable_id is found in the parent chain of descendant_stable_id.
    """
    node_meta = tree.find_by_stable_id(descendant_stable_id)
    if node_meta is None:
        return False
    current_nid: Optional[str] = node_meta.node_id
    while current_nid is not None:
        parent_nid: Optional[str] = tree.parent_map.get(current_nid)
        if not parent_nid:
            return False
        parent_meta = tree.metadata_map.get(parent_nid)
        if parent_meta is None:
            return False
        if parent_meta.stable_id == ancestor_stable_id:
            return True
        current_nid = parent_nid
    return False


def validate_sidecar_nested_batch(
    operations: List[Dict[str, Any]],
    tree_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Validate that no ancestor-descendant pairs exist in the batch.

    For sidecar group only. Checks every pair of node_ids in the batch.
    If any node is an ancestor of another, rejects the entire batch.

    Args:
        operations: List of edit operation dicts with parent_node_id.
        tree_id: In-memory CST tree UUID for ancestor resolution.

    Returns:
        None when batch is valid;
        error dict with NESTED_BATCH_FORBIDDEN when invalid.
    """
    node_ids: List[str] = []
    for op in operations:
        for field in (
            "node_id",
            "parent_node_id",
            "target_node_id",
            "start_node_id",
            "end_node_id",
        ):
            raw = op.get(field)
            if (
                isinstance(raw, str)
                and raw
                and raw != ROOT_NODE_ID_SENTINEL
                and ":" not in raw
            ):
                node_ids.append(raw)
    if len(node_ids) < 2 or tree_id is None:
        return None
    tree = get_tree(tree_id)
    if tree is None:
        return None
    for i, nid_a in enumerate(node_ids):
        for nid_b in node_ids[i + 1 :]:
            if _is_ancestor(tree, nid_a, nid_b) or _is_ancestor(tree, nid_b, nid_a):
                return cast(
                    Dict[str, Any],
                    make_error(
                        NESTED_BATCH_FORBIDDEN,
                        "Ancestor-descendant pair in batch",
                    ),
                )
    return None


def _run_valid_session_sidecar_batch(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply sidecar ops via G-004 EditOperation dispatch on the session tree."""
    from ai_editor.core.backup_manager import BackupManager
    from ai_editor.tree.edit_operations import EditOperationError

    try:
        bm = BackupManager(root_dir=session.core.project_root)
        bm.create_backup(
            session.core.session_source_path, command="universal_file_edit"
        )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            "WRITE_FAILED",
            {"path": str(session.core.session_source_path)},
        )

    snapshot = session.core.session_tree_path.read_text(encoding="utf-8")
    source_snapshot = session.core.session_source_path.read_text(encoding="utf-8")

    def _rollback() -> None:
        session.core.session_tree_path.write_text(snapshot, encoding="utf-8")
        session.core.session_source_path.write_text(source_snapshot, encoding="utf-8")

    try:
        apply_command_ops_on_session_tree(session.core, operations)
    except EditOperationError as exc:
        _rollback()
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"operations": operations},
        )
    except Exception as exc:
        _rollback()
        return error_result_for_edit(
            str(exc),
            "WRITE_FAILED",
            {"path": str(session.core.session_tree_path)},
        )

    session.draft_path = session.core.session_source_path
    session.dirty = True
    return SuccessResult(data={"success": True, "updated": True})


def run_sidecar_cst_edit_batch(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply sidecar CST operations synchronously (for asyncio.to_thread)."""
    uses_node = any(
        _operation_uses_node_address(_coalesce_node_ref_keys(op)) for op in operations
    )
    ops_for_cst = operations
    if session_has_map_tree(session.core) and uses_node:
        if sidecar_ops_use_unified_tree(session.core, operations):
            return _run_valid_session_sidecar_batch(session, operations)
        translated, ok = _translate_sidecar_preview_short_ids(session, operations)
        if not ok:
            m = _coalesce_node_ref_keys(operations[0])
            return error_result_for_edit(
                "One or more node_ref values could not be resolved in the session tree.",
                UNKNOWN_NODE_REF,
                {
                    "operations": operations,
                    "node_ref": m.get("node_ref") or m.get("node_id"),
                    "target_node_id": m.get("target_node_id"),
                },
            )
        ops_for_cst = translated
    elif session_has_map_tree(session.core) and sidecar_ops_use_unified_tree(
        session.core, operations
    ):
        return _run_valid_session_sidecar_batch(session, operations)
    else:
        ops_to_expand = operations
        translated, ok = _translate_sidecar_preview_short_ids(session, operations)
        if uses_node and not ok:
            m = _coalesce_node_ref_keys(operations[0])
            return error_result_for_edit(
                "One or more node_ref values could not be resolved in the session tree.",
                UNKNOWN_NODE_REF,
                {
                    "operations": operations,
                    "node_ref": m.get("node_ref") or m.get("node_id"),
                    "target_node_id": m.get("target_node_id"),
                },
            )
        if ok:
            ops_to_expand = translated
        expanded = _expand_cst_move_operations(session, ops_to_expand)
        if isinstance(expanded, (SuccessResult, ErrorResult)):
            return expanded
        ops_for_cst = expanded

    def _rollback_sidecar_session(
        tree_id: str,
        code: str,
        metadata_snapshot: Dict[str, Any],
    ) -> None:
        rollback_tree_to_code(
            tree_id,
            code,
            index_metadata_for_code=metadata_snapshot,
        )
        session.tree_id = tree_id
        restored = get_tree(tree_id)
        if restored is not None:
            write_sidecar_atomic(_edit_source_path(session), restored)

    tid = session.tree_id
    tree = get_tree(tid) if tid else None
    if tree is None:
        try:
            tree = load_file_to_tree(str(_edit_source_path(session)))
        except FileNotFoundError as exc:
            return error_result_for_edit(
                str(exc),
                "FILE_NOT_FOUND",
                {"path": str(_edit_source_path(session))},
            )
        except Exception as exc:
            return error_result_for_edit(
                str(exc),
                PARSE_ERROR,
                {"path": str(_edit_source_path(session))},
            )
    session.tree_id = tree.tree_id

    batch_original_code = logical_source_from_module(tree.module)
    batch_original_tree_id = tree.tree_id
    batch_original_metadata = dict(tree.metadata_map)

    def _rollback_and_fail(err: ErrorResult) -> ErrorResult:
        _rollback_sidecar_session(
            batch_original_tree_id,
            batch_original_code,
            batch_original_metadata,
        )
        return err

    for op in ops_for_cst:
        try:
            resolved_op = _resolve_stable_to_span(op, tree)
        except StaleNodeIdError as _stale:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(_stale),
                    "STALE_NODE_ID",
                    {
                        "field": _stale.field,
                        "stable_id": _stale.stable_id,
                        "hint": (
                            "stable_id was lost from metadata (unexpected). "
                            "Re-call universal_file_preview with session_id."
                        ),
                    },
                )
            )
        try:
            normalized_op = _normalized_cst_modify_operation(resolved_op)
        except ValueError as exc:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(exc),
                    "INVALID_OPERATION",
                    {"operation": op},
                )
            )
        built, err = build_tree_operations(tree, [normalized_op])
        if err is not None:
            return _rollback_and_fail(err)
        if not built:
            return _rollback_and_fail(
                error_result_for_edit(
                    "No operations built from edit payload",
                    "INVALID_OPERATION",
                    {"operation": normalized_op},
                )
            )
        try:
            tree = modify_tree(tree.tree_id, built)
        except ValueError as exc:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(exc),
                    "INVALID_OPERATION",
                    {"operation": op},
                )
            )
        session.tree_id = tree.tree_id
        try:
            sidecar_path = write_sidecar_atomic(_edit_source_path(session), tree)
        except Exception as exc:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(exc),
                    "WRITE_FAILED",
                    {"path": str(_edit_source_path(session))},
                )
            )

    from ai_editor.commands.universal_file_edit.session import (
        apply_cst_sidecar_mutation,
    )

    code = logical_source_from_module(tree.module)
    apply_cst_sidecar_mutation(session, code, sidecar_abs=sidecar_path)
    session.tree_id = tree.tree_id

    return SuccessResult(data={"success": True, "updated": True})
