#!/usr/bin/env python3
"""
CLI: copy ai_editor SQLite DB into PostgreSQL (schema + data).

Для полного сценария (CREATE DATABASE, сброс public, сверка строк) см.
scripts/full_migrate_sqlite_to_postgres.py

Requires: psycopg (pip install -e . or pip install 'psycopg[binary]>=3.1')

Example:
  .venv/bin/python scripts/sqlite_to_postgres_migrate.py \\
    --sqlite data/ai_editor.db \\
    --dbname postgres --user postgres --password postgres --host localhost

Or use a DSN:
  --dsn "postgresql://postgres:postgres@localhost:5432/postgres"

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    parser = argparse.ArgumentParser(
        description="Migrate SQLite ai_editor DB to PostgreSQL"
    )
    parser.add_argument(
        "--sqlite",
        required=True,
        help="Path to SQLite .db file (e.g. data/ai_editor.db)",
    )
    parser.add_argument("--dsn", default=None, help="PostgreSQL connection URI")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default=None)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="")
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only create tables/indexes, do not copy rows",
    )
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError:
        print(
            "Error: psycopg is not installed. Run: pip install -e . or pip install 'psycopg[binary]>=3.1'",
            file=sys.stderr,
        )
        return 2

    from ai_editor.core.database.sqlite_to_postgres import (
        migrate_sqlite_to_postgresql,
    )

    sqlite_path = Path(args.sqlite).resolve()
    if not sqlite_path.is_file():
        print(f"Error: SQLite file not found: {sqlite_path}", file=sys.stderr)
        return 2

    if args.dsn:
        conn = psycopg.connect(conninfo=args.dsn)
    else:
        if not args.dbname:
            print("Error: --dbname is required when --dsn is not set", file=sys.stderr)
            return 2
        conn = psycopg.connect(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password,
        )

    try:
        summary = migrate_sqlite_to_postgresql(
            sqlite_path,
            conn,
            create_schema=True,
            copy_data=not args.schema_only,
        )
        print(json.dumps(summary, indent=2, default=str))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
