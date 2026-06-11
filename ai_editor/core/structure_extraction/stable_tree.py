"""
Resolve stable preview-compatible Python CST metadata (persisted sidecar).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ai_editor.core.cst_tree.models import TreeNodeMetadata
from ai_editor.core.cst_tree.tree_sidecar import (
    metadata_map_from_payload,
    read_sidecar_payload,
)
from ai_editor.core.structure_extraction.models import StructureWarning
from ai_editor.tree.sibling_convention import sibling_tree_path


@dataclass
class TreeResolutionStats:
    files_requiring_tree_check: int = 0
    valid_trees_reused: int = 0
    stale_trees_rebuilt: int = 0
    missing_trees_created: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "files_requiring_tree_check": self.files_requiring_tree_check,
            "valid_trees_reused": self.valid_trees_reused,
            "stale_trees_rebuilt": self.stale_trees_rebuilt,
            "missing_trees_created": self.missing_trees_created,
        }


def _metadata_from_sidecar_payload(
    payload: dict,
) -> Optional[Dict[str, TreeNodeMetadata]]:
    meta_blob = payload.get("metadata_map")
    order_raw = payload.get("metadata_node_order")
    order = [str(x) for x in order_raw] if isinstance(order_raw, list) else None
    metadata_map = metadata_map_from_payload(meta_blob, order)
    return metadata_map or None


def _project_root_and_file_path(abs_path: Path) -> tuple[Path, str]:
    resolved = abs_path.resolve()
    return resolved.parent, resolved.name


def _read_sidecar_metadata_map(
    abs_path: Path,
    *,
    allow_cst_index_fallback: bool,
) -> Optional[Dict[str, TreeNodeMetadata]]:
    payload = read_sidecar_payload(abs_path)
    if payload is not None:
        meta = _metadata_from_sidecar_payload(payload)
        if meta:
            return meta
    if not allow_cst_index_fallback:
        return None
    from ai_editor.core.cst_tree.tree_builder import load_file_to_tree, remove_tree

    try:
        tree = load_file_to_tree(str(abs_path))
        meta = dict(tree.metadata_map)
        remove_tree(tree.tree_id)
    except Exception:
        return None
    return meta or None


def _load_sidecar_metadata_readonly(
    abs_path: Path,
) -> Optional[Dict[str, TreeNodeMetadata]]:
    """Return metadata when sidecar checksum matches source; never rebuild."""
    project_root, file_path = _project_root_and_file_path(abs_path)
    try:
        from ai_editor.core.search_session.tree_representation import (
            _read_sidecar_state,
            classify_tree_format,
            sidecar_path_for,
        )
        from ai_editor.core.tree_lifecycle.checksum import (
            compute_content_checksum,
            is_tree_valid,
        )

        resolved = abs_path.resolve()
        if not resolved.is_file():
            return None
        kind = classify_tree_format(file_path)
        content = resolved.read_text(encoding="utf-8")
        content_checksum = compute_content_checksum(content)
        sidecar_path = sidecar_path_for(file_path, project_root)
        if not sidecar_path.is_file():
            return None
        sidecar_digest, _ = _read_sidecar_state(
            kind=kind,
            source_abs=resolved,
            sidecar_path=sidecar_path,
        )
        if not is_tree_valid(content_checksum, sidecar_digest):
            return None
    except (FileNotFoundError, ValueError, OSError, NotImplementedError):
        return None
    return _read_sidecar_metadata_map(abs_path, allow_cst_index_fallback=False)


def _metadata_from_edit_session(
    session_id: str,
    abs_path: Path,
) -> Optional[Dict[str, TreeNodeMetadata]]:
    from ai_editor.commands.universal_file_edit.format_group import FORMAT_SIDECAR
    from ai_editor.commands.universal_file_edit.session import get_session
    from ai_editor.core.cst_tree.tree_builder import get_cst_tree

    try:
        session = get_session(session_id)
    except ValueError:
        return None
    if session.abs_path.resolve() != abs_path.resolve():
        return None
    if session.format_group != FORMAT_SIDECAR or not session.tree_id:
        return None
    tree = get_cst_tree(session.tree_id)
    if tree is None:
        return None
    return dict(tree.metadata_map)


def resolve_python_metadata_stable(
    abs_path: Path,
    content: str,
    *,
    source: str,
    session_id: Optional[str],
    ensure_persisted_tree: bool,
) -> tuple[
    Optional[Dict[str, TreeNodeMetadata]], List[StructureWarning], TreeResolutionStats
]:
    """
    Return metadata_map whose stable_id values match persisted sidecar / preview.

    Never returns ids from ``create_tree_from_code(..., persist_sidecar=False)``.
    """
    _ = content  # checksum policy reads source from disk; callers pass grep text for API symmetry
    stats = TreeResolutionStats(files_requiring_tree_check=1)
    warnings: List[StructureWarning] = []

    if source == "draft_session" and session_id:
        meta = _metadata_from_edit_session(session_id, abs_path)
        if meta:
            stats.valid_trees_reused += 1
            return meta, warnings, stats
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_NOT_PERSISTED",
                message="Draft session tree not available for stable enrichment.",
                file_path=str(abs_path),
            )
        )
        return None, warnings, stats

    if not abs_path.is_file():
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_ENRICHMENT_FAILED",
                message="Python file not on disk; cannot persist stable tree.",
                file_path=str(abs_path),
            )
        )
        return None, warnings, stats

    if not ensure_persisted_tree:
        meta = _load_sidecar_metadata_readonly(abs_path)
        if meta:
            stats.valid_trees_reused += 1
            return meta, warnings, stats
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_NOT_PERSISTED",
                message="Stable tree identity was required but no persisted tree was available.",
                file_path=str(abs_path),
            )
        )
        return None, warnings, stats

    project_root, file_path = _project_root_and_file_path(abs_path)
    had_sidecar = sibling_tree_path(abs_path.resolve()).is_file()
    from ai_editor.core.tree_lifecycle.checksum import (
        validate_or_recreate_tree_file,
    )

    try:
        _tree_ref, validity_state = validate_or_recreate_tree_file(
            project_root=project_root,
            file_path=file_path,
        )
    except (FileNotFoundError, ValueError, OSError, NotImplementedError) as exc:
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_ENRICHMENT_FAILED",
                message=f"Failed to create persisted CST tree: {exc}",
                file_path=str(abs_path),
            )
        )
        return None, warnings, stats

    meta = _read_sidecar_metadata_map(abs_path, allow_cst_index_fallback=True)
    if not meta:
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_ENRICHMENT_FAILED",
                message="Persisted tree has no metadata.",
                file_path=str(abs_path),
            )
        )
        return None, warnings, stats

    from ai_editor.core.search_session.tree_representation import TreeValidityState

    if validity_state == TreeValidityState.reused:
        stats.valid_trees_reused += 1
    elif had_sidecar:
        stats.stale_trees_rebuilt += 1
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_CREATED",
                message="A stale structure tree was rebuilt before enrichment.",
                file_path=str(abs_path),
            )
        )
    else:
        stats.missing_trees_created += 1
        warnings.append(
            StructureWarning(
                code="STRUCTURE_TREE_CREATED",
                message="A missing structure tree was created before enrichment.",
                file_path=str(abs_path),
            )
        )
    return meta, warnings, stats
