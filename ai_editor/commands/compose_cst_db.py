"""
No-op DB backup helpers for CST compose when local database is absent.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def backup_file_data(database: Any, file_id: Any) -> Optional[Dict[str, Any]]:
    if database is None:
        return None
    raise RuntimeError("Local database backup is not available in file-editing mode")


def delete_file_data(
    database: Any,
    file_id: Any,
    transaction_id: Optional[str] = None,
) -> None:
    if database is None:
        return
    raise RuntimeError("Local database delete is not available in file-editing mode")


def restore_file_data(database: Any, file_id: Any, backup_data: Dict[str, Any]) -> None:
    if database is None:
        return
    raise RuntimeError("Local database restore is not available in file-editing mode")
