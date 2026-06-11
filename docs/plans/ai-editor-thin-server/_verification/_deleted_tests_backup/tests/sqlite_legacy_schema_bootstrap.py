"""Single import site for legacy full-schema SQLite DDL used by integration tests.

Opening only ``database_driver_pkg`` + ``sync_schema`` does not reproduce the same
constraints as production for some watcher paths; tests therefore materialize the
database file once with the historical :class:`SchemaComparator` sync path
(:class:`~ai_editor.core.database_driver_pkg.sqlite_proxy_legacy.legacy_sqlite.SQLiteDriver`),
then reopen with the packaged universal driver and RPC clients.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple


def bootstrap_sqlite_schema_paths(
    driver_config: Dict[str, Any],
    *,
    default_backup_dir: str,
) -> Tuple[str, str]:
    """Create DB file and full schema; return ``(db_path, backup_dir)`` for ``create_driver``."""
    from ai_editor.core.database.schema_definition import get_schema_definition
    from ai_editor.core.database_driver_pkg.sqlite_proxy_legacy.legacy_sqlite import (
        SQLiteDriver,
    )

    cfg = driver_config["config"]
    path_str = cfg["path"]
    backup_dir = cfg.get("backup_dir", default_backup_dir)
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)

    driver = SQLiteDriver()
    driver.connect(cfg)
    try:
        driver.sync_schema(get_schema_definition(), backup_path)
    finally:
        driver.disconnect()
    return path_str, str(backup_path.resolve())
