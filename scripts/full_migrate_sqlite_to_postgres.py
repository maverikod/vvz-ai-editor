#!/usr/bin/env python3
"""
Полный перенос базы ai_editor из SQLite в PostgreSQL.

Шаги (по флагам):
  --create-database   создать целевую БД, если её нет (подключение к maintenance DB);
  --reset-target      очистить схему public (DROP SCHEMA CASCADE) перед загрузкой;
  затем DDL + копирование данных + сверка COUNT(*) по таблицам.

FAISS-файлы data/<project_id>.bin не копируются в БД — остаются на диске;
при неизменном каталоге data/ векторный поиск продолжит их использовать.

Требуется: pip install -e . или pip install 'psycopg[binary]>=3.1'

Примеры:
  .venv/bin/python scripts/full_migrate_sqlite_to_postgres.py \\
    --sqlite data/ai_editor.db \\
    --dbname ai_editor --user postgres --password postgres \\
    --create-database --reset-target

  .venv/bin/python scripts/full_migrate_sqlite_to_postgres.py \\
    --sqlite data/ai_editor.db \\
    --dsn "postgresql://postgres:postgres@127.0.0.1:5432/postgres" \\
    --reset-target

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    parser = argparse.ArgumentParser(
        description="Full SQLite → PostgreSQL migration for ai_editor"
    )
    parser.add_argument(
        "--sqlite",
        required=True,
        help="Путь к SQLite .db (например data/ai_editor.db)",
    )
    parser.add_argument(
        "--dsn", default=None, help="PostgreSQL URI (конфликтует с --create-database)"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default="postgres")
    parser.add_argument("--user", default="postgres")
    parser.add_argument(
        "--password",
        default="",
        help="Пароль PostgreSQL; если пусто — из переменной AI_EDITOR_POSTGRES_PASSWORD (после загрузки .env)",
    )
    parser.add_argument(
        "--maintenance-dbname",
        default="postgres",
        help="БД для CREATE DATABASE (если используется --create-database)",
    )
    parser.add_argument(
        "--create-database",
        action="store_true",
        help="Создать --dbname на сервере, если отсутствует",
    )
    parser.add_argument(
        "--reset-target",
        action="store_true",
        help="Перед загрузкой выполнить DROP SCHEMA public CASCADE",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Только DDL (без копирования строк)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Не сравнивать COUNT(*) после загрузки",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Логировать шаги в stderr",
    )
    args = parser.parse_args()

    from ai_editor.core.env_loader import load_dotenv_near_config

    load_dotenv_near_config(root / "config.json")

    password = args.password or os.environ.get("AI_EDITOR_POSTGRES_PASSWORD", "")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    try:
        import psycopg  # noqa: F401
    except ImportError:
        print(
            "Ошибка: установите psycopg: pip install -e . или pip install 'psycopg[binary]>=3.1'",
            file=sys.stderr,
        )
        return 2

    from ai_editor.core.database.migrate_sqlite_to_postgres_full import (
        run_full_migration,
    )

    sqlite_path = Path(args.sqlite).resolve()
    if not sqlite_path.is_file():
        print(f"Файл SQLite не найден: {sqlite_path}", file=sys.stderr)
        return 2

    try:
        result = run_full_migration(
            sqlite_path,
            dsn=args.dsn,
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=password,
            create_database=args.create_database,
            reset_target_schema=args.reset_target,
            schema_only=args.schema_only,
            verify=not args.no_verify,
            maintenance_dbname=args.maintenance_dbname,
        )
    except Exception as e:
        print(f"Ошибка миграции: {e}", file=sys.stderr)
        if args.verbose:
            logging.exception("migrate")
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    ver = result.get("verification")
    if ver and not ver.get("ok"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
