"""
Portable SQL predicates for SQLite and PostgreSQL.

Boolean columns (``files.deleted``, ``files.has_docstring``, ``projects.deleted``)
are often INTEGER 0/1 in SQLite and native BOOLEAN in PostgreSQL. Comparisons such
as ``deleted = 0`` or ``has_docstring = 1`` fail on PostgreSQL
(``operator does not exist: boolean = integer``). Use ``IS TRUE`` / ``IS NOT TRUE``
with ``OR ... IS NULL`` where legacy rows may have NULL.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

# --- files.deleted / projects.deleted: "active" (not soft-deleted) ---
WHERE_FILES_ACTIVE = "(deleted IS NOT TRUE OR deleted IS NULL)"
WHERE_FILES_ACTIVE_F = "(f.deleted IS NOT TRUE OR f.deleted IS NULL)"
WHERE_FILES_ACTIVE_P = "(p.deleted IS NOT TRUE OR p.deleted IS NULL)"

# --- soft-deleted row (trash) ---
WHERE_FILES_TRASHED = "deleted IS TRUE"
WHERE_PROJECTS_TRASHED = "deleted IS TRUE"

# --- projects.deleted: not soft-deleted (active project row) ---
WHERE_PROJECTS_ACTIVE = "(deleted IS NOT TRUE OR deleted IS NULL)"
WHERE_PROJECTS_ACTIVE_P = "(p.deleted IS NOT TRUE OR p.deleted IS NULL)"

# --- files.has_docstring ---
WHERE_HAS_DOCSTRING = "has_docstring IS TRUE"
WHERE_HAS_DOCSTRING_F = "f.has_docstring IS TRUE"

# --- projects.processing_paused (BOOLEAN): "not paused" ---
WHERE_PROCESSING_ACTIVE = "(processing_paused IS NOT TRUE OR processing_paused IS NULL)"
WHERE_PROCESSING_ACTIVE_P = (
    "(p.processing_paused IS NOT TRUE OR p.processing_paused IS NULL)"
)


def sql_julian_timestamp_now_expr(database: Any) -> str:
    """
    SQL fragment for REAL Julian-day style timestamps (``files.updated_at``).

    SQLite uses ``julianday('now')``; PostgreSQL uses ``EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)``
    to match schema defaults mapped in ``schema_sync_sql_postgres``.
    """
    dt = getattr(database, "_driver_type", None)
    if isinstance(dt, str) and dt == "postgres":
        return "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)"
    return "julianday('now')"


def sql_julian_one_day_ago_expr(database: Any) -> str:
    """
    SQL fragment for Julian-day threshold ~24 hours ago (status / analytics).

    SQLite: ``julianday('now', '-1 day')``; PostgreSQL: subtract ``INTERVAL '1 day'``.
    """
    dt = getattr(database, "_driver_type", None)
    if isinstance(dt, str) and dt == "postgres":
        return "EXTRACT(JULIAN FROM (CURRENT_TIMESTAMP - INTERVAL '1 day'))"
    return "julianday('now', '-1 day')"


def database_has_sqlite_code_content_fts(database: Any) -> bool:
    """
    Return True if DML may target SQLite FTS5 ``code_content_fts``.

    PostgreSQL deployments omit that virtual table; callers must skip FTS
    ``DELETE`` statements. Unknown / non-string ``_driver_type`` (e.g. bare mocks)
    defaults to True (SQLite-style).
    """
    driver_type = getattr(database, "_driver_type", None)
    if not isinstance(driver_type, str):
        return True
    return driver_type != "postgres"
