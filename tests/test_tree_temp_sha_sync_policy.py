"""Branch tests for SHA sync policy wrapper (tree-temp).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib

import pytest

from ai_editor.core.tree_temp.sha_policy import ShaSyncDecision, resolve_sha_sync

DIG = "ab" * 32
DIG2 = "cd" * 32


def sha_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("session_flag", [True, False])
def test_no_sidecar_branch_constant(session_flag: bool) -> None:
    assert (
        resolve_sha_sync(
            sidecar_present=False,
            sidecar_digest=DIG,
            current_digest=sha_of("x"),
            session_active_for_path=session_flag,
        )
        == ShaSyncDecision.NO_SIDE_CAR_MATERIALIZE
    )


@pytest.mark.parametrize("session_flag", [True, False])
def test_sha_match_returns_load_even_if_session_true(session_flag: bool) -> None:
    d = DIG
    assert (
        resolve_sha_sync(
            sidecar_present=True,
            sidecar_digest=d,
            current_digest=d,
            session_active_for_path=session_flag,
        )
        == ShaSyncDecision.SIDE_CAR_DIGEST_MATCH_LOAD
    )


def test_sha_mismatch_no_session_returns_rebuild() -> None:
    assert (
        resolve_sha_sync(
            sidecar_present=True,
            sidecar_digest=DIG,
            current_digest=DIG2,
            session_active_for_path=False,
        )
        == ShaSyncDecision.SHA_MISMATCH_REBUILD_NO_SESSION
    )


def test_sha_mismatch_active_session_prefers_hold() -> None:
    assert (
        resolve_sha_sync(
            sidecar_present=True,
            sidecar_digest=DIG,
            current_digest=DIG2,
            session_active_for_path=True,
        )
        == ShaSyncDecision.SHA_MISMATCH_HOLD_SESSION_SIDE
    )


def test_invalid_digest_length_raises_value_error_with_digest_token() -> None:
    bad = "00" * 31
    assert len(bad) == 62
    with pytest.raises(ValueError, match="digest"):
        resolve_sha_sync(
            sidecar_present=True,
            sidecar_digest=bad,
            current_digest=DIG,
            session_active_for_path=False,
        )
