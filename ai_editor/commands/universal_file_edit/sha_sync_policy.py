"""SHA sync branch resolver for tree sidecar open workflow.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ShaSyncBranch(str, Enum):
    NO_SIDECAR = "no_sidecar"
    SHA_MATCH = "sha_match"
    SHA_MISMATCH_NO_SESSION = "sha_mismatch_no_session"
    SHA_MISMATCH_ACTIVE_SESSION = "sha_mismatch_active_session"


@dataclass(frozen=True)
class ShaSyncDecision:
    branch: ShaSyncBranch
    missing_sidecar: bool
    sha_equal: bool
    sha_unequal_without_active_session: bool
    sha_unequal_with_active_session: bool


def resolve_sha_sync_policy(
    *,
    sidecar_exists: bool,
    sidecar_source_sha256: Optional[str],
    current_source_sha256: str,
    active_session_holds_file: bool,
) -> ShaSyncDecision:
    if not sidecar_exists:
        return ShaSyncDecision(
            branch=ShaSyncBranch.NO_SIDECAR,
            missing_sidecar=True,
            sha_equal=False,
            sha_unequal_without_active_session=False,
            sha_unequal_with_active_session=False,
        )

    if sidecar_source_sha256 is None or not str(sidecar_source_sha256).strip():
        if active_session_holds_file:
            return ShaSyncDecision(
                branch=ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION,
                missing_sidecar=False,
                sha_equal=False,
                sha_unequal_without_active_session=False,
                sha_unequal_with_active_session=True,
            )
        return ShaSyncDecision(
            branch=ShaSyncBranch.SHA_MISMATCH_NO_SESSION,
            missing_sidecar=False,
            sha_equal=False,
            sha_unequal_without_active_session=True,
            sha_unequal_with_active_session=False,
        )

    a = sidecar_source_sha256.strip().lower()
    b = current_source_sha256.strip().lower()
    if a == b:
        return ShaSyncDecision(
            branch=ShaSyncBranch.SHA_MATCH,
            missing_sidecar=False,
            sha_equal=True,
            sha_unequal_without_active_session=False,
            sha_unequal_with_active_session=False,
        )

    if active_session_holds_file:
        return ShaSyncDecision(
            branch=ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION,
            missing_sidecar=False,
            sha_equal=False,
            sha_unequal_without_active_session=False,
            sha_unequal_with_active_session=True,
        )

    return ShaSyncDecision(
        branch=ShaSyncBranch.SHA_MISMATCH_NO_SESSION,
        missing_sidecar=False,
        sha_equal=False,
        sha_unequal_without_active_session=True,
        sha_unequal_with_active_session=False,
    )
