"""Optional post-write helpers for universal_file_write (verify read-back).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


def verify_ca_readback(
    client: Any,
    *,
    project_id: str,
    file_path: str,
    expected_bytes: bytes,
) -> Dict[str, Any]:
    """Download file from CA without lock and compare to expected bytes."""
    try:
        actual = client.download_without_lock(
            project_id=project_id,
            file_path=file_path,
        )
    except Exception as exc:
        return {
            "verified": False,
            "error": str(exc),
            "expected_length": len(expected_bytes),
            "actual_length": 0,
        }
    return {
        "verified": actual == expected_bytes,
        "expected_length": len(expected_bytes),
        "actual_length": len(actual),
        "error": None if actual == expected_bytes else "read-back bytes differ",
    }
