#!/usr/bin/env python3
"""
PostgreSQL bootstrap helpers driven by ``config.json`` and ``.env``.

Subcommands
-----------

1. ``set-superuser-password`` — set the cluster superuser password to
   ``POSTGRES_SUPERUSER_PASSWORD`` from ``.env``. Connects using host/port from
   ``ai_editor.database.driver.config`` and authenticates as superuser
   (see connection password resolution below).

2. ``ensure-app-db`` — read application ``user``, ``dbname``, ``host``, ``port``
   from the same driver config; read the application password from the env var
   named by ``password_env`` (typically ``AI_EDITOR_POSTGRES_PASSWORD``).
   As superuser: create database if missing, create role if missing, set role
   password, grant database and ``public`` schema privileges (same idea as
   ``setup_postgres_ai_editor_db.sh``).

3. ``pull-postgres-docker-image`` — download the Postgres/pgvector image (see
   ``--force``). Does not need ``config.json``.

4. ``run-postgres-docker`` — create or start the container **without** pulling the
   image (run ``pull-postgres-docker-image`` first, or ``pull-and-run-postgres-docker``).
   Container name = ``driver.config.host`` (Docker name, not an IP). Binds
   ``<repo>/data/postgres``, publishes ``driver.config.port`` → container 5432,
   ``--restart=always``, ``--user 1000:1000``. Ensures the user-defined bridge
   network ``smart-assistant`` exists (``docker network create`` if missing). New
   containers join it via ``--network smart-assistant``; already existing containers
   get ``docker network connect smart-assistant`` when needed.    On **new** ``docker run``, adds ``--add-host`` for each line from the host's
   ``/etc/hosts`` whose IP falls into a subnet reported by ``docker network inspect``
   (unless ``--no-docker-hosts``). Additionally, if ``driver.config.host`` is not
   ``0.0.0.0`` and is not a bare IPv4, the host's ``/etc/hosts`` is scanned for that
   name; if found, ``--add-host=<host>:<ip>`` is set so the container uses the same
   address as the host. Existing containers keep their old ``/etc/hosts`` unless you
   recreate with ``--replace``.

5. ``pull-and-run-postgres-docker`` — runs (3) then (4) with the same image options.

Connection password for superuser (before ``ALTER ROLE`` / DDL)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
In order: ``POSTGRES_SUPERUSER_CONNECT_PASSWORD`` (optional, explicit current
login password), then ``POSTGRES_SUPERUSER_PASSWORD``, ``POSTGRES_ADMIN_PASSWORD``,
``POSTGRES_PASSWORD``, ``PGPASSWORD``. To rotate the superuser password, set
``POSTGRES_SUPERUSER_CONNECT_PASSWORD`` to the old password and
``POSTGRES_SUPERUSER_PASSWORD`` to the new one.

Usage (repo root, venv active)::

    python scripts/postgres_setup_from_env_config.py set-superuser-password
    python scripts/postgres_setup_from_env_config.py ensure-app-db
    python scripts/postgres_setup_from_env_config.py ensure-app-db --fix-existing-db-owner
    python scripts/postgres_setup_from_env_config.py pull-postgres-docker-image
    python scripts/postgres_setup_from_env_config.py run-postgres-docker
    python scripts/postgres_setup_from_env_config.py pull-and-run-postgres-docker --replace

Optional: ``--config /path/to/config.json`` (not required for ``pull-postgres-docker-image``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

_IDENT_SAFE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_DOCKER_CONTAINER_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_DEFAULT_PGVECTOR_IMAGE = "pgvector/pgvector:pg16"
_PG_CONTAINER_PORT = 5432
_PG_DATA_MOUNT = "/var/lib/postgresql/data"
_DOCKER_USER = "1000:1000"
# User-defined bridge for cross-service DNS (e.g. smart-assistant stack).
_SMART_ASSISTANT_DOCKER_NETWORK = "smart-assistant"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_config_path(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise SystemExit(f"ERROR: config file not found: {p}")
        return p
    env_p = os.environ.get("CONFIG_PATH") or os.environ.get("CASMGR_CONFIG")
    if env_p:
        p = Path(env_p).expanduser().resolve()
        if p.is_file():
            return p
    root = _repo_root()
    for name in ("config-venv.json", "config.json"):
        cand = root / name
        if cand.is_file():
            return cand.resolve()
    raise SystemExit(
        "ERROR: pass --config, or set CONFIG_PATH / CASMGR_CONFIG, "
        "or place config.json in the repository root."
    )


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
    """Env-first overrides (same keys as ``setup_postgres_ai_editor_credentials.py``)."""
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


def _superuser_connect_password() -> str:
    return (
        os.environ.get("POSTGRES_SUPERUSER_CONNECT_PASSWORD")
        or os.environ.get("POSTGRES_SUPERUSER_PASSWORD")
        or os.environ.get("POSTGRES_ADMIN_PASSWORD")
        or os.environ.get("POSTGRES_PASSWORD")
        or os.environ.get("PGPASSWORD")
        or ""
    )


def _superuser_name() -> str:
    return (
        os.environ.get("POSTGRES_SUPERUSER_USER")
        or os.environ.get("PGUSER")
        or "postgres"
    ).strip()


def _require_non_empty(name: str, value: str) -> str:
    if not (value or "").strip():
        raise SystemExit(f"ERROR: environment variable {name} is empty or unset.")
    return value


def _validate_sql_identifier(label: str, value: str) -> str:
    v = value.strip()
    if not _IDENT_SAFE.match(v):
        raise SystemExit(
            f"ERROR: {label} must match [a-zA-Z_][a-zA-Z0-9_]* (got {value!r})"
        )
    return v


def _require_docker_cli() -> str:
    path = shutil.which("docker")
    if not path:
        raise SystemExit("ERROR: `docker` not found in PATH.")
    return path


def _docker_run(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    _require_docker_cli()
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=capture_output,
        text=True,
    )


def _docker_image_ref(image_arg: str | None) -> str:
    return (
        (image_arg or "").strip()
        or os.environ.get("AI_EDITOR_POSTGRES_DOCKER_IMAGE", "").strip()
        or _DEFAULT_PGVECTOR_IMAGE
    )


def cmd_pull_postgres_docker_image(image: str, *, force: bool) -> None:
    """Download the image. Without ``force``, skip when already present locally."""
    if not force:
        r = _docker_run(["image", "inspect", image], check=False, capture_output=True)
        if r.returncode == 0:
            print(f"Image already present: {image} (use --force to re-pull).")
            return
    print(f"Pulling {image!r} …")
    _docker_run(["pull", image])
    print(f"Pulled {image}")


def _collect_docker_subnets() -> list[ipaddress._BaseNetwork]:
    """IPv4/IPv6 subnets from all Docker networks (``docker network inspect``)."""
    r = _docker_run(["network", "ls", "-q"], capture_output=True, check=True)
    ids = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
    out: list[ipaddress._BaseNetwork] = []
    for nid in ids:
        ir = _docker_run(["network", "inspect", nid], capture_output=True, check=True)
        for net in json.loads(ir.stdout or "[]"):
            ipam = net.get("IPAM") or {}
            for cfg in ipam.get("Config") or []:
                sub = cfg.get("Subnet")
                if not sub:
                    continue
                try:
                    out.append(ipaddress.ip_network(sub, strict=False))
                except ValueError:
                    continue
    return out


def _address_in_docker_subnets(
    addr: ipaddress._BaseAddress, nets: list[ipaddress._BaseNetwork]
) -> bool:
    for net in nets:
        if addr.version != net.version:
            continue
        if addr in net:
            return True
    return False


def _docker_add_host_args_from_etc_hosts(
    hosts_file: Path, subnets: list[ipaddress._BaseNetwork]
) -> list[str]:
    """
    Build ``docker run`` fragments: repeated ``--add-host=name:ip`` for host
    ``/etc/hosts`` lines whose IP lies in a Docker-managed subnet.
    """
    if not subnets:
        print(
            "WARNING: no subnets from `docker network inspect`; "
            "skipping --add-host from /etc/hosts."
        )
        return []
    if not hosts_file.is_file():
        print(f"WARNING: {hosts_file} not found; skipping --add-host imports.")
        return []
    try:
        text = hosts_file.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"WARNING: cannot read {hosts_file}: {e}; skipping --add-host imports.")
        return []

    seen: dict[str, str] = {}
    conflicts: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        ip_s = parts[0]
        try:
            addr = ipaddress.ip_address(ip_s)
        except ValueError:
            continue
        if not _address_in_docker_subnets(addr, subnets):
            continue
        ip_norm = addr.compressed if addr.version == 6 else str(addr)
        for host in parts[1:]:
            if host.startswith("#"):
                break
            if host in ("localhost", "ip6-localhost", "ip6-loopback"):
                continue
            prev = seen.get(host)
            if prev is not None and prev != ip_norm:
                conflicts.append(f"{host!r}: {prev} vs {ip_norm}")
                continue
            if host not in seen:
                seen[host] = ip_norm

    for c in conflicts:
        print(f"WARNING: /etc/hosts conflict for Docker nets, skipped: {c}")

    args: list[str] = []
    for host, ip_norm in sorted(seen.items()):
        args.extend(["--add-host", f"{host}:{ip_norm}"])
    if args:
        print(
            f"Injecting {len(args) // 2} static host(s) from {hosts_file} "
            "(IPs in Docker subnets)."
        )
    return args


def _driver_host_for_etc_hosts_lookup(raw: str) -> str | None:
    """
    Hostname to resolve via the host's ``/etc/hosts`` for ``--add-host``.

    Skips empty, ``0.0.0.0``, and plain IPv4 literals (no name lookup).
    """
    h = (raw or "").strip()
    if not h or h == "0.0.0.0":
        return None
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", h):
        return None
    return h


def _etc_hosts_first_ip_for_hostname(hosts_file: Path, hostname: str) -> str | None:
    """Return the IP from the first ``/etc/hosts`` line listing ``hostname``."""
    if not hostname or not hosts_file.is_file():
        return None
    try:
        text = hosts_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    want = hostname.strip()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if want not in parts[1:]:
            continue
        ip_s = parts[0]
        try:
            addr = ipaddress.ip_address(ip_s)
        except ValueError:
            continue
        return addr.compressed if addr.version == 6 else str(addr)
    return None


def _add_host_flags_hostnames(flat: list[str]) -> set[str]:
    names: set[str] = set()
    i = 0
    while i < len(flat):
        if flat[i] == "--add-host" and i + 1 < len(flat):
            val = flat[i + 1]
            if ":" in val:
                names.add(val.split(":", 1)[0])
            i += 2
        else:
            i += 1
    return names


def _prepend_add_host_for_config_driver_hostname(
    hosts_file: Path,
    driver_host: str,
    flat: list[str],
) -> list[str]:
    """
    If ``driver.config.host`` is a non-``0.0.0.0`` name and appears in
    ``/etc/hosts``, prepend ``--add-host=name:ip`` so the container resolves it
    like the host (unless that name is already listed).
    """
    label = _driver_host_for_etc_hosts_lookup(driver_host)
    if not label:
        return flat
    ip = _etc_hosts_first_ip_for_hostname(hosts_file, label)
    if not ip:
        print(
            f"NOTE: driver.config.host {label!r} has no matching line in {hosts_file}; "
            "skipping --add-host for that name."
        )
        return flat
    if ip in ("127.0.0.1", "::1", "0:0:0:0:0:0:0:1"):
        print(
            f"WARNING: {hosts_file} maps {label!r} to loopback ({ip}); inside the "
            "container that address is the container itself, not the host."
        )
    if label in _add_host_flags_hostnames(flat):
        return flat
    print(
        f"Adding --add-host for driver.config.host from {hosts_file}: {label!r} → {ip}"
    )
    return ["--add-host", f"{label}:{ip}", *flat]


def _container_name_from_driver_host(host: str) -> str:
    h = host.strip()
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", h):
        raise SystemExit(
            "ERROR: driver.config.host looks like an IPv4 address; use a container name "
            "(e.g. ai-editor-db) for run-postgres-docker. Connect from the host via "
            "localhost and driver.config.port."
        )
    if not _DOCKER_CONTAINER_NAME.match(h):
        raise SystemExit(
            f"ERROR: driver.config.host {h!r} is not a valid Docker container name "
            "(pattern: [a-zA-Z0-9][a-zA-Z0-9_.-]*)."
        )
    return h


def _docker_container_running(name: str) -> bool | None:
    """True if running, False if stopped, None if missing."""
    r = _docker_run(
        ["inspect", "-f", "{{.State.Running}}", name],
        check=False,
        capture_output=True,
    )
    if r.returncode != 0:
        return None
    v = (r.stdout or "").strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    return None


def _ensure_docker_network(network: str) -> None:
    """Create a user-defined bridge network if it does not exist."""
    r = _docker_run(["network", "inspect", network], check=False, capture_output=True)
    if r.returncode == 0:
        print(f"Docker network {network!r} already exists.")
        return
    _docker_run(["network", "create", network])
    print(f"Created Docker network {network!r}.")


def _container_attached_to_network(container: str, network: str) -> bool:
    r = _docker_run(
        ["inspect", "-f", "{{json .NetworkSettings.Networks}}", container],
        capture_output=True,
        check=True,
    )
    nets = json.loads(r.stdout or "{}")
    return network in nets


def _docker_network_connect_if_needed(container: str, network: str) -> None:
    if _container_attached_to_network(container, network):
        print(f"Container {container!r} already attached to {network!r}.")
        return
    _docker_run(["network", "connect", network, container])
    print(f"Attached container {container!r} to network {network!r}.")


def cmd_run_postgres_docker(
    config_path: Path,
    *,
    image: str,
    replace: bool,
    sync_hosts: bool = True,
    hosts_file: Path | None = None,
) -> None:
    from ai_editor.core.env_loader import load_dotenv_near_config

    load_dotenv_near_config(config_path)

    super_pw = _require_non_empty(
        "POSTGRES_SUPERUSER_PASSWORD",
        os.environ.get("POSTGRES_SUPERUSER_PASSWORD") or "",
    )

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    dc = _merge_env_overrides(_driver_config_from_json(cfg))

    container = _container_name_from_driver_host(str(dc.get("host") or ""))
    host_port = int(dc.get("port") or _PG_CONTAINER_PORT)
    dbname = _validate_sql_identifier(
        "database name", str(dc.get("dbname") or "postgres")
    )

    data_dir = _repo_root() / "data" / "postgres"
    data_dir.mkdir(parents=True, exist_ok=True)

    _ensure_docker_network(_SMART_ASSISTANT_DOCKER_NETWORK)

    hf = Path(hosts_file or "/etc/hosts")

    if replace:
        _docker_run(["rm", "-f", container], check=False, capture_output=True)
        print(f"Removed existing container {container!r} (--replace).")

    running = _docker_container_running(container)
    if running is True:
        _docker_run(["update", "--restart=always", container])
        _docker_network_connect_if_needed(container, _SMART_ASSISTANT_DOCKER_NETWORK)
        print(
            f"Container {container!r} already running; set restart policy to always. "
            f"Data: {data_dir} → {_PG_DATA_MOUNT}, publish {host_port}:{_PG_CONTAINER_PORT}."
        )
        if sync_hosts:
            print(
                "NOTE: /etc/hosts → --add-host is applied only on new `docker run`; "
                "use --replace to recreate the container if you need updated static hosts."
            )
        return

    if running is False:
        _docker_run(["update", "--restart=always", container])
        _docker_run(["start", container])
        _docker_network_connect_if_needed(container, _SMART_ASSISTANT_DOCKER_NETWORK)
        print(
            f"Started existing container {container!r} (restart=always). "
            f"Data: {data_dir} → {_PG_DATA_MOUNT}, publish {host_port}:{_PG_CONTAINER_PORT}."
        )
        if sync_hosts:
            print(
                "NOTE: /etc/hosts → --add-host is applied only on new `docker run`; "
                "use --replace to recreate the container if you need updated static hosts."
            )
        return

    add_host_args: list[str] = []
    if sync_hosts:
        add_host_args = _docker_add_host_args_from_etc_hosts(
            hf, _collect_docker_subnets()
        )
    add_host_args = _prepend_add_host_for_config_driver_hostname(
        hf,
        str(dc.get("host") or ""),
        add_host_args,
    )

    run_cmd = [
        "run",
        "-d",
        "--name",
        container,
        "--network",
        _SMART_ASSISTANT_DOCKER_NETWORK,
        "--restart",
        "always",
        "--user",
        _DOCKER_USER,
        *add_host_args,
        "-v",
        f"{data_dir.resolve()}:{_PG_DATA_MOUNT}",
        "-p",
        f"{host_port}:{_PG_CONTAINER_PORT}",
        "-e",
        f"POSTGRES_PASSWORD={super_pw}",
        "-e",
        f"POSTGRES_DB={dbname}",
        image,
    ]
    _docker_run(run_cmd)
    print(
        f"Created and started {container!r} from {image!r} as user {_DOCKER_USER} "
        f"on network {_SMART_ASSISTANT_DOCKER_NETWORK!r}. "
        f"Data: {data_dir} → {_PG_DATA_MOUNT}, "
        f"host port {host_port} → container {_PG_CONTAINER_PORT} "
        f"(POSTGRES_DB={dbname!r})."
    )


def _connect_super(
    *,
    host: str,
    port: int,
    password: str,
    user: str,
    sslmode: str | None,
) -> Any:
    import psycopg

    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "dbname": "postgres",
        "user": user,
        "password": password,
        "autocommit": True,
    }
    if sslmode:
        kwargs["sslmode"] = sslmode
    return psycopg.connect(**kwargs)


def cmd_set_superuser_password(config_path: Path) -> None:
    from ai_editor.core.env_loader import load_dotenv_near_config

    load_dotenv_near_config(config_path)

    new_pw = _require_non_empty(
        "POSTGRES_SUPERUSER_PASSWORD",
        os.environ.get("POSTGRES_SUPERUSER_PASSWORD") or "",
    )
    connect_pw = _superuser_connect_password()
    if not connect_pw:
        raise SystemExit(
            "ERROR: need a superuser login password: set POSTGRES_SUPERUSER_CONNECT_PASSWORD "
            "(recommended when rotating) or POSTGRES_SUPERUSER_PASSWORD / POSTGRES_PASSWORD / "
            "PGPASSWORD."
        )

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    dc = _merge_env_overrides(_driver_config_from_json(cfg))
    host = str(dc.get("host") or "127.0.0.1").strip()
    port = int(dc.get("port") or 5432)
    sslmode = dc.get("sslmode")
    sslmode_s = str(sslmode).strip() if sslmode not in (None, "") else None
    superuser = _superuser_name()

    from psycopg import sql

    with _connect_super(
        host=host,
        port=port,
        password=connect_pw,
        user=superuser,
        sslmode=sslmode_s,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(superuser),
                    sql.Literal(new_pw),
                )
            )
    print(f"OK: superuser {superuser!r} password updated (host={host!r} port={port}).")


def cmd_ensure_app_db(config_path: Path, *, fix_existing_db_owner: bool) -> None:
    from ai_editor.core.env_loader import load_dotenv_near_config
    from ai_editor.core.postgres_cli_backup import (
        PostgresCliBackupError,
        load_postgres_cli_config,
    )

    load_dotenv_near_config(config_path)

    connect_pw = _superuser_connect_password()
    if not connect_pw:
        raise SystemExit(
            "ERROR: superuser login password missing. Set POSTGRES_SUPERUSER_PASSWORD or "
            "POSTGRES_PASSWORD / PGPASSWORD (see script docstring)."
        )

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    dc = _merge_env_overrides(_driver_config_from_json(cfg))

    try:
        cli = load_postgres_cli_config(dc)
    except PostgresCliBackupError as e:
        raise SystemExit(f"ERROR: {e}") from e

    app_user = _validate_sql_identifier("database user", cli.user)
    db_name = _validate_sql_identifier("database name", cli.dbname)
    app_pass = cli.password
    if not app_pass:
        raise SystemExit(
            "ERROR: application password is empty after resolving password_env."
        )

    superuser = _validate_sql_identifier("superuser name", _superuser_name())

    from psycopg import sql

    sslmode = cli.sslmode

    with _connect_super(
        host=cli.host,
        port=cli.port,
        password=connect_pw,
        user=superuser,
        sslmode=sslmode,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s",
                (app_user,),
            )
            if cur.fetchone():
                print(f"Role {app_user!r} already exists.")
            else:
                cur.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(app_user),
                        sql.Literal(app_pass),
                    )
                )
                print(f"Created role {app_user!r}.")

            cur.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(app_user),
                    sql.Literal(app_pass),
                )
            )
            print(f"Password set for role {app_user!r}.")

            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (db_name,),
            )
            if cur.fetchone():
                print(f"Database {db_name!r} already exists.")
                if fix_existing_db_owner:
                    cur.execute(
                        sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                            sql.Identifier(db_name),
                            sql.Identifier(app_user),
                        )
                    )
                    print(
                        f"ALTER DATABASE OWNER TO {app_user!r} (fix-existing-db-owner)."
                    )
            else:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(db_name),
                        sql.Identifier(app_user),
                    )
                )
                print(f"Created database {db_name!r} (owner {app_user!r}).")

    with _connect_super(
        host=cli.host,
        port=cli.port,
        password=connect_pw,
        user=superuser,
        sslmode=sslmode,
    ) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(db_name),
                    sql.Identifier(app_user),
                )
            )

    import psycopg

    app_kwargs: dict[str, Any] = {
        "host": cli.host,
        "port": cli.port,
        "dbname": db_name,
        "user": superuser,
        "password": connect_pw,
        "autocommit": True,
    }
    if sslmode:
        app_kwargs["sslmode"] = sslmode

    with psycopg.connect(**app_kwargs) as dbconn:
        with dbconn.cursor() as cur:
            cur.execute(
                sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                    sql.Identifier(app_user)
                )
            )
            cur.execute(
                sql.SQL(
                    "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {}"
                ).format(sql.Identifier(app_user))
            )
            cur.execute(
                sql.SQL(
                    "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(sql.Identifier(app_user))
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT ALL ON TABLES TO {}"
                ).format(sql.Identifier(app_user))
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT ALL ON SEQUENCES TO {}"
                ).format(sql.Identifier(app_user))
            )

    print(
        "OK: grants applied. DSN: "
        f"postgresql://{app_user}:<password>@{cli.host}:{cli.port}/{db_name}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "PostgreSQL: superuser password, app DB bootstrap, and optional Docker pgvector "
            "container from config + .env."
        )
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to config.json (default: CONFIG_PATH / CASMGR_CONFIG / config-venv.json / config.json).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_super = sub.add_parser(
        "set-superuser-password",
        help="ALTER ROLE superuser PASSWORD from POSTGRES_SUPERUSER_PASSWORD.",
    )
    p_super.set_defaults(func=_dispatch_set_super)

    p_app = sub.add_parser(
        "ensure-app-db",
        help="Create DB/role from driver config; password from password_env / .env.",
    )
    p_app.add_argument(
        "--fix-existing-db-owner",
        action="store_true",
        help="If the database already exists, run ALTER DATABASE ... OWNER TO app user.",
    )
    p_app.set_defaults(func=_dispatch_ensure)

    p_pull = sub.add_parser(
        "pull-postgres-docker-image",
        help="docker pull the Postgres/pgvector image (no config.json required).",
    )
    p_pull.add_argument(
        "--image",
        metavar="REF",
        help=(
            "Docker image (default: AI_EDITOR_POSTGRES_DOCKER_IMAGE env or "
            f"{_DEFAULT_PGVECTOR_IMAGE!r})."
        ),
    )
    p_pull.add_argument(
        "--force",
        action="store_true",
        help="Always run docker pull even if the image already exists locally.",
    )
    p_pull.set_defaults(func=_dispatch_pull, needs_config=False)

    p_docker = sub.add_parser(
        "run-postgres-docker",
        help=(
            "Create/start Docker Postgres (pull image separately first). "
            "Adds --add-host from host /etc/hosts for IPs in Docker subnets on new run."
        ),
    )
    p_docker.add_argument(
        "--image",
        metavar="REF",
        help=(
            "Docker image (default: AI_EDITOR_POSTGRES_DOCKER_IMAGE env or "
            f"{_DEFAULT_PGVECTOR_IMAGE!r})."
        ),
    )
    p_docker.add_argument(
        "--replace",
        action="store_true",
        help="Remove existing container with the same name before creating a new one.",
    )
    p_docker.add_argument(
        "--no-docker-hosts",
        action="store_true",
        help=(
            "Skip --add-host lines copied from /etc/hosts for Docker subnets only; "
            "the driver.config.host alias from /etc/hosts (when host is not 0.0.0.0) "
            "is still applied on new runs."
        ),
    )
    p_docker.add_argument(
        "--hosts-file",
        default="/etc/hosts",
        metavar="PATH",
        help="Host file to scan (default: /etc/hosts).",
    )
    p_docker.set_defaults(func=_dispatch_docker)

    p_pull_run = sub.add_parser(
        "pull-and-run-postgres-docker",
        help="pull-postgres-docker-image then run-postgres-docker.",
    )
    p_pull_run.add_argument(
        "--image",
        metavar="REF",
        help=(
            "Docker image (default: AI_EDITOR_POSTGRES_DOCKER_IMAGE env or "
            f"{_DEFAULT_PGVECTOR_IMAGE!r})."
        ),
    )
    p_pull_run.add_argument(
        "--replace",
        action="store_true",
        help="Remove existing container with the same name before creating a new one.",
    )
    p_pull_run.add_argument(
        "--force",
        action="store_true",
        help="Always docker pull before starting the container.",
    )
    p_pull_run.add_argument(
        "--no-docker-hosts",
        action="store_true",
        help=(
            "Skip --add-host lines for Docker subnets only; driver.config.host /etc/hosts "
            "alias still applies when host is not 0.0.0.0."
        ),
    )
    p_pull_run.add_argument(
        "--hosts-file",
        default="/etc/hosts",
        metavar="PATH",
        help="Host file to scan (default: /etc/hosts).",
    )
    p_pull_run.set_defaults(func=_dispatch_pull_and_run)

    args = parser.parse_args()
    config_path: Path | None = None
    if getattr(args, "needs_config", True):
        config_path = _resolve_config_path(args.config)

    sr = str(_repo_root())
    if sr not in sys.path:
        sys.path.insert(0, sr)

    args.func(args, config_path)
    return 0


def _dispatch_set_super(args: argparse.Namespace, config_path: Path | None) -> None:
    if config_path is None:
        raise SystemExit("ERROR: internal: config path required.")
    cmd_set_superuser_password(config_path)


def _dispatch_ensure(args: argparse.Namespace, config_path: Path | None) -> None:
    if config_path is None:
        raise SystemExit("ERROR: internal: config path required.")
    cmd_ensure_app_db(config_path, fix_existing_db_owner=args.fix_existing_db_owner)


def _dispatch_pull(args: argparse.Namespace, config_path: Path | None) -> None:
    del config_path
    image = _docker_image_ref(getattr(args, "image", None))
    cmd_pull_postgres_docker_image(image, force=bool(args.force))


def _dispatch_docker(args: argparse.Namespace, config_path: Path | None) -> None:
    if config_path is None:
        raise SystemExit("ERROR: internal: config path required.")
    image = _docker_image_ref(getattr(args, "image", None))
    cmd_run_postgres_docker(
        config_path,
        image=image,
        replace=args.replace,
        sync_hosts=not args.no_docker_hosts,
        hosts_file=Path(args.hosts_file),
    )


def _dispatch_pull_and_run(args: argparse.Namespace, config_path: Path | None) -> None:
    if config_path is None:
        raise SystemExit("ERROR: internal: config path required.")
    image = _docker_image_ref(getattr(args, "image", None))
    cmd_pull_postgres_docker_image(image, force=bool(args.force))
    cmd_run_postgres_docker(
        config_path,
        image=image,
        replace=args.replace,
        sync_hosts=not args.no_docker_hosts,
        hosts_file=Path(args.hosts_file),
    )


if __name__ == "__main__":
    raise SystemExit(main())
