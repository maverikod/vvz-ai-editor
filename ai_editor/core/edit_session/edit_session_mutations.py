"""EditSession lifecycle and tree helper functions (C-019).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ai_editor.core.tree_lifecycle import compute_content_checksum
from ai_editor.core.tree_lifecycle.node_id_map import (
    ChecksumsSection,
    DiscoveredNode,
    NodeIdMap,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from ai_editor.tree.handler_registry import HandlerRegistry

if TYPE_CHECKING:
    from .edit_session_impl import EditSession


def checkout_history_index(session: EditSession, index: int) -> None:
    """Restore working artefacts to ``timeline[index]`` without a new commit."""
    if not session.is_open:
        raise RuntimeError("EditSession is not open")
    commit_hash = session.history.timeline[index]
    mode = session.session_repo.checkout_revision(rev=commit_hash)
    session._sync_state_after_checkout(mode=mode)
    session.history.move_to(index)


def undo(session: EditSession) -> dict[str, object]:
    """Step back one edit; classic undo without creating a commit."""
    if not session.is_open:
        raise RuntimeError("EditSession is not open")
    if not session.history.can_undo():
        raise RuntimeError("nothing to undo")
    target = session.history.undo_index()
    checkout_history_index(session, target)
    return cast(dict[str, object], session.history.snapshot())


def redo(session: EditSession) -> dict[str, object]:
    """Step forward one edit; classic redo without creating a commit."""
    if not session.is_open:
        raise RuntimeError("EditSession is not open")
    if not session.history.can_redo():
        raise RuntimeError("nothing to redo")
    target = session.history.redo_index()
    checkout_history_index(session, target)
    return cast(dict[str, object], session.history.snapshot())


def record_revert_commit(session: EditSession, *, rev: str) -> str:
    """Git-style revert: checkout ``rev`` and append a new tracked commit."""
    new_commit = session.session_repo.revert(rev=rev)
    session._sync_state_after_checkout(
        mode=(
            "full"
            if session.session_repo.revision_includes_tree(rev=new_commit)
            else "degraded"
        )
    )
    session._record_history_commit(new_commit)
    return cast(str, new_commit)


def export_source_via_unmark(session: EditSession) -> None:
    handler = HandlerRegistry.default_registry().resolve(session.source_abs)
    sections = parse_tree_file(session.session_tree_path.read_text(encoding="utf-8"))
    clean = handler.unmark(sections.tree)
    session.session_source_path.write_text(clean, encoding="utf-8")


def update_session_tree_checksums(session: EditSession, source_sha256: str) -> None:
    """Write fresh source_sha256 into CHECKSUMS section of session tree file."""
    tree_text = session.session_tree_path.read_text(encoding="utf-8")
    sections = parse_tree_file(tree_text)
    sections.checksums = {"source_sha256": source_sha256}
    updated = serialize_tree_file(sections)
    tmp = session.session_tree_path.with_suffix(
        session.session_tree_path.suffix + ".tmp"
    )
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, session.session_tree_path)


def build_session_tree(session: EditSession, source_text: str) -> bool:
    """Build marked tree in session dir using MAP from session tree file."""
    handler = HandlerRegistry.default_registry().resolve(session.source_abs)
    marked_text = handler.mark(source_text)
    nodes = handler.parse_content(Path(session.file_path), source_text)
    discovered: list[DiscoveredNode] = [
        DiscoveredNode(
            content_fingerprint=compute_content_fingerprint(node.content),
            kind=node.kind,
            marker_short_id=int(node.short_id),
            attributes=dict(node.attributes),
        )
        for node in nodes
    ]
    if not discovered:
        return False
    prior_map = None
    if session.session_tree_path.is_file():
        try:
            prior_map = parse_tree_file(
                session.session_tree_path.read_text(encoding="utf-8")
            ).map
        except Exception:
            prior_map = None
    checksums: ChecksumsSection = {"source_sha256": session.source_checksum}
    sections, node_map = NodeIdMap.build(
        tree_marked_text=marked_text,
        discovered_nodes=discovered,
        source_sha256=session.source_checksum,
        prior_map=prior_map,
    )
    if prior_map is not None:
        sections = node_map.validate_and_repair(
            tree_marked_text=marked_text,
            discovered_nodes=discovered,
            checksums=checksums,
        )
    file_text = serialize_tree_file(sections)
    tmp = session.session_tree_path.with_suffix(
        session.session_tree_path.suffix + ".tmp"
    )
    tmp.write_text(file_text, encoding="utf-8")
    os.replace(tmp, session.session_tree_path)
    return True


def try_revalidate(session: EditSession) -> None:
    from .edit_session_impl import SessionTreeValidity

    if session.tree_validity != SessionTreeValidity.INVALID:
        return
    source_text = session.session_source_path.read_text(encoding="utf-8")
    try:
        HandlerRegistry.default_registry().resolve(session.source_abs).parse_content(
            Path(session.file_path),
            source_text,
        )
    except Exception:
        return
    if not build_session_tree(session, source_text):
        return
    export_source_via_unmark(session)
    session.source_checksum = compute_content_checksum(
        session.session_source_path.read_text(encoding="utf-8")
    )
    update_session_tree_checksums(session, session.source_checksum)
    session.tree_validity = SessionTreeValidity.VALID
    session.tree_checksum = compute_content_checksum(
        session.session_tree_path.read_text(encoding="utf-8")
    )
    session.session_repo.commit_full(message="session: revalidation")
    session._record_history_commit(session.session_repo.log()[0].hash)


def preview_external_write(session: EditSession) -> dict[str, Any]:
    """Compute unified diffs of in-session artefacts vs live external files; no external writes."""
    if not session.is_open:
        raise RuntimeError("EditSession is not open; cannot preview external write.")
    in_source = (
        session.session_source_path.read_text(encoding="utf-8")
        if session.session_source_path.is_file()
        else ""
    )
    in_tree = (
        session.session_tree_path.read_text(encoding="utf-8")
        if session.session_tree_path.is_file()
        else ""
    )
    ext_source = (
        session.source_abs.read_text(encoding="utf-8")
        if session.source_abs.is_file()
        else ""
    )
    ext_tree = (
        session.tree_abs.read_text(encoding="utf-8")
        if session.tree_abs.is_file()
        else ""
    )
    source_diff = "".join(
        difflib.unified_diff(
            in_source.splitlines(keepends=True),
            ext_source.splitlines(keepends=True),
            fromfile="in-session-source",
            tofile="external-source",
        )
    )
    tree_diff = "".join(
        difflib.unified_diff(
            in_tree.splitlines(keepends=True),
            ext_tree.splitlines(keepends=True),
            fromfile="in-session-tree",
            tofile="external-tree",
        )
    )
    has_changes = bool(source_diff.strip() or tree_diff.strip())
    return {
        "has_changes": has_changes,
        "source_diff": source_diff,
        "tree_diff": tree_diff,
    }


def confirm_external_copy_out(session: EditSession) -> None:
    """Atomically copy in-session artefacts to external co-located paths; both or neither when valid."""
    from .edit_session_impl import SessionTreeValidity

    if not session.is_open:
        raise RuntimeError("EditSession is not open; cannot confirm external copy-out.")
    preview = preview_external_write(session)
    if not preview["has_changes"]:
        return
    if session.tree_validity == SessionTreeValidity.VALID:
        if (
            not session.session_tree_path.is_file()
            or not session.session_source_path.is_file()
        ):
            raise RuntimeError("Session artefacts missing for external copy-out")
        tmp_tree = session.tree_abs.with_suffix(session.tree_abs.suffix + ".tmp")
        tmp_source = session.source_abs.with_suffix(session.source_abs.suffix + ".tmp")
        backup_tree = session.tree_abs.with_suffix(session.tree_abs.suffix + ".bak")
        try:
            shutil.copy2(session.session_tree_path, tmp_tree)
            shutil.copy2(session.session_source_path, tmp_source)
            if session.tree_abs.exists():
                shutil.copy2(session.tree_abs, backup_tree)
            tmp_tree.replace(session.tree_abs)
            try:
                tmp_source.replace(session.source_abs)
            except Exception:
                if backup_tree.exists():
                    shutil.copy2(backup_tree, session.tree_abs)
                raise
        except Exception:
            tmp_tree.unlink(missing_ok=True)
            tmp_source.unlink(missing_ok=True)
            raise
        finally:
            backup_tree.unlink(missing_ok=True)
    else:
        tmp_source = session.source_abs.with_suffix(session.source_abs.suffix + ".tmp")
        try:
            shutil.copy2(session.session_source_path, tmp_source)
            tmp_source.replace(session.source_abs)
        except Exception:
            tmp_source.unlink(missing_ok=True)
            raise


def close(session: EditSession) -> None:
    from .edit_session_impl import _active_sessions

    _active_sessions.pop(session.session_id, None)
    if session.session_dir.exists():
        shutil.rmtree(session.session_dir)
    session.is_open = False


def record_tree_modification(session: EditSession) -> None:
    raise RuntimeError("use apply_valid_tree_mutation or apply_tree_operation")
