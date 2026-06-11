"""
Fresh DB: skip driver migrations before base tables; catalog probe without noisy SELECT.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

_CORE_SCHEMA_TABLES = frozenset(
    {
        "projects",
        "files",
        "code_chunks",
        "issues",
        "functions",
        "methods",
        "classes",
    }
)

_CONNECTION_TIME_TABLES = frozenset(
    {
        "file_advisory_lock_leases",
        "entity_cross_ref",
        "indexing_worker_stats",
        "indexing_errors",
    }
)

_LEGACY_REMOVED_TABLES = frozenset(
    {
        "runtime_lock_sessions",
        "client_sessions",
        "session_file_locks",
        "subordinate_sessions",
        "roles",
        "role_permissions",
        "session_roles",
    }
)


def _user_table_names(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return {r[0] for r in cur.fetchall()}


def test_sqlite_table_exists_false_on_empty_db() -> None:
    mod = pytest.importorskip(
        "ai_editor.core.database_driver_pkg.drivers.sqlite_migrations"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        try:
            assert mod._sqlite_table_exists(conn, "projects") is False
        finally:
            conn.close()


def test_run_all_ensure_skips_core_schema_on_empty_db() -> None:
    """Connection-time ensure_* tables are created; core schema is not bootstrapped."""
    sqlite_migrations = pytest.importorskip(
        "ai_editor.core.database_driver_pkg.drivers.sqlite_migrations"
    )
    sqlite_schema = pytest.importorskip(
        "ai_editor.core.database_driver_pkg.drivers.sqlite_schema"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        try:
            sm = sqlite_schema.SQLiteSchemaManager(conn)
            sqlite_migrations.run_all_ensure(conn, sm, p)
            names = _user_table_names(conn)
            assert _CORE_SCHEMA_TABLES.isdisjoint(names)
            assert _CONNECTION_TIME_TABLES <= names
            assert _LEGACY_REMOVED_TABLES.isdisjoint(names)
        finally:
            conn.close()


def test_run_migrate_schema_probes_without_creating_core_schema() -> None:
    """run_migrate_schema inspects missing tables but only creates connection-time DDL."""
    sqlite_migrations = pytest.importorskip(
        "ai_editor.core.database_driver_pkg.drivers.sqlite_migrations"
    )
    sqlite_schema = pytest.importorskip(
        "ai_editor.core.database_driver_pkg.drivers.sqlite_schema"
    )
    schema_creation_migrate = pytest.importorskip(
        "ai_editor.core.database.schema_creation_migrate"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "e.db"
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        try:
            sm = sqlite_schema.SQLiteSchemaManager(conn)
            schema_creation_migrate.run_migrate_schema(
                sqlite_migrations._SqliteConnMigrateAdapter(conn, sm)
            )
            names = _user_table_names(conn)
            assert _CORE_SCHEMA_TABLES.isdisjoint(names)
            assert {
                "file_advisory_lock_leases",
                "entity_cross_ref",
            } <= names
            assert _LEGACY_REMOVED_TABLES.isdisjoint(names)
        finally:
            conn.close()
