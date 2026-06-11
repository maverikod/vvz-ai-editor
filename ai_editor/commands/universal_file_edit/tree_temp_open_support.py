"""Helpers to acquire TreeNode roots for tree-temp universal_file_open (G-003).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple, cast

from ai_editor.commands.universal_file_edit.session import (
    active_session_uses_abs_path,
)
from ai_editor.commands.universal_file_edit.sha_sync_policy import (
    ShaSyncBranch,
    resolve_sha_sync_policy,
)
from ai_editor.core.tree_temp.sidecar_payload import (
    SidecarParseError,
    parse_sidecar_json_bytes,
)
from ai_editor.tree.sibling_convention import sibling_tree_path
from ai_editor.core.tree_temp.tree_node import TreeNode


class SidecarWriteIntent(str, Enum):
    NONE = "none"
    CREATE = "create"
    REPLACE = "replace"


@dataclass(frozen=True)
class TreeTempOpenAcquisition:
    roots: List[TreeNode]
    source_sha256: str
    sidecar_path: Path
    sidecar_write_intent: SidecarWriteIntent


def parse_source_bytes_to_roots(handler_id: str, raw: bytes) -> List[TreeNode]:
    """Parse source bytes into root-level TreeNode list (json/yaml handlers)."""
    if not raw.strip():
        return []
    text = raw.decode("utf-8")
    if handler_id == "json":
        from ai_editor.core.tree_temp.json_source_parser import parse_json_source

        return cast(List[TreeNode], parse_json_source(text))
    if handler_id == "yaml":
        from ai_editor.core.tree_temp.yaml_source_parser import parse_yaml_source

        return cast(List[TreeNode], parse_yaml_source(text))
    raise ValueError(f"unsupported tree-temp handler_id: {handler_id!r}")


def _read_trees_sidecar_optional(
    sidecar_path: Path,
) -> Optional[Tuple[str, List[TreeNode]]]:
    if not sidecar_path.exists():
        return None
    try:
        raw = sidecar_path.read_bytes()
        return cast(Tuple[str, List[TreeNode]], parse_sidecar_json_bytes(raw))
    except SidecarParseError:
        return None


def acquire_tree_temp_for_open(
    *,
    project_root: Path,
    source_abs: Path,
    handler_id: str,
    raw_source_bytes: bytes,
    workspace_origin_path: Optional[Path] = None,
    workspace_edit_root: Optional[Path] = None,
) -> TreeTempOpenAcquisition:
    """Compute SHA, run SHASyncPolicy, return roots + staging intent; workspace mode reads sidecar beside origin snapshot."""
    current_sha = hashlib.sha256(raw_source_bytes).hexdigest()

    _ws_pair = (workspace_origin_path, workspace_edit_root)
    if any(p is not None for p in _ws_pair) and not all(
        p is not None for p in _ws_pair
    ):
        raise ValueError(
            "workspace_origin_path and workspace_edit_root must be provided together"
        )
    workspace_mode = all(p is not None for p in _ws_pair)

    if workspace_mode:
        assert workspace_origin_path is not None
        assert workspace_edit_root is not None
        origin_resolved = workspace_origin_path.resolve()
        edit_resolved = workspace_edit_root.resolve()
        edit_source_path = edit_resolved / origin_resolved.name
        read_sidecar_path = sibling_tree_path(origin_resolved)
        write_sidecar_path = sibling_tree_path(edit_source_path)
        active_session_path = origin_resolved
    else:
        read_sidecar_path = sibling_tree_path(source_abs.resolve())
        write_sidecar_path = read_sidecar_path
        active_session_path = source_abs.resolve()

    loaded = _read_trees_sidecar_optional(read_sidecar_path)
    sidecar_exists = loaded is not None
    sidecar_sha = loaded[0] if loaded else None
    decision = resolve_sha_sync_policy(
        sidecar_exists=sidecar_exists,
        sidecar_source_sha256=sidecar_sha,
        current_source_sha256=current_sha,
        active_session_holds_file=active_session_uses_abs_path(active_session_path),
    )
    branch = decision.branch

    if branch == ShaSyncBranch.NO_SIDECAR:
        roots = parse_source_bytes_to_roots(handler_id, raw_source_bytes)
        intent = SidecarWriteIntent.CREATE
    elif branch == ShaSyncBranch.SHA_MATCH:
        if loaded is None:
            raise ValueError("SHA_MATCH branch requires a valid loaded sidecar")
        roots = deepcopy(loaded[1])
        intent = SidecarWriteIntent.NONE
    elif branch == ShaSyncBranch.SHA_MISMATCH_NO_SESSION:
        roots = parse_source_bytes_to_roots(handler_id, raw_source_bytes)
        intent = SidecarWriteIntent.REPLACE
    elif branch == ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION:
        if loaded is None:
            raise ValueError(
                "SHA_MISMATCH_ACTIVE_SESSION branch requires a valid loaded sidecar"
            )
        roots = deepcopy(loaded[1])
        intent = SidecarWriteIntent.NONE
    else:
        raise ValueError(f"unexpected ShaSyncBranch: {branch!r}")

    if raw_source_bytes.strip() and not roots:
        raise ValueError("parser returned empty roots for non-empty source document")

    return TreeTempOpenAcquisition(
        roots=roots,
        source_sha256=current_sha,
        sidecar_path=write_sidecar_path,
        sidecar_write_intent=intent,
    )
