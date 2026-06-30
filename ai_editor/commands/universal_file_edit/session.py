"""
EditSession facade and command-layer metadata over core C-012 EditSession.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_editor.commands.universal_file_edit.format_group import (
    FormatDescriptor,
    lockfile_path_for_edit_source,
)
from ai_editor.core.edit_session import (
    EditSession as CoreEditSession,
    SessionTreeValidity,
)
from ai_editor.core.exceptions import ValidationError
from ai_editor.tree.edit_operations import EditOperation
from ai_editor.core.edit_session.edit_session import _active_sessions
from ai_editor.core.tree_temp.tree_node import TreeNode

# ca_session_id -> project-relative file_path -> EditSession facade
_session_bundles: dict[str, dict[str, "EditSession"]] = {}
# (project_id, norm file_path) -> ca_session_id
_file_open_index: dict[tuple[str, str], str] = {}


@dataclass
class EditSession:
    """Universal-file command facade over one core EditSession (C-012)."""

    session_id: str
    project_id: str
    file_path: str
    abs_path: Path
    draft_path: Path
    lockfile_path: Path
    format_group: str
    handler_id: str
    tree_id: Optional[str]
    core: CoreEditSession
    source_sha256_at_open: Optional[str] = None
    dirty: bool = False
    # True once the file exists on Code Analysis (an existing file opened with a
    # lock, or a new file persisted by a successful commit). False for a new file
    # opened with create=true that has never been committed: it lives only in the
    # local workspace draft and holds no CA lock yet. Drives R3 (lock-then-create
    # on first commit) and R4 (release the CA lock on close only when it exists).
    persisted_on_ca: bool = True
    # True when at least one edit produced a non-empty diff since open or the last
    # successful commit. Set by universal_file_edit, cleared by a successful
    # universal_file_write commit, consulted by universal_file_close (R5/R6).
    modified: bool = False
    tree_temp_roots: Optional[List[TreeNode]] = None
    sidecar_write_intent: Optional[str] = None
    fallback_reason: Optional[str] = None
    original_format_group: Optional[str] = None
    is_invalid: bool = False
    workspace_session_root: Optional[Path] = None
    workspace_file_subtree_root: Optional[Path] = None
    workspace_origin_path: Optional[Path] = None
    workspace_edit_subdir: Optional[Path] = None


def _norm_file_path(file_path: str) -> str:
    return Path(str(file_path).replace("\\", "/")).as_posix()


def _file_key(project_id: str, file_path: str) -> tuple[str, str]:
    return (str(project_id or "").strip(), _norm_file_path(file_path))


def lookup_ca_session_id(project_id: str, file_path: str) -> Optional[str]:
    """Return CA ``ca_session_id`` for an open file, if any."""
    return _file_open_index.get(_file_key(project_id, file_path))


def bundle_file_count(ca_session_id: str) -> int:
    """Return number of open files in the ca_session bundle."""
    bundle = _session_bundles.get(str(ca_session_id or "").strip())
    if bundle is None:
        return 0
    return len(bundle)


def bundle_has_multiple_files(ca_session_id: str) -> bool:
    """Return True when the bundle holds more than one open file."""
    return bundle_file_count(ca_session_id) > 1


def list_bundle_file_paths(ca_session_id: str) -> List[str]:
    """Return sorted project-relative file_path keys for the bundle."""
    bundle = _session_bundles.get(str(ca_session_id or "").strip())
    if bundle is None:
        return []
    return sorted(bundle.keys())


def resolve_session_for_command(
    ca_session_id: str,
    file_path: Optional[str],
) -> EditSession:
    """Resolve EditSession for workflow commands; enforce file_path when N>1."""
    return get_session(ca_session_id, file_path=file_path)


def build_multi_file_bundle_payload(ca_session_id: str) -> Dict[str, Any]:
    """Build multi_file_bundle object for universal_file_open success (C-006)."""
    sid = str(ca_session_id or "").strip()
    bundle = _session_bundles.get(sid)
    if bundle is None or not bundle:
        return {"session_id": sid, "open_file_count": 0, "files": []}
    files: List[Dict[str, Any]] = []
    for _norm_path, session in sorted(bundle.items()):
        files.append(
            {
                "file_path": session.file_path,
                "project_id": session.project_id,
                "origin_path": str(
                    session.workspace_origin_path
                    if session.workspace_origin_path is not None
                    else session.abs_path
                ),
                "draft_path": str(session.draft_path),
                "edit_subdir": str(
                    session.workspace_edit_subdir
                    if session.workspace_edit_subdir is not None
                    else session.core.session_dir
                ),
            }
        )
    return {"session_id": sid, "open_file_count": len(files), "files": files}


def _resolve_project_root_near(abs_path: Path) -> Path:
    """Locate project root upward from ``abs_path`` for core session open."""
    resolved = abs_path.resolve()
    probe = resolved.parent if resolved.is_file() else resolved
    for candidate in (probe,) + tuple(probe.parents):
        if (candidate / "pyproject.toml").exists() or (
            candidate / "projectid"
        ).exists():
            return candidate
    return probe


def create_session(
    abs_path: Path,
    descriptor: FormatDescriptor,
    file_path: str,
    tree_id: Optional[str] = None,
    *,
    project_root: Optional[Path] = None,
    source_sha256_at_open: Optional[str] = None,
    tree_temp_roots: Optional[List[TreeNode]] = None,
    sidecar_write_intent: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    original_format_group: Optional[str] = None,
    is_invalid: bool = False,
    initial_source_text: Optional[str] = None,
    ca_session_id: str,
    project_id: str = "",
    persisted_on_ca: bool = True,
    workspace_session_root: Optional[Path] = None,
    workspace_file_subtree_root: Optional[Path] = None,
    workspace_origin_path: Optional[Path] = None,
    workspace_edit_subdir: Optional[Path] = None,
) -> EditSession:
    """Open a core EditSession and register command-layer metadata.

    ``ca_session_id`` is the CA session identifier and the sole bundle key.
    Multiple files opened under the same ``ca_session_id`` share one bundle.

    ``persisted_on_ca`` records whether the file already exists on Code Analysis.
    Pass ``False`` for a new file opened with ``create=true`` (R1): it is held
    only in the local draft until the first successful commit promotes it (R3).
    """
    ca_id = str(ca_session_id or "").strip()
    if not ca_id:
        raise ValidationError(
            "ca_session_id is required",
            field="ca_session_id",
        )

    norm_path = _norm_file_path(file_path)
    pid = str(project_id or "").strip()
    if pid:
        existing = _file_open_index.get(_file_key(pid, norm_path))
        if existing is not None:
            raise ValueError("FILE_ALREADY_IN_SESSION")

    bundle = _session_bundles.get(ca_id)
    if bundle is None:
        bundle = {}
        _session_bundles[ca_id] = bundle
    elif norm_path in bundle:
        raise ValueError("FILE_ALREADY_IN_SESSION")

    root = (
        project_root
        if project_root is not None
        else _resolve_project_root_near(abs_path)
    )
    content = initial_source_text
    if content is None and not abs_path.is_file():
        content = ""
    open_kwargs: dict[str, Any] = {
        "source_abs": abs_path,
        "project_root": root,
        "file_path": file_path,
        "content": content if not abs_path.is_file() else None,
    }
    if (
        workspace_session_root is not None
        and workspace_file_subtree_root is not None
        and workspace_origin_path is not None
        and workspace_edit_subdir is not None
    ):
        open_kwargs.update(
            {
                "workspace_session_root": workspace_session_root,
                "workspace_file_subtree_root": workspace_file_subtree_root,
                "workspace_origin_path": workspace_origin_path,
                "workspace_edit_subdir": workspace_edit_subdir,
            }
        )
    core = CoreEditSession.open(**open_kwargs)
    lockfile_path = lockfile_path_for_edit_source(core.session_source_path)
    session = EditSession(
        session_id=ca_id,
        project_id=pid,
        file_path=file_path,
        abs_path=abs_path,
        draft_path=core.session_source_path,
        lockfile_path=lockfile_path,
        format_group=descriptor.format_group,
        handler_id=descriptor.handler_id,
        tree_id=tree_id,
        core=core,
        source_sha256_at_open=source_sha256_at_open,
        dirty=False,
        persisted_on_ca=persisted_on_ca,
        modified=False,
        tree_temp_roots=tree_temp_roots,
        sidecar_write_intent=sidecar_write_intent,
        fallback_reason=fallback_reason,
        original_format_group=original_format_group,
        is_invalid=is_invalid,
        workspace_session_root=workspace_session_root,
        workspace_file_subtree_root=workspace_file_subtree_root,
        workspace_origin_path=workspace_origin_path,
        workspace_edit_subdir=workspace_edit_subdir,
    )
    bundle[norm_path] = session
    if pid:
        _file_open_index[_file_key(pid, norm_path)] = ca_id
    return session


def get_session(session_id: str, file_path: Optional[str] = None) -> EditSession:
    """Return the command facade for a CA session and optional file path."""
    bundle = _session_bundles.get(session_id)
    if not bundle:
        raise ValueError("SESSION_NOT_FOUND")
    if file_path is None:
        if len(bundle) == 1:
            session = next(iter(bundle.values()))
        else:
            raise ValueError("SESSION_FILE_PATH_REQUIRED")
    else:
        found = bundle.get(_norm_file_path(file_path))
        if found is None:
            raise ValueError("SESSION_NOT_FOUND")
        session = found
    if not session.core.is_open:
        raise ValueError("SESSION_NOT_FOUND")
    return session


def release_session(session_id: str, file_path: Optional[str] = None) -> None:
    """Remove one file (or the sole file) from a CA bundle and close its core session."""
    bundle = _session_bundles.get(session_id)
    if bundle is None:
        return
    if file_path is None:
        if len(bundle) != 1:
            raise ValueError("SESSION_FILE_PATH_REQUIRED")
        norm_path = next(iter(bundle))
    else:
        norm_path = _norm_file_path(file_path)
    session = bundle.pop(norm_path, None)
    if session is not None:
        if session.project_id:
            _file_open_index.pop(
                _file_key(session.project_id, session.file_path),
                None,
            )
        if session.core.is_open:
            session.core.close()
    if not bundle:
        _session_bundles.pop(session_id, None)


def purge_stale_open_index_entry(
    project_id: str,
    file_path: str,
    *,
    ca_session_dead: bool,
) -> bool:
    """Purge a stale ``_file_open_index`` entry when its CA session is dead.

    The open-time guard rejects a re-open while ``_file_open_index`` still maps
    the path to a session id. That mapping is normally cleared by
    ``release_session`` on close, but a CA-side ``session_delete force=true``
    drops the CA session without notifying the editor, orphaning the entry. This
    helper detects such a dead entry and removes it so the open can proceed.

    Staleness combines two independent signals; the entry is stale when **either**
    holds:

    - **Local:** no live ``EditSession`` backs the registered id — the bundle or
      the file's session is missing, or its ``core.is_open`` is ``False``.
    - **CA:** ``ca_session_dead`` is ``True``, i.e. CA reported the session as
      ``NOT_FOUND``. CA-unreachable must map to ``False`` here so a possibly-live
      lock is never torn down on the basis of CA being unavailable.

    This function only reads the module registries and delegates cleanup to
    ``release_session``; it performs no Code Analysis round-trip.

    Args:
        project_id: Project UUID owning the file.
        file_path: Project-relative path of the file being opened.
        ca_session_dead: ``True`` only when CA reported the registered session as
            ``NOT_FOUND``.

    Returns:
        ``True`` when a stale entry was found and removed; ``False`` when nothing
        is registered for the path or the registered session is genuinely live.
    """
    sid = _file_open_index.get(_file_key(project_id, file_path))
    if sid is None:
        return False
    bundle = _session_bundles.get(sid)
    session = bundle.get(_norm_file_path(file_path)) if bundle is not None else None
    is_stale = (
        bundle is None
        or session is None
        or session.core.is_open is False
        or ca_session_dead is True
    )
    if not is_stale:
        return False
    release_session(sid, file_path)
    return True


def active_session_uses_abs_path(abs_path: Path) -> bool:
    """Return True if any registered core session uses this resolved absolute path."""
    target = abs_path.resolve()
    for core in _active_sessions.values():
        if core.source_abs.resolve() == target:
            return True
    return False


def apply_tree_operation(session: EditSession, operation: EditOperation) -> None:
    """Apply one G-004 EditOperation via core session adapter ({h008})."""
    session.core.apply_tree_operation(operation)
    session.draft_path = session.core.session_source_path
    session.dirty = True


def apply_source_mutation(session: EditSession, new_source_text: str) -> None:
    """Apply in-session source change via core valid-tree or plaintext mutation."""
    if session.is_invalid or session.core.tree_validity == SessionTreeValidity.INVALID:
        session.core.apply_plaintext_mutation(new_source_text)
    else:
        session.core.apply_valid_tree_mutation(lambda _: new_source_text)
    session.draft_path = session.core.session_source_path
    session.dirty = True


def apply_cst_sidecar_mutation(
    session: EditSession,
    new_source_text: str,
    *,
    sidecar_abs: Path,
) -> None:
    """Persist legacy CST sidecar edit into the session repo and undo history."""
    session.core.apply_cst_sidecar_mutation(
        new_source_text,
        sidecar_abs=sidecar_abs,
    )
    session.draft_path = session.core.session_source_path
    session.dirty = True
