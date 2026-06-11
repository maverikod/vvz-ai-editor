"""
Centralized tree-lifecycle: checksum + validate + recreate.

This module owns ONE responsibility: "is there a valid tree (sidecar) for this
content; if not, build it". Every consumer that needs a structurally valid tree
(preview, grep, watcher, indexer, edit sessions, builders) routes through here
so the rule lives in a single place.

Design:
- The CORE works on CONTENT (strings), not file paths. Builders and edit
  sessions that already hold the source text in memory call the core directly,
  avoiding a redundant file read.
- A thin FILE wrapper sits on top: it reads the source once, computes the
  checksum, reads the sidecar digest, and delegates to the core.

Representation building (turning a valid tree into a preview/structure) is NOT
this module's job — that stays in ``tree_representation``. This module only
guarantees the tree is valid and rebuilds it when stale.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ai_editor.core.search_session.tree_representation import (
    TreeFormatKind,
    TreeRepresentationRef,
    TreeValidityState,
    classify_tree_format,
    sidecar_path_for,
)
from ai_editor.commands.universal_file_edit.sha_sync_policy import (
    ShaSyncBranch,
    ShaSyncDecision,
    resolve_sha_sync_policy,
)


def compute_content_checksum(content: str) -> str:
    """Return the SHA-256 hex digest of *content*.

    This is the content-based counterpart of hashing a file: callers that hold
    the source text in memory hash it directly, without touching disk.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_tree_valid(content_checksum: str, sidecar_digest: str | None) -> bool:
    """Return True when a sidecar digest exists and matches the content checksum."""
    return sidecar_digest is not None and sidecar_digest == content_checksum


class ChecksumSyncPolicy:
    """ChecksumSyncPolicy (C-006): four-branch tree-vs-source truth decision.

    This is the single mechanism that decides whether a TreeFile (C-003) is
    current with respect to its SourceFile (C-004), based solely on SHA-256
    checksums. Checksum computation and verification are the only synchronization
    trigger; mtime, size, and other file metadata are not used.

    Four-branch decision table (applies uniformly to all formats):

    Branch 1 -- NO_SIDECAR (ShaSyncBranch.NO_SIDECAR):
        Precondition: no co-located TreeFile exists.
        Action: build a new tree from the SourceFile content.

    Branch 2 -- SHA_MATCH (ShaSyncBranch.SHA_MATCH):
        Precondition: TreeFile present; stored checksum == current source
        checksum.
        Action: tree is current; no rebuild needed.

    Branch 3 -- SHA_MISMATCH_NO_SESSION (ShaSyncBranch.SHA_MISMATCH_NO_SESSION):
        Precondition: TreeFile present; checksums differ; no active edit
        session holds the file.
        Action: tree is stale; rebuild from SourceFile content.

    Branch 4 -- SHA_MISMATCH_ACTIVE_SESSION
    (ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION):
        Precondition: TreeFile present; checksums differ; an active edit
        session holds the file.
        Action: tree is truth, source copy inside session is stale;
        do NOT rebuild -- the session tree takes precedence.

    Session-truth invariant (C-006, HRS {a005}):
        Inside an active edit session the tree is the source of truth.
        Outside any session the SourceFile (C-004) is the source of truth.
    """

    #: Re-export the branch enum so callers need only import this class.
    Branch = ShaSyncBranch

    @staticmethod
    def decide(
        *,
        tree_file_present: bool,
        stored_checksum: str | None,
        current_checksum: str,
        active_session: bool,
    ) -> ShaSyncDecision:
        """Run the four-branch decision for one file.

        Args:
            tree_file_present: True when a co-located TreeFile exists on disk.
            stored_checksum: SHA-256 hex digest stored in the TreeFile, or None
                when the TreeFile is absent or its digest is unreadable.
            current_checksum: SHA-256 hex digest of the current SourceFile
                content, produced by :func:`compute_content_checksum`.
            active_session: True when an active edit session currently holds
                the file; the session tree is the source of truth in that case.

        Returns:
            A :class:`ShaSyncDecision` whose ``branch`` attribute identifies
            which of the four branches applies.
        """
        return resolve_sha_sync_policy(
            sidecar_exists=tree_file_present,
            sidecar_source_sha256=stored_checksum,
            current_source_sha256=current_checksum,
            active_session_holds_file=active_session,
        )


