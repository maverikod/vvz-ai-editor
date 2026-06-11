#!/usr/bin/env python3
"""
Migrate a PostgreSQL database from one server to another using ``pg_dump -Fc`` and
``pg_restore``.

Reads ``ai_editor.database.driver.config`` from two JSON config files (same shape
as the main ``config.json``). Loads ``.env`` next to each config path (and cwd walk)
via :func:`ai_editor.core.env_loader.load_dotenv_near_config`, so ``password_env``
and passwords resolve like the application.

Typical flow:

1. Dump source DB to a custom-format file in ``--work-dir``.
2. Restore into the target DB with ``pg_restore`` (default: ``--clean --if-exists``).

**Warning:** ``--clean`` drops objects in the target database before restore. Use
``--no-clean-restore`` only if you know you need a non-destructive merge.

Usage::

    # Preview (validates configs / password resolution only)
    python scripts/postgres_migrate_server_to_server.py \\
        --source-config /path/source-config.json \\
        --target-config /path/target-config.json \\
        --dry-run

    python scripts/postgres_migrate_server_to_server.py \\
        --source-config /path/source-config.json \\
        --target-config /path/target-config.json

    python scripts/postgres_migrate_server_to_server.py \\
        --source-config source.json --target-config target.json \\
        --work-dir data/pg_migrate_work --keep-dump

Requires ``pg_dump`` and ``pg_restore`` on PATH (or ``pg_dump_path`` /
``pg_restore_path`` in the respective driver configs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


def _driver_config_from_json(cfg: Mapping[str, Any]) -> dict[str, Any]:
    driver = cfg.get("ai_editor", {}).get("database", {}).get("driver") or {}
    dtype = str(driver.get("type") or "").strip().lower()
    if dtype not in ("postgres", "postgresql"):
        raise SystemExit(
            f"ERROR: ai_editor.database.driver.type must be postgres (got {dtype!r})"
        )
    dc = driver.get("config")
    if not isinstance(dc, dict):
        dc = {}
    return dict(dc)


def _load_driver_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"ERROR: config file not found: {path}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return _driver_config_from_json(cfg)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="pg_dump (custom) from source server, pg_restore to target server."
    )
    parser.add_argument(
        "--source-config",
        type=Path,
        required=True,
        help="JSON with ai_editor.database.driver (source PostgreSQL).",
    )
    parser.add_argument(
        "--target-config",
        type=Path,
        required=True,
        help="JSON with ai_editor.database.driver (target PostgreSQL).",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("data/pg_migrate_work"),
        help="Directory for the temporary dump file (created if missing).",
    )
    parser.add_argument(
        "--no-clean-restore",
        action="store_true",
        help="Do not pass --clean/--if-exists to pg_restore (avoid dropping target objects).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=7200.0,
        help="Subprocess timeout in seconds for pg_dump and pg_restore (default: 7200).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only load .env, parse configs, and print connection summaries; no dump/restore.",
    )
    parser.add_argument(
        "--keep-dump",
        action="store_true",
        help="Keep the dump file on disk after a successful restore.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    sr = str(repo_root)
    if sr not in sys.path:
        sys.path.insert(0, sr)

    from ai_editor.core.env_loader import load_dotenv_near_config
    from ai_editor.core.postgres_cli_backup import (
        PostgresCliBackupError,
        backup_postgres_custom_format,
        load_postgres_cli_config,
        restore_postgres_from_custom_dump,
    )

    src_path = args.source_config.expanduser().resolve()
    tgt_path = args.target_config.expanduser().resolve()

    load_dotenv_near_config(src_path)
    load_dotenv_near_config(tgt_path)

    src_dc = _load_driver_config(src_path)
    tgt_dc = _load_driver_config(tgt_path)

    if args.dry_run:

        def _summ(dc: dict[str, Any]) -> str:
            pw = dc.get("password_env") or ("inline" if dc.get("password") else "unset")
            return (
                f"{dc.get('user')}@{dc.get('host')}:{dc.get('port')}/{dc.get('dbname')} "
                f"(password: {pw!r})"
            )

        print("Source:", _summ(src_dc))
        print("Target:", _summ(tgt_dc))
        print("Dry run: no pg_dump / pg_restore executed.")
        return 0

    try:
        src_cli = load_postgres_cli_config(src_dc)
        tgt_cli = load_postgres_cli_config(tgt_dc)
    except PostgresCliBackupError as e:
        raise SystemExit(f"ERROR: {e}") from e

    print("Source:", f"{src_cli.user}@{src_cli.host}:{src_cli.port}/{src_cli.dbname}")
    print("Target:", f"{tgt_cli.user}@{tgt_cli.host}:{tgt_cli.port}/{tgt_cli.dbname}")

    work_dir = args.work_dir.expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    dump_path: Path | None = None
    try:
        print("Running pg_dump on source …")
        (dump_str,) = backup_postgres_custom_format(
            src_dc,
            backup_dir=work_dir,
            timeout_seconds=args.timeout,
        )
        dump_path = Path(dump_str)
        print(f"Dump written: {dump_path} ({dump_path.stat().st_size} bytes)")

        print("Running pg_restore on target …")
        restore_postgres_from_custom_dump(
            tgt_dc,
            dump_path,
            clean=not args.no_clean_restore,
            timeout_seconds=args.timeout,
        )
        print("Restore finished.")
    except PostgresCliBackupError as e:
        raise SystemExit(f"ERROR: {e}") from e
    finally:
        if not args.keep_dump and dump_path is not None and dump_path.is_file():
            dump_path.unlink()
            print(f"Removed temporary dump: {dump_path}")

    if args.keep_dump and dump_path is not None:
        print(f"Kept dump file: {dump_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
