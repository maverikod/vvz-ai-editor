"""
Legacy JSON/YAML tree-temp universal edit apply (registered-tree pointer ops).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, cast

import json as _json

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.edit_draft_path_utils import (
    project_root_near,
)
from ai_editor.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    UNKNOWN_FORMAT,
    WRITE_FAILED,
    error_result_for_edit,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.json_tree.models import JSONTree
from ai_editor.core.json_tree.tree_modifier import modify_tree as json_modify_tree
from ai_editor.core.json_tree.tree_modifier import (
    _op_delete,
    _op_insert,
    _op_replace,
)
from ai_editor.core.json_tree.tree_builder import get_tree as json_get_registered
from ai_editor.core.yaml_tree.tree_builder import _build_index as yaml_rebuild_index
from ai_editor.core.yaml_tree.tree_builder import get_tree as yaml_get_tree


def _normalized_json_modify_operation(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal-edit op keys into ``core.json_tree.tree_modifier`` shape."""
    m = dict(op)
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
                m["value"] = _json.loads(cnt)
            except _json.JSONDecodeError:
                m["value"] = cnt
        else:
            m["value"] = cnt
    return m


def _modify_yaml_registered_one(tree_id: str, mop: Dict[str, Any]) -> None:
    """Apply one JSON-shaped modify dict to YAML tree and rebuild its index."""

    tree = yaml_get_tree(tree_id)
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


def run_tree_temp_legacy_json_yaml_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply tree-temp group operations via JSON/YAML pipelines (registered tree)."""

    tid = session.tree_id
    if not tid:
        return error_result_for_edit(
            "Session has no registered tree id for tree-temp format.",
            "INVALID_SESSION",
            None,
        )
    try:
        root_dir = session.core.project_root or project_root_near(session.draft_path)
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
                dump = _json.dumps(jt.root_data, indent=2, ensure_ascii=False) + "\n"
                session.draft_path.write_text(
                    dump,
                    encoding="utf-8",
                )
        elif session.handler_id == "yaml":
            import yaml

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
