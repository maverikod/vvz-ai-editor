"""Shared CA upstream mocks for thin-editor universal_file_* tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_proxy_adapter.commands.result import SuccessResult

from ai_editor.commands.universal_file_edit.session import release_session
from ai_editor.core.editor_workspace_paths import file_workspace_layout
from ai_editor.core.upstream.code_analysis_client import CaSessionStatus

GET_CA_CLIENT_PATCHES = (
    "ai_editor.commands.universal_file_edit.open_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.open_command_runtime.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.write_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_edit.close_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_preview_command.get_code_analysis_client",
    "ai_editor.commands.universal_file_preview_runtime.get_code_analysis_client",
    "ai_editor.core.upstream.code_analysis_client.get_code_analysis_client",
)

RESOLVE_WORKSPACE_PATCHES = (
    "ai_editor.core.editor_workspace_paths.resolve_workspace_root",
    "ai_editor.commands.universal_file_edit.open_command_runtime.resolve_workspace_root",
    "ai_editor.commands.universal_file_edit.close_command.resolve_workspace_root",
)

DEFAULT_CA_SESSION_ID = "ca-test"


def make_workspace(tmp_path: Path) -> Path:
    """Return editor workspace root under tmp_path."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def mock_upstream(
    *,
    origins: dict[str, bytes] | None = None,
    default: bytes = b"",
) -> MagicMock:
    """Build mock Code Analysis client with lock/download and upload hooks."""
    store: dict[str, bytes] = dict(origins or {})
    upstream = MagicMock()
    upstream.validate_ca_session.return_value = CaSessionStatus.VALID

    def _lock(session_id: str, project_id: str, file_path: str) -> bytes:
        _ = session_id, project_id
        if file_path in store:
            return store[file_path]
        return default

    upstream.lock_file_and_download.side_effect = _lock

    def _create(**kwargs: object) -> bytes:
        content = kwargs["content"]
        assert isinstance(content, bytes)
        file_path = str(kwargs["file_path"])
        store[file_path] = content
        return content

    upstream.upload_create_and_lock.side_effect = _create
    upstream.upload_session_file_content.side_effect = lambda **kwargs: kwargs[
        "content"
    ]

    def _download(*, project_id: str, file_path: str) -> bytes:
        _ = project_id
        return _lock("", "", file_path)

    upstream.download_without_lock.side_effect = _download
    upstream.unlock_session_file.return_value = True
    return upstream


@contextmanager
def upstream_context(
    *,
    workspace: Path,
    upstream: MagicMock,
) -> Iterator[None]:
    """Patch workspace resolver and CA client across universal_file_* commands."""
    with ExitStack() as stack:
        for target in RESOLVE_WORKSPACE_PATCHES:
            stack.enter_context(patch(target, return_value=workspace))
        for target in GET_CA_CLIENT_PATCHES:
            stack.enter_context(patch(target, return_value=upstream))
        yield


def layout_origin(
    workspace: Path,
    sid: str,
    project_id: str,
    file_path: str,
) -> Path:
    """Origin snapshot path for one open file in workspace mode."""
    return file_workspace_layout(workspace, sid, project_id, file_path).origin_path


def ensure_projectid_marker(session_dir: Path, project_id: str) -> None:
    """BackupManager marker under session_dir (C-022)."""
    (session_dir / "projectid").write_text(
        f'{{"id": "{project_id}"}}\n',
        encoding="utf-8",
    )


def session_dir_for(
    workspace: Path,
    sid: str,
    project_id: str,
    file_path: str,
) -> Path:
    return file_workspace_layout(workspace, sid, project_id, file_path).session_dir


def reset_ca_session(sid: str, *file_paths: str) -> None:
    """Release in-memory session bundle entries for test isolation."""
    if file_paths:
        for file_path in file_paths:
            release_session(sid, file_path)
        return
    from ai_editor.commands.universal_file_edit import session as session_mod

    bundle = session_mod._session_bundles.get(str(sid or "").strip())
    if bundle is None:
        return
    for file_path in list(bundle.keys()):
        release_session(sid, file_path)


def clear_ca_session(sid: str = DEFAULT_CA_SESSION_ID) -> None:
    """Release every open file in a CA session bundle."""
    reset_ca_session(sid)


