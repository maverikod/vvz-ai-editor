"""
SQLite DB verification helpers for MCP pipeline tests.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def open_db(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open SQLite database in read-only mode for deterministic test assertions.

    Callers must pass the same path as real server runtime DB, for example:
    `PipelineConfig.get_db_path()`.
    """
    resolved_path = Path(db_path).expanduser().resolve()
    uri = f"file:{resolved_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def query_db(
    db_path: str | Path,
    sql: str,
    params: Sequence[Any] | None = None,
) -> list[sqlite3.Row]:
    """Execute a read-only SQL query and return all rows.

    This helper is intended for `SELECT`-based assertions in tests that verify
    DB side effects after MCP command execution.
    """
    normalized_sql = sql.lstrip()
    if not normalized_sql:
        raise ValueError("SQL query must not be empty")

    first_token = normalized_sql.split(None, maxsplit=1)[0].upper()
    if first_token not in {"SELECT", "WITH", "PRAGMA"}:
        raise ValueError("Only read-only SQL queries are allowed (SELECT/WITH/PRAGMA)")

    query_params: Sequence[Any] = params if params is not None else ()
    with open_db(db_path) as connection:
        cursor = connection.execute(sql, query_params)
        return list(cursor.fetchall())
