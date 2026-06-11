"""SHA sync decision helpers for tree-temp tests (G-005 contract surface).

Maps to :func:`resolve_sha_sync_policy` with stricter digest validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Optional

from ai_editor.commands.universal_file_edit.sha_sync_policy import (
    ShaSyncBranch,
    resolve_sha_sync_policy,
)

_lower_hex_64 = re.compile(r"^[0-9a-f]{64}$")


class ShaSyncDecision:
    """Symbolic constants for branch comparison in tests."""

    NO_SIDE_CAR_MATERIALIZE = ShaSyncBranch.NO_SIDECAR
    SIDE_CAR_DIGEST_MATCH_LOAD = ShaSyncBranch.SHA_MATCH
    SHA_MISMATCH_REBUILD_NO_SESSION = ShaSyncBranch.SHA_MISMATCH_NO_SESSION
    SHA_MISMATCH_HOLD_SESSION_SIDE = ShaSyncBranch.SHA_MISMATCH_ACTIVE_SESSION


def _require_digest(name: str, value: Optional[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not _lower_hex_64.match(value):
        raise ValueError(f"digest invalid for {name}: require 64 lowercase hex chars")


def resolve_sha_sync(
    *,
    sidecar_present: bool,
    sidecar_digest: Optional[str],
    current_digest: str,
    session_active_for_path: bool,
) -> ShaSyncBranch:
    """Resolve sync branch; validates digests when required (lowercase hex only)."""
    _require_digest("current_digest", current_digest)
    if sidecar_present:
        _require_digest("sidecar_digest", sidecar_digest)
    decision = resolve_sha_sync_policy(
        sidecar_exists=sidecar_present,
        sidecar_source_sha256=sidecar_digest,
        current_source_sha256=current_digest,
        active_session_holds_file=session_active_for_path,
    )
    return decision.branch


__all__ = ["ShaSyncDecision", "resolve_sha_sync"]
