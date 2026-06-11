"""Apply universal_file_edit operations to TreeNode-backed tree-temp sessions (G-003 / G-004).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, cast

import yaml
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    UNKNOWN_FORMAT,
    WRITE_FAILED,
    error_result_for_edit,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import FORMAT_TREE_TEMP
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    apply_source_mutation,
    apply_tree_operation,
)
from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    apply_single_tree_temp_mutation,
    serialize_tree_temp_roots,
)
from ai_editor.commands.universal_file_edit.insert_position import (
    coalesce_tree_temp_insert_position,
    parse_colon_position,
)
from ai_editor.core.edit_session import SessionTreeValidity
from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.edit_session.edit_operations_adapter import (
    _coalesce_node_ref_keys,
    _node_at_json_pointer,
    _parse_marked_tree_root,
    _resolve_pointer_to_short_id,
    _wrapper_short_id,
    command_op_to_edit_operation,
    resolve_node_ref_to_short_id,
)
from ai_editor.core.json_tree.json_pointer import set_value_at
from ai_editor.core.tree_lifecycle.node_id_map import parse_tree_file
from ai_editor.tree.contracts import NodeId
from ai_editor.tree.edit_operations import EditOperation, EditOperationKind
from ai_editor.core.json_tree.tree_builder import get_tree as json_get_registered
from ai_editor.core.json_tree.tree_modifier import modify_tree as json_modify_tree
from ai_editor.core.yaml_tree.tree_builder import get_tree as yaml_get_tree

_JSON_ID_KEY = "___id___"
_JSON_VAL_KEY = "v"


def _require_integer_short_id(raw: Any, field_name: str) -> int:
    if isinstance(raw, bool):
        raise ValueError(f"{field_name} must be integer short_id, got {raw!r}")
    if isinstance(raw, int):
        if raw < 1:
            raise ValueError(f"{field_name} must be integer short_id, got {raw!r}")
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        sid = int(raw.strip())
        if sid < 1:
            raise ValueError(f"{field_name} must be integer short_id, got {raw!r}")
        return sid
    raise ValueError(f"{field_name} must be integer short_id, got {raw!r}")


def _optional_integer_short_id(raw: Any, field_name: str) -> int | None:
    if raw is None or raw == "":
        return None
    return _require_integer_short_id(raw, field_name)


def _session_tree_sections(session: EditSession) -> Any:
    tree_text = session.core.session_tree_path.read_text(encoding="utf-8")
    return parse_tree_file(tree_text)


def _session_marked_root(session: EditSession) -> Any:
    sections = _session_tree_sections(session)
    return _parse_marked_tree_root(sections, session.handler_id)


def _json_object_entry_short_id(obj_node: dict[str, Any], key: str) -> int:
    if _JSON_VAL_KEY in obj_node:
        inner = obj_node[_JSON_VAL_KEY]
        if not isinstance(inner, dict) or key not in inner:
            raise ValueError(f"object has no key {key!r}")
        return cast(int, _wrapper_short_id(inner[key]))
    if key not in obj_node:
        raise ValueError(f"object has no key {key!r}")
    return cast(int, _wrapper_short_id(obj_node[key]))


def _resolve_json_target_short_id(session: EditSession, mop: Dict[str, Any]) -> int:
    sections = _session_tree_sections(session)
    for field in ("node_ref", "node_id", "target_node_id"):
        raw = mop.get(field)
        if raw is None or raw == "":
            continue
        sid = _optional_integer_short_id(raw, field)
        if sid is not None:
            return sid
        return cast(
            int,
            resolve_node_ref_to_short_id(
                raw,
                sections,
                source_abs=session.core.source_abs,
                unmarked_source=session.core.session_source_path.read_text(
                    encoding="utf-8"
                ),
                handler_id=session.handler_id,
            ),
        )
    if "json_pointer" in mop:
        return cast(
            int,
            _resolve_pointer_to_short_id(
                str(mop["json_pointer"]), sections, session.handler_id
            ),
        )
    raise ValueError(
        "valid-mode edit requires integer node_ref short_id or json_pointer target"
    )


def _serialize_insert_value(handler_id: str, value: Any) -> str:
    if handler_id == "json":
        return json.dumps(value, ensure_ascii=False)
    if handler_id == "yaml":
        dumped: str = cast(
            str,
            yaml.safe_dump(
                value,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
        )
        return dumped
    raise ValueError(f"Unsupported handler for tree-temp: {handler_id!r}")


def _resolve_optional_anchor_short_id(
    session: EditSession, raw: Any, field_name: str
) -> int | None:
    if raw is None or raw == "":
        return None
    sid = _optional_integer_short_id(raw, field_name)
    if sid is not None:
        return sid
    sections = _session_tree_sections(session)
    return cast(
        int,
        resolve_node_ref_to_short_id(
            raw,
            sections,
            source_abs=session.core.source_abs,
            unmarked_source=session.core.session_source_path.read_text(
                encoding="utf-8"
            ),
            handler_id=session.handler_id,
        ),
    )


def _resolve_json_insert_anchor_and_position(
    session: EditSession,
    mop: Dict[str, Any],
) -> tuple[int, str]:
    sections = _session_tree_sections(session)
    target_raw = mop.get("target_node_id")
    if target_raw not in (None, ""):
        position = str(mop.get("position") or "after").strip().lower()
        parsed = parse_colon_position(mop.get("position"))
        if parsed is not None:
            position, target_raw = parsed[0], parsed[1]
        if position not in ("before", "after"):
            raise ValueError(
                "target_node_id insert requires position 'before' or 'after', "
                f"got {position!r}"
            )
        sid = _resolve_optional_anchor_short_id(session, target_raw, "target_node_id")
        if sid is None:
            raise ValueError("target_node_id could not be resolved to short_id")
        return sid, position

    node_ref = mop.get("node_id") or mop.get("node_ref")
    position_raw = mop.get("position")
    parsed = parse_colon_position(position_raw)
    if parsed is not None and node_ref in (None, ""):
        side, addr = parsed
        sid = _resolve_optional_anchor_short_id(session, addr, "node_ref")
        if sid is None:
            raise ValueError("node_ref could not be resolved to short_id")
        return sid, side
    pos_norm = str(position_raw or "").strip().lower()
    if (
        node_ref not in (None, "")
        and pos_norm in ("before", "after")
        and mop.get("parent_json_pointer") in (None, "")
    ):
        sid = _resolve_optional_anchor_short_id(session, node_ref, "node_ref")
        if sid is None:
            raise ValueError("node_ref could not be resolved to short_id")
        return sid, pos_norm

    before_ptr = mop.get("before_json_pointer")
    after_ptr = mop.get("after_json_pointer")
    if before_ptr is not None and after_ptr is not None:
        raise ValueError(
            "before_json_pointer and after_json_pointer are mutually exclusive"
        )
    if before_ptr is not None:
        return (
            _resolve_pointer_to_short_id(str(before_ptr), sections, session.handler_id),
            "before",
        )
    if after_ptr is not None:
        return (
            _resolve_pointer_to_short_id(str(after_ptr), sections, session.handler_id),
            "after",
        )

    before_sid = _resolve_optional_anchor_short_id(
        session, mop.get("before_node_id"), "before_node_id"
    )
    after_sid = _resolve_optional_anchor_short_id(
        session, mop.get("after_node_id"), "after_node_id"
    )
    if before_sid is not None and after_sid is not None:
        raise ValueError("before_node_id and after_node_id are mutually exclusive")
    if before_sid is not None:
        return before_sid, "before"
    if after_sid is not None:
        return after_sid, "after"

    parent_ptr = str(mop.get("parent_json_pointer", ""))
    root = _session_marked_root(session)
    parent_node = _node_at_json_pointer(root, parent_ptr) if parent_ptr else root

    before_key = mop.get("before_key")
    after_key = mop.get("after_key")
    if before_key is not None and after_key is not None:
        raise ValueError("before_key and after_key are mutually exclusive")
    if isinstance(before_key, str):
        return _json_object_entry_short_id(parent_node, before_key), "before"
    if isinstance(after_key, str):
        return _json_object_entry_short_id(parent_node, after_key), "after"

    idx_raw = mop.get("index")
    if idx_raw is not None:
        try:
            idx = int(idx_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("index must be integer") from exc
        arr: list[Any] | None = None
        if isinstance(parent_node, list):
            arr = parent_node
        elif isinstance(parent_node, dict) and _JSON_VAL_KEY in parent_node:
            inner = parent_node[_JSON_VAL_KEY]
            if isinstance(inner, list):
                arr = inner
        if arr is None:
            raise ValueError("index requires array parent_json_pointer")
        if not arr:
            raise ValueError("cannot insert at index into empty array")
        if idx <= 0:
            return _wrapper_short_id(arr[0]), "before"
        if idx >= len(arr):
            return _wrapper_short_id(arr[-1]), "after"
        return _wrapper_short_id(arr[idx]), "before"

    insert_position = mop.get("position")
    if insert_position in (None, "last"):
        if isinstance(parent_node, list):
            if not parent_node:
                raise ValueError("cannot append to empty array without index")
            return _wrapper_short_id(parent_node[-1]), "after"
        inner = parent_node.get(_JSON_VAL_KEY)
        if isinstance(inner, list):
            if not inner:
                raise ValueError("cannot append to empty array without index")
            return _wrapper_short_id(inner[-1]), "after"
        return _wrapper_short_id(parent_node), "last_child"
    if insert_position == "first":
        if isinstance(parent_node, list):
            if not parent_node:
                raise ValueError("cannot prepend to empty array without index")
            return _wrapper_short_id(parent_node[0]), "before"
        inner = parent_node.get(_JSON_VAL_KEY)
        if isinstance(inner, list):
            if not inner:
                raise ValueError("cannot prepend to empty array without index")
            return _wrapper_short_id(inner[0]), "before"
        return _wrapper_short_id(parent_node), "first_child"
    raise ValueError(
        "insert requires integer anchor short_id, json_pointer parent, or sibling keys"
    )


def _tree_temp_op_to_edit_operation(
    session: EditSession,
    mop: Dict[str, Any],
    handler_id: str,
) -> EditOperation:
    action = str(mop.get("action") or mop.get("type") or "").lower()
    if action == "replace":
        if "value" not in mop and "content" not in mop:
            raise ValueError("replace requires value")
        value = mop["value"] if "value" in mop else mop["content"]
        return EditOperation(
            kind=EditOperationKind.REPLACE,
            short_id=NodeId(_resolve_json_target_short_id(session, mop)),
            new_content=_serialize_insert_value(handler_id, value),
        )
    if action == "delete":
        return EditOperation(
            kind=EditOperationKind.DELETE,
            short_id=NodeId(_resolve_json_target_short_id(session, mop)),
        )
    if action == "insert":
        if "value" not in mop:
            raise ValueError("insert requires value")
        anchor_sid, position = _resolve_json_insert_anchor_and_position(session, mop)
        insert_value: Any = mop["value"]
        key = mop.get("key")
        if isinstance(key, str) and key:
            insert_value = {key: insert_value}
        return EditOperation(
            kind=EditOperationKind.INSERT,
            anchor_short_id=NodeId(anchor_sid),
            position=position,
            new_content=_serialize_insert_value(handler_id, insert_value),
        )
    if action == "move":
        sections = _session_tree_sections(session)
        m = _coalesce_node_ref_keys(dict(mop))
        if m.get("json_pointer") and not m.get("node_id") and not m.get("node_ref"):
            m["node_id"] = str(
                _resolve_pointer_to_short_id(
                    str(m["json_pointer"]), sections, session.handler_id
                )
            )
        elif not m.get("node_id") and not m.get("node_ref"):
            m["node_id"] = str(_resolve_json_target_short_id(session, m))
        return command_op_to_edit_operation(m, sections, session.core)
    raise ValueError(f"Unknown tree-temp action: {action!r}")


def _apply_source_pointer_set(session: EditSession, pointer: str, value: Any) -> None:
    """Set a JSON-pointer path on unmarked draft source and rebuild the session tree."""
    path = session.core.session_source_path
    text = path.read_text(encoding="utf-8")
    if session.handler_id == "yaml":
        data = yaml.safe_load(text)
        if data is None:
            data = {}
        set_value_at(data, pointer, value)
        _dumped = yaml.safe_dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        new_text: str = cast(str, _dumped)
    else:
        data = json.loads(text)
        set_value_at(data, pointer, value)
        new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    apply_source_mutation(session, new_text)


def _expand_list_pointer_replace(
    session: EditSession, mop: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Route replace-at-list-pointer through unmarked source when marked target is a bare list."""
    action = str(mop.get("action") or mop.get("type") or "").lower()
    if action != "replace" or "json_pointer" not in mop:
        return [mop]
    ptr = str(mop["json_pointer"])
    root = _session_marked_root(session)
    try:
        target = _node_at_json_pointer(root, ptr)
    except ValueError:
        return [mop]
    if not isinstance(target, list):
        return [mop]
    return [
        {
            "__source_pointer_set__": ptr,
            "value": mop.get("value"),
        }
    ]