def recreate_tree_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild the sidecar tree for *content* using the per-format tree builders.

    Takes the already-in-memory ``content`` instead of re-reading the file, so a
    caller that just hashed the content does not pay a second read. Writes the
    sidecar atomically and returns a validated reference.
    """
    # Local imports break a module-load cycle with tree_representation and keep
    # the per-format builder dependencies lazy (heavy modules).
    if kind == TreeFormatKind.python_cst:
        from ai_editor.core.cst_tree.tree_builder import create_tree_from_code
        from ai_editor.core.search_session.tree_representation import (
            _read_cst_digest_and_root,
        )

        create_tree_from_code(str(source_abs), content, persist_sidecar=True)
        _digest, root_stable_id = _read_cst_digest_and_root(source_abs, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=root_stable_id,
        )

    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        from ai_editor.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )
        from ai_editor.core.search_session.tree_representation import (
            _read_tree_temp_root_stable_id,
        )

        if kind == TreeFormatKind.json:
            from ai_editor.core.json_tree.tree_builder import build_tree_from_data
            from ai_editor.core.tree_temp.json_frontend import (
                parse_json_source_to_roots,
            )

            data = json.loads(content)
            build_tree_from_data(str(source_abs), data)
            roots = parse_json_source_to_roots(content)
        else:
            import yaml as _yaml

            from ai_editor.core.tree_temp.yaml_frontend import (
                parse_yaml_source_to_roots,
            )
            from ai_editor.core.yaml_tree.tree_builder import (
                build_yaml_tree_from_data,
            )

            data = _yaml.safe_load(content)
            build_yaml_tree_from_data(str(source_abs), data)
            roots = parse_yaml_source_to_roots(content)

        sidecar_text = serialize_sidecar_to_json_text(content_checksum, roots)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )

    # markdown or plain text — sibling .tree
    from ai_editor.core.structure_extraction.extractor import extract_structure
    from ai_editor.core.search_session.tree_representation import (
        _read_adjacent_root_stable_id,
    )

    extract_structure(
        file_path=str(source_abs),
        content=content,
        ensure_persisted_tree=True,
    )
    payload: dict = {"source_sha256": content_checksum}
    root_stable_id = _read_adjacent_root_stable_id(sidecar_path)
    if root_stable_id is not None:
        payload["root_stable_id"] = root_stable_id
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar_path)
    return TreeRepresentationRef(
        file_path=file_path,
        sidecar_path=sidecar_path,
        content_checksum=content_checksum,
        root_stable_id=root_stable_id,
    )


def validate_or_recreate_from_content(
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
    """Decide reuse vs recreate for already-in-memory *content*.

    The caller supplies the current sidecar digest (and root stable id) it has
    already read. When the digest matches the content checksum and ``force`` is
    false, the existing sidecar is reused; otherwise the tree is rebuilt.
    """
    content_checksum = compute_content_checksum(content)
    if not force and is_tree_valid(content_checksum, sidecar_digest):
        return (
            TreeRepresentationRef(
                file_path=file_path,
                sidecar_path=sidecar_path,
                content_checksum=content_checksum,
                root_stable_id=root_stable_id,
            ),
            TreeValidityState.reused,
        )
    # Local import breaks cycle: format_handler → checksum → builder → format_handler.
    from ai_editor.core.tree_lifecycle.builder import TreeBuilder

    ref = TreeBuilder.build(
        content=content,
        source_abs=source_abs,
        file_path=file_path,
        content_checksum=content_checksum,
    )
    return ref, TreeValidityState.recreated


def validate_or_recreate_tree_file(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """File wrapper over the content core.

    Reads the source once, computes its checksum, reads the current sidecar
    digest, then delegates to ``validate_or_recreate_from_content``. This is the
    entry point for path-based consumers (preview, grep, watcher).

    Raises FileNotFoundError when the source file is absent.
    """
    from ai_editor.core.search_session.tree_representation import (
        _read_sidecar_state,
    )

    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content = source_abs.read_text(encoding="utf-8")
    sidecar_path = sidecar_path_for(file_path, root)
    sidecar_digest, root_stable_id = _read_sidecar_state(
        kind=kind, source_abs=source_abs, sidecar_path=sidecar_path
    )
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


__all__ = [
    "ChecksumSyncPolicy",
    "ShaSyncBranch",
    "ShaSyncDecision",
    "compute_content_checksum",
    "is_tree_valid",
    "recreate_tree_from_content",
    "validate_or_recreate_from_content",
    "validate_or_recreate_tree_file",
]
