"""
Emit shell exports for ``setup_postgres_ai_editor_db.sh``.

Reuses project helpers:
  - :func:`ai_editor.core.env_loader.load_dotenv_near_config` (same as server / CLI)
  - :func:`ai_editor.core.postgres_cli_backup.load_postgres_cli_config` (``password``,
    ``password_env``, host, port, dbname, user from driver config)

Superuser credentials for ``psql`` (CREATE DATABASE / ROLE) are not in the driver model;
they are read from the environment after ``.env`` is loaded (see script header in ``.sh``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import sys
from typing import Any, Mapping


def _q(val: Any) -> str:
    return shlex.quote("" if val is None else str(val))


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


def _merge_env_overrides(dc: dict[str, Any]) -> dict[str, Any]:
    """Env-first overrides for the same keys the app uses (see postgres driver)."""
    if os.environ.get("AI_EDITOR_POSTGRES_USER"):
        dc["user"] = os.environ["AI_EDITOR_POSTGRES_USER"].strip()
    elif os.environ.get("AI_EDITOR_DB_USER"):
        dc["user"] = os.environ["AI_EDITOR_DB_USER"].strip()
    elif os.environ.get("AI_EDITOR_DB_ROLE"):
        dc["user"] = os.environ["AI_EDITOR_DB_ROLE"].strip()

    pw_direct = os.environ.get("AI_EDITOR_POSTGRES_PASSWORD") or os.environ.get(
        "AI_EDITOR_DB_PASSWORD"
    )
    if pw_direct:
        dc["password"] = pw_direct

    if os.environ.get("PGHOST"):
        dc["host"] = os.environ["PGHOST"].strip()
    if os.environ.get("PGPORT"):
        dc["port"] = os.environ["PGPORT"].strip()
    if os.environ.get("AI_EDITOR_DB_NAME"):
        dc["dbname"] = os.environ["AI_EDITOR_DB_NAME"].strip()
    return dc


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: setup_postgres_ai_editor_credentials.py "
            "<config.json> <repo_root>",
            file=sys.stderr,
        )
        return 2

    config_path = pathlib.Path(sys.argv[1]).resolve()
    repo_root = pathlib.Path(sys.argv[2]).resolve()

    if not config_path.is_file():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 2

    sr = str(repo_root)
    if sr not in sys.path:
        sys.path.insert(0, sr)

    from ai_editor.core.env_loader import load_dotenv_near_config
    from ai_editor.core.postgres_cli_backup import (
        PostgresCliBackupError,
        load_postgres_cli_config,
    )

    load_dotenv_near_config(config_path)

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    dc = _merge_env_overrides(_driver_config_from_json(cfg))

    try:
        cli = load_postgres_cli_config(dc)
    except PostgresCliBackupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    admin_pass = (
        os.environ.get("POSTGRES_SUPERUSER_PASSWORD")
        or os.environ.get("POSTGRES_ADMIN_PASSWORD")
        or os.environ.get("POSTGRES_PASSWORD")
        or os.environ.get("PGPASSWORD")
        or ""
    )
    admin_user = (
        os.environ.get("POSTGRES_SUPERUSER_USER")
        or os.environ.get("PGUSER")
        or "postgres"
    )

    print(f"export SETUP_PG_CONFIG_PATH={_q(str(config_path))}")
    print(f"export SETUP_PG_SUPER_USER={_q(admin_user)}")
    print(f"export SETUP_PG_SUPER_PASS={_q(admin_pass)}")
    print(f"export SETUP_PG_APP_USER={_q(cli.user)}")
    print(f"export SETUP_PG_APP_PASS={_q(cli.password)}")
    print(f"export SETUP_PG_DBNAME={_q(cli.dbname)}")
    print(f"export SETUP_PG_HOST={_q(cli.host)}")
    print(f"export SETUP_PG_PORT={_q(str(cli.port))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