def _apply_valid_tree_temp_mutations(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    try:
        for op in operations:
            for sub in _expand_list_pointer_replace(
                session, _normalized_json_modify_operation(op)
            ):
                ptr_set = sub.get("__source_pointer_set__")
                if isinstance(ptr_set, str):
                    _apply_source_pointer_set(session, ptr_set, sub.get("value"))
                    continue
                edit_op = _tree_temp_op_to_edit_operation(
                    session,
                    sub,
                    session.handler_id,
                )
                apply_tree_operation(session, edit_op)
    except ValueError as exc:
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"operations": operations},
        )
    return SuccessResult(data={"success": True, "updated": True})


def _project_root_near(path: Path) -> Path:
    """Locate project-like root upward from ``path`` for backups."""
    resolved = path.resolve()
    probe = resolved.parent if resolved.is_file() else resolved
    for candidate in (probe,) + tuple(probe.parents):
        if (candidate / "pyproject.toml").exists() or (
            candidate / "projectid"
        ).exists():
            return candidate
    raise ValueError(f"Cannot resolve project root near {resolved}")


def _normalized_json_modify_operation(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal-edit op keys into ``core.json_tree.tree_modifier`` shape."""
    m = dict(op)
    coalesce_tree_temp_insert_position(m)
    if "json_pointer" not in m and "node_ref" in m:
        ref = m.get("node_ref")
        if ref == "" or (isinstance(ref, str) and ref.startswith("/")):
            m["json_pointer"] = ref
    for ref_key, id_key in (
        ("node_ref", "node_id"),
        ("parent_node_ref", "parent_node_id"),
        ("target_node_ref", "target_node_id"),
    ):
        if ref_key in m and not m.get(id_key):
            m[id_key] = m[ref_key]
    raw_action = op.get("action")
    raw_type = op.get("type")
    if isinstance(raw_action, str) and raw_action.strip():
        m["action"] = raw_action.strip().lower()
    elif isinstance(raw_type, str) and raw_type.strip():
        m["action"] = raw_type.strip().lower()
    if "value" not in m and "content" in m:
        cnt = m.get("content")
        if isinstance(cnt, str):
            try:
                m["value"] = json.loads(cnt)
            except json.JSONDecodeError:
                m["value"] = cnt
        else:
            m["value"] = cnt
    return m


def _modify_yaml_registered_one(tree_id: str, mop: Dict[str, Any]) -> None:
    """Apply one JSON-shaped modify dict to YAML tree and rebuild its index."""

    from ai_editor.core.json_tree.models import JSONTree
    from ai_editor.core.json_tree.tree_modifier import (
        _op_delete,
        _op_insert,
        _op_replace,
    )
    from ai_editor.core.yaml_tree.tree_builder import (
        _build_index as yaml_rebuild_index,
        get_tree as yaml_get_registered_inner,
    )

    tree = yaml_get_registered_inner(tree_id)
    if tree is None:
        raise ValueError(f"YAML tree not found: {tree_id}")
    act = str(mop.get("action") or "").lower()
    jtree = cast(JSONTree, tree)
    if act == "replace":
        _op_replace(jtree, mop)
    elif act == "delete":
        _op_delete(jtree, mop)
    elif act == "insert":
        _op_insert(jtree, mop)
    else:
        raise ValueError(f"Unknown YAML tree action: {act!r}")
    yaml_rebuild_index(tree)


def _run_legacy_tree_temp_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    tid = session.tree_id
    if not tid:
        return error_result_for_edit(
            "Session has no registered tree id for tree-temp format.",
            "INVALID_SESSION",
            None,
        )
    try:
        root_dir = _project_root_near(session.draft_path)
        bm = BackupManager(root_dir=root_dir)
        if session.draft_path.exists():
            bm.create_backup(
                session.draft_path,
                command="universal_file_edit",
            )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.draft_path)},
        )

    try:
        if session.handler_id == "json":
            for op in operations:
                mop = _normalized_json_modify_operation(op)
                json_modify_tree(tid, [mop])
                jt = json_get_registered(tid)
                if jt is None:
                    return error_result_for_edit(
                        f"JSON tree not found after apply: {tid}",
                        PARSE_ERROR,
                        None,
                    )
                dump = json.dumps(jt.root_data, indent=2, ensure_ascii=False) + "\n"
                session.draft_path.write_text(
                    dump,
                    encoding="utf-8",
                )
        elif session.handler_id == "yaml":
            for op in operations:
                mop = _normalized_json_modify_operation(op)
                _modify_yaml_registered_one(tid, mop)
                yt = yaml_get_tree(tid)
                if yt is None:
                    return error_result_for_edit(
                        f"YAML tree not found after apply: {tid}",
                        PARSE_ERROR,
                        None,
                    )
                session.draft_path.write_text(
                    yaml.safe_dump(
                        yt.root_data,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
        else:
            return error_result_from_make_error(
                cast(
                    Dict[str, Any],
                    make_error(
                        UNKNOWN_FORMAT,
                        f"Unsupported handler for tree-temp: {session.handler_id}",
                    ),
                )
            )
    except ValueError as exc:
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"operations": operations},
        )

    return SuccessResult(data={"success": True, "updated": True})


def apply_tree_temp_mutations(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    if session.format_group != FORMAT_TREE_TEMP:
        return error_result_for_edit(
            "Session format_group is not tree-temp.",
            "INVALID_SESSION",
            None,
        )
    if session.tree_temp_roots is None:
        return _run_legacy_tree_temp_apply(session, operations)

    if session.core.tree_validity == SessionTreeValidity.VALID:
        try:
            root_dir = _project_root_near(session.draft_path)
            bm = BackupManager(root_dir=root_dir)
            if session.draft_path.exists():
                bm.create_backup(
                    session.draft_path,
                    command="universal_file_edit",
                )
        except Exception as exc:
            return error_result_for_edit(
                f"Backup before edit failed: {exc}",
                WRITE_FAILED,
                {"path": str(session.draft_path)},
            )
        return _apply_valid_tree_temp_mutations(session, operations)

    roots_snap = deepcopy(session.tree_temp_roots)

    try:
        root_dir = _project_root_near(session.draft_path)
        bm = BackupManager(root_dir=root_dir)
        if session.draft_path.exists():
            bm.create_backup(
                session.draft_path,
                command="universal_file_edit",
            )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.draft_path)},
        )

    roots = session.tree_temp_roots

    def rollback() -> None:
        session.tree_temp_roots = deepcopy(roots_snap)
        apply_source_mutation(
            session,
            serialize_tree_temp_roots(session.handler_id, session.tree_temp_roots),
        )

    try:
        for op in operations:
            mop = _normalized_json_modify_operation(op)
            try:
                apply_single_tree_temp_mutation(roots, session.handler_id, mop)
            except ValueError as exc:
                rollback()
                return error_result_for_edit(
                    str(exc),
                    "INVALID_OPERATION",
                    {"operations": operations},
                )
        apply_source_mutation(
            session,
            serialize_tree_temp_roots(session.handler_id, roots),
        )
        return SuccessResult(data={"success": True, "updated": True})
    except ValueError as exc:
        rollback()
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"operations": operations},
        )
