"""
Preview diff and commit persistence for tree-temp TreeNode edit sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Tuple, cast

import yaml

if TYPE_CHECKING:
    from ai_editor.commands.universal_file_edit.session import EditSession

from ai_editor.commands.universal_file_edit.format_group import FORMAT_TREE_TEMP
from ai_editor.commands.universal_file_edit.tree_temp_edit_nodes import (
    serialize_tree_temp_roots,
)
from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.edit_session import SessionTreeValidity
from ai_editor.core.file_handlers.diff_support import unified_diff_text
from ai_editor.core.tree_lifecycle.builder import TreeBuilder
from ai_editor.tree.sibling_convention import sibling_tree_path


def serialize_tree_temp_session_source(session: "EditSession") -> str:
    """Return canonical serialized source text for a tree-temp session (handlers json/yaml)."""
    if session.format_group != FORMAT_TREE_TEMP:
        raise ValueError(
            "serialize_tree_temp_session_source requires tree-temp format_group",
        )
    if session.core.tree_validity == SessionTreeValidity.VALID:
        return session.core.session_source_path.read_text(encoding="utf-8")
    if session.tree_temp_roots is not None:
        return cast(
            str,
            serialize_tree_temp_roots(
                session.handler_id,
                session.tree_temp_roots,
            ),
        )
    if session.handler_id == "json":
        from ai_editor.core.json_tree.tree_builder import (
            get_tree as get_json_tree,
        )

        jtree = get_json_tree(session.tree_id) if session.tree_id else None
        if jtree is None:
            return str(session.draft_path.read_text(encoding="utf-8"))
        return str(
            json.dumps(jtree.root_data, indent=2, ensure_ascii=False) + "\n",
        )
    from ai_editor.core.yaml_tree.tree_builder import (
        get_tree as get_yaml_tree,
    )

    ytree = get_yaml_tree(session.tree_id) if session.tree_id else None
    if ytree is None:
        return str(session.draft_path.read_text(encoding="utf-8"))
    return str(
        yaml.safe_dump(
            ytree.root_data,
            sort_keys=False,
            allow_unicode=True,
        )
    )


def build_tree_temp_preview_text(*, abs_path: Path, session: "EditSession") -> str:
    """Return canonical source text for current session tree via SourceSerializer."""
    if session.abs_path.resolve() != abs_path.resolve():
        raise ValueError("abs_path does not match session.abs_path")
    return serialize_tree_temp_session_source(session)


def commit_tree_temp_to_disk(
    *,
    session: "EditSession",
    project_id: str,
    bm: BackupManager,
    rel_str: str,
) -> Tuple[str, str]:
    """Write tree-temp source and optional sidecar; update session checksum and flags.

    Returns:
        Tuple of ``(new_source_sha256_hex, unified_diff_str)``.
    Raises:
        ValueError if serialization fails.
        OSError on I/O failures (caller may restore from backup ``rel_str``).
    """
    original_content = session.abs_path.read_text(encoding="utf-8")
    try:
        code = serialize_tree_temp_session_source(session)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Tree-temp source serialization failed: {exc}") from exc

    from ai_editor.commands.universal_file_edit.edit_draft_path_utils import (
        project_root_near,
    )
    from ai_editor.core.file_validation.pre_write_pipeline import (
        promote_temp_to_target,
    )
    from ai_editor.commands.universal_file_edit.write_command_phases import (
        validate_draft_in_project_context,
    )

    project_root = session.core.project_root
    if project_root is None:
        try:
            project_root = project_root_near(session.abs_path)
        except ValueError:
            project_root = None

    outcome = validate_draft_in_project_context(
        session.handler_id,
        source_code=code,
        target_path=session.abs_path,
        project_root=project_root,
    )
    if not outcome.success:
        raise ValueError(outcome.error_message or "Pre-write validation failed")

    tmp_path: str | None = None
    try:
        if outcome.temp_path is None:
            raise ValueError("Validation succeeded but temp file is missing")
        tmp_path = str(outcome.temp_path)
        promote_temp_to_target(outcome.temp_path, session.abs_path)
        tmp_path = None
    except OSError:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        bm.restore_file(rel_str)
        raise

    final_bytes = session.abs_path.read_bytes()
    sha256_hex = hashlib.sha256(final_bytes).hexdigest()
    session.source_sha256_at_open = sha256_hex
    session.dirty = False

    if session.tree_temp_roots is not None:
        sidecar_path = sibling_tree_path(session.abs_path.resolve())
        try:
            if sidecar_path.exists():
                bm.create_backup(
                    sidecar_path,
                    command="universal_file_write",
                )
            TreeBuilder.build(
                content=code,
                source_abs=session.abs_path.resolve(),
                file_path=session.file_path,
                content_checksum=sha256_hex,
            )
        except OSError:
            bm.restore_file(rel_str)
            raise
        except Exception as exc:
            bm.restore_file(rel_str)
            raise ValueError(
                f"Tree-temp sidecar serialization failed: {exc}",
            ) from exc

    session.sidecar_write_intent = "none"

    diff = unified_diff_text(
        original_content,
        code,
        before_label=str(session.abs_path),
        after_label=str(session.abs_path),
    )
    return sha256_hex, diff
