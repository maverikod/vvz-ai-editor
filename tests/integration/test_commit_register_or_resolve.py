"""Acceptance: commit path is register-or-resolve, symmetric with open.

A file can be present on disk (returned by ``list_project_files``) yet carry a
null ``file_id`` if its registration row was never persisted. The open path heals
this via ``ensure_file_id_for_path``; ``upload_session_file_content`` (commit) must
do the same instead of failing with ``file not found in project index``.

These drive the real ``upload_session_file_content`` with the two id helpers and
the transfer stub patched at the module level, so the resolve-then-ensure
branching under test runs exactly as in production.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from ai_editor.core.upstream import code_analysis_client as cac

_MOD = "ai_editor.core.upstream.code_analysis_client"
_NOT_FOUND = "file not found in project index: 'g5.yaml'"


def _commit(fake_self: Any, **kwargs: Any) -> bytes:
    """Invoke the real (unbound) commit method against a mock ``self``."""
    return cac.CodeAnalysisClient.upload_session_file_content(fake_self, **kwargs)


def _fake_client() -> MagicMock:
    """Build a fake client with the production lock-aware boundary attached."""
    fake_self = MagicMock()
    fake_self.ensure_session_file_lock = (
        cac.CodeAnalysisClient.ensure_session_file_lock.__get__(
            fake_self, cac.CodeAnalysisClient
        )
    )
    return fake_self


def _save_calls(fake_self: MagicMock) -> List[Any]:
    """Update-mode ``project_file_transfer_upload_save`` invocations on self.call."""
    return [
        c
        for c in fake_self.call.call_args_list
        if c.args and c.args[0] == "project_file_transfer_upload_save"
    ]


def test_t1_commit_heals_unregistered_on_disk_file() -> None:
    """T1: disk-present/index-missing file is registered then uploaded (once)."""
    fake_self = _fake_client()
    fake_self.call.return_value = {"content_bytes": b"ACCEPTED"}

    with patch(
        f"{_MOD}.resolve_file_id_for_path", side_effect=RuntimeError(_NOT_FOUND)
    ) as m_resolve, patch(
        f"{_MOD}.ensure_file_id_for_path", return_value="fid-new"
    ) as m_ensure, patch(
        f"{_MOD}.upload_bytes_transfer_id", return_value="tr-1"
    ):
        out = _commit(
            fake_self,
            session_id="s1",
            project_id="p1",
            file_path="g5.yaml",
            content=b"data",
        )

    m_resolve.assert_called_once()
    # Register fallback invoked exactly once, with the commit session id.
    m_ensure.assert_called_once()
    assert m_ensure.call_args.kwargs.get("session_id") == "s1"
    # Update-mode save proceeded with the freshly registered file_id.
    saves = _save_calls(fake_self)
    assert len(saves) == 1
    assert saves[0].args[1]["file_id"] == "fid-new"
    assert out == b"ACCEPTED"


def test_t2_genuine_missing_file_errors_terminal() -> None:
    """T2: no index rows at all -> terminal error, no silent upload."""
    fake_self = _fake_client()

    with patch(
        f"{_MOD}.resolve_file_id_for_path", side_effect=RuntimeError(_NOT_FOUND)
    ), patch(
        f"{_MOD}.ensure_file_id_for_path", side_effect=RuntimeError(_NOT_FOUND)
    ) as m_ensure, patch(
        f"{_MOD}.upload_bytes_transfer_id"
    ) as m_transfer:
        with pytest.raises(RuntimeError, match="file not found in project index"):
            _commit(
                fake_self,
                session_id="s1",
                project_id="p1",
                file_path="g5.yaml",
                content=b"data",
            )

    m_ensure.assert_called_once()
    assert _save_calls(fake_self) == []
    m_transfer.assert_not_called()


def test_t3_already_registered_takes_pure_resolve_no_fallback() -> None:
    """T3: a resolvable file_id never triggers the register fallback."""
    fake_self = _fake_client()
    fake_self.call.return_value = {"content_bytes": b"OK"}

    with patch(
        f"{_MOD}.resolve_file_id_for_path", return_value="fid-existing"
    ) as m_resolve, patch(
        f"{_MOD}.ensure_file_id_for_path"
    ) as m_ensure, patch(
        f"{_MOD}.upload_bytes_transfer_id", return_value="tr-9"
    ):
        out = _commit(
            fake_self,
            session_id="s1",
            project_id="p1",
            file_path="g5.yaml",
            content=b"data",
        )

    m_resolve.assert_called_once()
    m_ensure.assert_not_called()
    saves = _save_calls(fake_self)
    assert len(saves) == 1
    assert saves[0].args[1]["file_id"] == "fid-existing"
    assert out == b"OK"


def test_unrelated_resolve_error_propagates_without_fallback() -> None:
    """A3: a non-"not found" resolve error is not swallowed by the fallback."""
    fake_self = _fake_client()

    with patch(
        f"{_MOD}.resolve_file_id_for_path",
        side_effect=RuntimeError("UPSTREAM_TIMEOUT contacting CA"),
    ), patch(f"{_MOD}.ensure_file_id_for_path") as m_ensure:
        with pytest.raises(RuntimeError, match="UPSTREAM_TIMEOUT"):
            _commit(
                fake_self,
                session_id="s1",
                project_id="p1",
                file_path="g5.yaml",
                content=b"data",
            )

    m_ensure.assert_not_called()
