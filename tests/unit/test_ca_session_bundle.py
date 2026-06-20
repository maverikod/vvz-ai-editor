"""Unit tests for multi-file bundle (C-004, C-006).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_editor.commands.universal_file_edit.format_group import resolve_format_group
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    build_multi_file_bundle_payload,
    bundle_file_count,
    create_session,
    get_session,
    list_bundle_file_paths,
    lookup_ca_session_id,
    resolve_session_for_command,
)
from ai_editor.core.exceptions import ValidationError


def _make_session(
    sid: str,
    file_path: str,
    *,
    project_id: str = "proj-1",
    format_group: str = "sidecar",
) -> EditSession:
    core = MagicMock()
    core.is_open = True
    core.session_dir = Path(f"/tmp/.session/{sid}/{file_path}")
    return EditSession(
        session_id=sid,
        project_id=project_id,
        file_path=file_path,
        abs_path=Path(f"/tmp/{file_path}"),
        draft_path=Path(f"/tmp/.session/{file_path}"),
        lockfile_path=Path("/tmp/.lock"),
        format_group=format_group,
        handler_id="python",
        tree_id=None,
        core=core,
        workspace_origin_path=Path(f"/tmp/{file_path}"),
        workspace_edit_subdir=Path(f"/tmp/.session/{sid}/{file_path}"),
    )


def _register_bundle(
    sid: str,
    sessions: list[EditSession],
) -> None:
    import ai_editor.commands.universal_file_edit.session as m

    bundle: dict[str, EditSession] = {}
    for session in sessions:
        norm_path = Path(session.file_path.replace("\\", "/")).as_posix()
        bundle[norm_path] = session
        if session.project_id:
            m._file_open_index[(session.project_id, norm_path)] = sid
    m._session_bundles[sid] = bundle


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    import ai_editor.commands.universal_file_edit.session as m

    m._session_bundles.clear()
    m._file_open_index.clear()


def test_create_session_rejects_empty_ca_session_id(tmp_path: Path) -> None:
    """Empty or whitespace ca_session_id raises ValidationError before registry."""
    src = tmp_path / "a.py"
    src.write_text("x = 1\n", encoding="utf-8")
    descriptor = resolve_format_group(src)

    for bad_id in ("", "   "):
        with pytest.raises(ValidationError, match="ca_session_id is required"):
            create_session(
                src.resolve(),
                descriptor,
                "a.py",
                ca_session_id=bad_id,
            )


def test_two_files_same_ca_session() -> None:
    sid = "ca-1"
    session_a = _make_session(sid, "a.py")
    session_b = _make_session(sid, "b.py")
    _register_bundle(sid, [session_a, session_b])

    assert get_session(sid, file_path="a.py") is session_a
    assert get_session(sid, file_path="b.py") is session_b

    with pytest.raises(ValueError, match="SESSION_FILE_PATH_REQUIRED"):
        get_session(sid)

    assert bundle_file_count(sid) == 2
    assert list_bundle_file_paths(sid) == ["a.py", "b.py"]

    payload = build_multi_file_bundle_payload(sid)
    assert payload["open_file_count"] == 2
    assert len(payload["files"]) == 2


def test_lookup_ca_session_id() -> None:
    sid = "ca-1"
    session_a = _make_session(sid, "a.py", project_id="proj-1")
    session_b = _make_session(sid, "b.py", project_id="proj-1")
    _register_bundle(sid, [session_a, session_b])

    assert lookup_ca_session_id("proj-1", "a.py") == sid
    assert lookup_ca_session_id("proj-1", "b.py") == sid
    assert lookup_ca_session_id("proj-1", "missing.py") is None
    assert lookup_ca_session_id("other-proj", "a.py") is None


def test_build_multi_file_bundle_payload_fields() -> None:
    sid = "ca-1"
    session_a = _make_session(sid, "a.py", project_id="proj-1")
    session_b = _make_session(sid, "b.py", project_id="proj-1")
    _register_bundle(sid, [session_a, session_b])

    payload = build_multi_file_bundle_payload(sid)
    assert payload["session_id"] == sid
    assert payload["open_file_count"] == 2
    assert [entry["file_path"] for entry in payload["files"]] == ["a.py", "b.py"]

    for entry, session in zip(payload["files"], [session_a, session_b]):
        assert entry["project_id"] == session.project_id
        assert entry["origin_path"] == str(session.workspace_origin_path)
        assert entry["draft_path"] == str(session.draft_path)
        assert entry["edit_subdir"] == str(session.workspace_edit_subdir)


def test_build_multi_file_bundle_payload_empty() -> None:
    payload = build_multi_file_bundle_payload("missing")
    assert payload == {
        "session_id": "missing",
        "open_file_count": 0,
        "files": [],
    }


def test_resolve_session_for_command_requires_file_path() -> None:
    sid = "ca-1"
    session_a = _make_session(sid, "a.py")
    session_b = _make_session(sid, "b.py")
    _register_bundle(sid, [session_a, session_b])

    with pytest.raises(ValueError, match="SESSION_FILE_PATH_REQUIRED"):
        resolve_session_for_command(sid, None)


def test_single_file_bundle_no_file_path_required() -> None:
    sid = "ca-1"
    session = _make_session(sid, "only.py")
    _register_bundle(sid, [session])

    assert resolve_session_for_command(sid, None) is session


def test_create_session_rejects_duplicate_file_in_same_session(
    tmp_path: Path,
) -> None:
    """One CA session cannot hold two open copies of the same file_path."""
    sid = "ca-1"
    session = _make_session(sid, "a.py", project_id="proj-1")
    _register_bundle(sid, [session])

    src = tmp_path / "a.py"
    src.write_text("x = 1\n", encoding="utf-8")
    descriptor = resolve_format_group(src)

    with pytest.raises(ValueError, match="FILE_ALREADY_IN_SESSION"):
        create_session(
            src.resolve(),
            descriptor,
            "a.py",
            ca_session_id=sid,
            project_id="proj-1",
        )


def test_create_session_rejects_file_open_in_other_session(tmp_path: Path) -> None:
    sid_a = "ca-a"
    sid_b = "ca-b"
    _register_bundle(sid_a, [_make_session(sid_a, "a.py", project_id="proj-1")])

    src = tmp_path / "a.py"
    src.write_text("x = 1\n", encoding="utf-8")
    descriptor = resolve_format_group(src)

    with pytest.raises(ValueError, match="FILE_ALREADY_IN_SESSION"):
        create_session(
            src.resolve(),
            descriptor,
            "a.py",
            ca_session_id=sid_b,
            project_id="proj-1",
        )


def test_merge_preview_params_multi_file_requires_matching_file_path() -> None:
    from ai_editor.commands.universal_file_preview.errors import (
        INPUT_ERROR_CONFLICTING_PARAMETERS,
        PreviewError,
    )
    from ai_editor.commands.universal_file_preview.session import (
        merge_edit_session_into_preview_params,
    )

    sid = "ca-1"
    session_a = _make_session(sid, "a.py", format_group="text")
    session_b = _make_session(sid, "b.md", format_group="text")
    _register_bundle(sid, [session_a, session_b])

    merged = merge_edit_session_into_preview_params(
        {
            "session_id": sid,
            "file_path": "b.md",
            "_preview_abs_path": "/unused",
        }
    )
    assert isinstance(merged, dict)
    assert merged["_preview_abs_path"] == str(session_b.draft_path)

    missing = merge_edit_session_into_preview_params({"session_id": sid})
    assert isinstance(missing, PreviewError)
    assert missing.code == INPUT_ERROR_CONFLICTING_PARAMETERS
    assert "file_path is required" in missing.message