def ensure_session_marked_tree(session_id: str, file_path: str) -> Path:
    """Build MAP sidecar for an open text/markdown session (short_id edits)."""
    from ai_editor.commands.universal_file_edit.session import get_session
    from ai_editor.core.edit_session.edit_session_impl import SessionTreeValidity
    from ai_editor.tree.sibling_convention import sibling_tree_path

    sess = get_session(session_id, file_path=file_path)
    draft = sess.core.session_source_path
    tree_path = sess.core.session_tree_path
    materialize_tree_sidecar(draft, file_path=file_path)
    built = sibling_tree_path(draft.resolve())
    if built.is_file() and built.resolve() != tree_path.resolve():
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        tree_path.write_text(built.read_text(encoding="utf-8"), encoding="utf-8")
    sess.core.tree_validity = SessionTreeValidity.VALID
    return tree_path


def session_draft_path(session_id: str, file_path: str) -> Path:
    """Return draft/source path for an open universal_file_edit session."""
    from ai_editor.commands.universal_file_edit.session import get_session

    return get_session(session_id, file_path=file_path).draft_path


def materialize_tree_sidecar(origin: Path, *, file_path: str) -> Path:
    """Write sibling .tree sidecar beside origin (test helper for tree-temp)."""
    import hashlib

    from ai_editor.core.tree_lifecycle.builder import TreeBuilder
    from ai_editor.tree.sibling_convention import sibling_tree_path

    content = origin.read_text(encoding="utf-8")
    sha = hashlib.sha256(origin.read_bytes()).hexdigest()
    TreeBuilder.build(
        content=content,
        source_abs=origin.resolve(),
        file_path=file_path,
        content_checksum=sha,
    )
    return sibling_tree_path(origin.resolve())


@contextmanager
def edit_guard_context(upstream: MagicMock | None = None) -> Iterator[MagicMock]:
    """Patch CA client for edit-command SessionGuard on create_session tests."""
    client = upstream if upstream is not None else mock_upstream()
    with patch(
        "ai_editor.commands.universal_file_edit.edit_command.get_code_analysis_client",
        return_value=client,
    ):
        yield client


async def open_ca_file(
    tmp_path: Path,
    *,
    project_id: str,
    file_path: str,
    content: bytes,
    sid: str = DEFAULT_CA_SESSION_ID,
    create: bool = False,
    initial_content: str = "",
) -> tuple[str, Path, Path, MagicMock]:
    """Open one file via CA mocks; return sid, workspace, origin, upstream."""
    from ai_editor.commands.universal_file_edit.open_command import (
        UniversalFileOpenCommand,
    )
    from mcp_proxy_adapter.commands.result import SuccessResult

    workspace = make_workspace(tmp_path)
    upstream = mock_upstream(origins={file_path: content})
    with upstream_context(workspace=workspace, upstream=upstream):
        cmd = UniversalFileOpenCommand()
        params: dict[str, object] = {
            "session_id": sid,
            "project_id": project_id,
            "file_path": file_path,
        }
        if create:
            params["create"] = True
            params["initial_content"] = initial_content
        res = await cmd.execute(**params)
        assert isinstance(res, SuccessResult), res
    ensure_projectid_marker(
        session_dir_for(workspace, sid, project_id, file_path),
        project_id,
    )
    origin = layout_origin(workspace, sid, project_id, file_path)
    return sid, workspace, origin, upstream


async def commit_write(
    *,
    workspace: Path,
    upstream: MagicMock,
    project_id: str,
    session_id: str,
    file_path: str | None = None,
) -> SuccessResult:
    """Commit write via CA mocks (preview deferred in thin server)."""
    from ai_editor.commands.universal_file_edit.write_command import (
        UniversalFileWriteCommand,
    )

    wr = UniversalFileWriteCommand()
    params: dict[str, object] = {
        "project_id": project_id,
        "session_id": session_id,
        "write_mode": "commit",
    }
    if file_path:
        params["file_path"] = file_path
    with upstream_context(workspace=workspace, upstream=upstream):
        res = await wr.execute(**wr.validate_params(params))
    assert isinstance(res, SuccessResult), res
    return res
