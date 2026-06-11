"""
TreeLifecycle (C-010): named entity layer over the checksum core.

Single entry point coordinating tree validity and creation. Delegates to
checksum.py helpers; unified rebuild wiring lives in checksum validate path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from ai_editor.core.search_session.tree_representation import (
    TreeFormatKind,
    TreeRepresentationRef,
    TreeValidityState,
)
from ai_editor.core.tree_lifecycle.checksum import (
    ChecksumSyncPolicy,
    validate_or_recreate_from_content,
    validate_or_recreate_tree_file,
)


class TreeLifecycle:
    """TreeLifecycle (C-010): single entry point for tree validity and creation."""

    policy: type[ChecksumSyncPolicy] = ChecksumSyncPolicy

    class _LazyBuilder:
        """Defer TreeBuilder import until first access (parallel A-001)."""

        _cached: type | None = None

        def __get__(self, obj: object | None, owner: type) -> type:
            if self._cached is None:
                from ai_editor.core.tree_lifecycle.builder import TreeBuilder

                self._cached = TreeBuilder
            return self._cached

    builder = _LazyBuilder()

    @staticmethod
    def from_content(
        *,
        kind: TreeFormatKind,
        content: str,
        source_abs: Path,
        sidecar_path: Path,
        file_path: str,
        sidecar_digest: str | None,
        root_stable_id: str | None,
        force: bool = False,
    ) -> tuple[TreeRepresentationRef, TreeValidityState]:
        return validate_or_recreate_from_content(
            kind=kind,
            content=content,
            source_abs=source_abs,
            sidecar_path=sidecar_path,
            file_path=file_path,
            sidecar_digest=sidecar_digest,
            root_stable_id=root_stable_id,
            force=force,
        )

    @staticmethod
    def from_path(
        *,
        project_root: Path,
        file_path: str,
        force: bool = False,
    ) -> tuple[TreeRepresentationRef, TreeValidityState]:
        return validate_or_recreate_tree_file(
            project_root=project_root,
            file_path=file_path,
            force=force,
        )


__all__ = ["TreeLifecycle"]
