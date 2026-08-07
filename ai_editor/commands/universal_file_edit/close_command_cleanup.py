"""
Format-group workspace cleanup for universal_file_close (Close Stage, C-013).

Extracted from ``close_command`` so the command module keeps the close policy
(unsaved-edit refusal, parameter validation, CA unlock, bundle release) and this
module keeps the per-format-group draft/sidecar reconciliation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import EditSession


def close_sidecar(session: EditSession) -> Dict[str, Any]:
    """Close a sidecar group session.

    Verifies the sidecar checksum. On mismatch rebuilds the sidecar from source.
    The sidecar is never deleted.

    Args:
        session: Active sidecar group EditSession.

    Returns:
        Dict with success=True and the draft_rebuilt flag.
    """
    from ai_editor.core.cst_tree import tree_builder as cst_builder
    from ai_editor.core.cst_tree.tree_sidecar import (
        read_sidecar_payload,
        verify_sidecar_against_source,
        write_sidecar_atomic,
    )

    tree = cst_builder.load_file_to_tree(str(session.abs_path))
    payload = read_sidecar_payload(session.abs_path)
    if payload is not None and verify_sidecar_against_source(tree.module.code, payload):
        return {"success": True, "draft_rebuilt": False}
    write_sidecar_atomic(session.abs_path, tree)
    return {"success": True, "draft_rebuilt": True}


def close_tree_temp_or_text(session: EditSession) -> Dict[str, Any]:
    """Close a tree-temp or text group session.

    Args:
        session: Active tree-temp or text group EditSession.

    Returns:
        Dict with success=True and the draft_rebuilt flag.
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
        draft_rebuilt = _rebuild_tree_temp_draft(session, abs_path)

    if session.tree_id:
        if session.handler_id == "json":
            from ai_editor.core.json_tree import tree_builder as json_builder

            json_builder.remove_tree(session.tree_id)
        else:
            from ai_editor.core.yaml_tree import tree_builder as yaml_builder

            yaml_builder.remove_tree(session.tree_id)

    return {"success": True, "draft_rebuilt": draft_rebuilt}


def _rebuild_tree_temp_draft(session: EditSession, abs_path: Any) -> bool:
    """Reconcile a tree-temp draft against the on-disk source.

    Returns:
        True when the draft had to be rebuilt from the on-disk source.
    """
    if not session.draft_path.exists():
        return False
    draft_sha = hashlib.sha256(session.draft_path.read_bytes()).hexdigest()
    orig_sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
    if draft_sha == orig_sha:
        session.draft_path.unlink(missing_ok=True)
        return False
    if session.handler_id == "json":
        import json

        from ai_editor.core.json_tree import tree_builder as json_builder

        loaded_json = json_builder.load_file_to_tree(str(abs_path))
        draft_text = (
            json.dumps(loaded_json.root_data, indent=2, ensure_ascii=False) + "\n"
        )
        session.draft_path.write_text(draft_text, encoding="utf-8")
        json_builder.remove_tree(loaded_json.tree_id)
    else:
        import yaml

        from ai_editor.core.yaml_tree import tree_builder as yaml_builder

        loaded_yaml = yaml_builder.load_file_to_tree(str(abs_path))
        draft_text = yaml.safe_dump(
            loaded_yaml.root_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        session.draft_path.write_text(draft_text, encoding="utf-8")
        yaml_builder.remove_tree(loaded_yaml.tree_id)
    return True
