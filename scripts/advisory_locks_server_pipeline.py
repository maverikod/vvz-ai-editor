#!/usr/bin/env python3
"""
End-to-end pipeline against a **running** ai-editor JSON-RPC server: exercises
commands touched by the advisory-lock / transfer work and inspects SQLite (or
Postgres) for ``runtime_lock_sessions`` and ``file_advisory_lock_leases``.

Loads ``config.json`` (or ``--config``), TLS client settings, and the same DB as
the server: **SQLite** via ``ai_editor.db_path``, or **PostgreSQL** via
``ai_editor.database.driver`` (password from ``password_env`` / ``.env``).

Steps (non-zero exit on first hard failure):
  1. ``list_projects`` — server reachability.
  2. Read daemon ``session_id`` from ``runtime_lock_sessions`` (role=daemon).
  3. DB snapshot: session/lease counts.
  4. ``project_file_advisory_lock_batch`` — mixed success/failure items + lease checks.
  5. ``project_file_transfer_download_begin`` with ``lock_mode=full`` — lease present;
     full ``download_file`` — lease cleared (via adapter hooks).
  6. Optional destructive round-trip: upload + ``project_file_transfer_upload_save``
     (same as adapter demo) with lock params.

**Warning:** step 6 overwrites the target file in the project (see demo).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient

from ai_editor.core.env_loader import load_dotenv_near_config


def _unwrap_command_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("success"):
        err = result.get("error") or result.get("message") or result
        raise RuntimeError(f"Command failed: {err!r}")
    data = result.get("data")
    if isinstance(data, dict):
        return data
    return result


def _load_config(config_path: Path) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("config root must be an object")
    return raw


def _resolve_ssl_path(repo_root: Path, value: Optional[str]) -> Optional[str]:
    if not value or not str(value).strip():
        return None
    p = Path(value)
    if not p.is_absolute():
        p = repo_root / p
    return str(p.resolve())


def _build_jsonrpc_client(
    config: Dict[str, Any],
    repo_root: Path,
    *,
    connect_host: str,
    connect_port: Optional[int],
    timeout: float,
) -> JsonRpcClient:
    srv = config.get("server")
    if not isinstance(srv, dict):
        srv = {}
    protocol = str(srv.get("protocol", "https")).lower()
    port = int(connect_port if connect_port is not None else srv.get("port", 15000))

    client_block = config.get("client")
    if not isinstance(client_block, dict):
        client_block = {}
    ssl_sec = client_block.get("ssl")
    if not isinstance(ssl_sec, dict):
        ssl_sec = {}
    if not any(ssl_sec.get(k) for k in ("cert", "cert_path", "key", "key_path")):
        srv_ssl = srv.get("ssl")
        if isinstance(srv_ssl, dict):
            ssl_sec = srv_ssl

    cert = _resolve_ssl_path(repo_root, ssl_sec.get("cert") or ssl_sec.get("cert_path"))
    key = _resolve_ssl_path(repo_root, ssl_sec.get("key") or ssl_sec.get("key_path"))
    ca = _resolve_ssl_path(repo_root, ssl_sec.get("ca") or ssl_sec.get("ca_path"))

    return JsonRpcClient(
        protocol=protocol,
        host=connect_host,
        port=port,
        cert=cert,
        key=key,
        ca=ca,
        check_hostname=bool(ssl_sec.get("check_hostname", False)),
        timeout=timeout,
    )


@dataclass(frozen=True)
class _DbTarget:
    """SQLite file path or PostgreSQL driver config (same as server)."""

    sqlite_path: Optional[Path] = None
    postgres_config: Optional[Dict[str, Any]] = None

    @property
    def is_postgres(self) -> bool:
        return self.postgres_config is not None


def _resolve_db_target(config: Dict[str, Any], repo_root: Path) -> _DbTarget:
    ca = config.get("ai_editor")
    if not isinstance(ca, dict):
        raise ValueError("config.ai_editor missing")
    db_block = ca.get("database")
    if isinstance(db_block, dict):
        driver = db_block.get("driver")
        if isinstance(driver, dict):
            dtype = str(driver.get("type", "")).strip().lower()
            if dtype == "postgres":
                dconf = driver.get("config")
                if not isinstance(dconf, dict):
                    raise ValueError("database.driver.config required for postgres")
                return _DbTarget(postgres_config=dconf)
    raw = ca.get("db_path")
    if not raw:
        raise ValueError("ai_editor.db_path not set (or use database.driver)")
    p = Path(str(raw))
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {p}")
    return _DbTarget(sqlite_path=p)


def _pg_connect(pg_config: Dict[str, Any]) -> Any:
    import psycopg

    from ai_editor.core.database_driver_pkg.drivers.postgres import (
        _connect_kwargs_from_config,
    )

    return psycopg.connect(**_connect_kwargs_from_config(pg_config))


_PLAIN_TEXT_SUFFIXES = (".txt", ".md", ".rst", ".adoc")


def _pick_two_files_from_rows(
    rows: List[Dict[str, Any]],
) -> Tuple[str, str, str, str, str, bool]:
    by_project: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        pid = str(r.get("project_id") or "").strip()
        fid = str(r.get("id") or "").strip()
        rel = str(r.get("rel") or "").strip()
        if not pid or not fid or not rel:
            continue
        by_project[pid].append({"id": fid, "rel": rel})
    for pid, lst in sorted(by_project.items()):
        if len(lst) < 2:
            continue
        for i, src in enumerate(lst):
            for dst in lst[i + 1 :]:
                if src["id"] == dst["id"]:
                    continue
                dlow = dst["rel"].lower()
                if any(dlow.endswith(s) for s in _PLAIN_TEXT_SUFFIXES):
                    return pid, src["id"], src["rel"], dst["id"], dst["rel"], True
                slow = src["rel"].lower()
                if any(slow.endswith(s) for s in _PLAIN_TEXT_SUFFIXES):
                    return pid, dst["id"], dst["rel"], src["id"], src["rel"], True
        a, b = lst[0], lst[1]
        if a["id"] != b["id"]:
            return pid, a["id"], a["rel"], b["id"], b["rel"], False
    raise RuntimeError(
        "Need at least two distinct indexed files in the same project (see files table)."
    )


def _fetch_file_pairs_postgres(
    pg_config: Dict[str, Any],
) -> Tuple[str, str, str, str, str, bool]:
    conn = _pg_connect(pg_config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text AS id, project_id::text AS project_id,
                       COALESCE(
                         NULLIF(BTRIM(relative_path), ''),
                         NULLIF(BTRIM(path), '')
                       ) AS rel
                FROM files
                WHERE deleted IS NOT TRUE
                  AND COALESCE(
                        NULLIF(BTRIM(relative_path), ''),
                        NULLIF(BTRIM(path), '')
                      ) IS NOT NULL
                ORDER BY project_id, rel
                """
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
    return _pick_two_files_from_rows(rows)


def _fetch_file_pairs_sqlite(db_path: Path) -> Tuple[str, str, str, str, str, bool]:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, project_id,
                   COALESCE(NULLIF(TRIM(relative_path), ''), NULLIF(TRIM(path), '')) AS rel
            FROM files
            WHERE COALESCE(deleted, 0) = 0
              AND COALESCE(NULLIF(TRIM(relative_path), ''), NULLIF(TRIM(path), '')) IS NOT NULL
            ORDER BY project_id, rel
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return _pick_two_files_from_rows(rows)


def _sqlite_any_session_id(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT session_id FROM runtime_lock_sessions
            ORDER BY CASE WHEN role = 'daemon' THEN 0 ELSE 1 END, started_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise RuntimeError(
            "No rows in runtime_lock_sessions. Start the server against this DB first."
        )
    return str(row[0]).strip()


def _sqlite_db_snapshot(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        n_sess = conn.execute("SELECT COUNT(*) FROM runtime_lock_sessions").fetchone()[
            0
        ]
        n_lease = conn.execute(
            "SELECT COUNT(*) FROM file_advisory_lock_leases"
        ).fetchone()[0]
        daemons = conn.execute(
            "SELECT session_id, pid, role FROM runtime_lock_sessions WHERE role='daemon'"
        ).fetchall()
    finally:
        conn.close()
    return {
        "runtime_lock_sessions": int(n_sess),
        "file_advisory_lock_leases": int(n_lease),
        "daemon_rows": [
            {"session_id": r[0], "pid": r[1], "role": r[2]} for r in daemons
        ],
    }


def _sqlite_lease_count(
    db_path: Path, *, project_id: str, file_path: str, session_id: Optional[str] = None
) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        if session_id:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM file_advisory_lock_leases
                WHERE project_id = ? AND file_path = ? AND session_id = ?
                """,
                (project_id, file_path, session_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM file_advisory_lock_leases
                WHERE project_id = ? AND file_path = ?
                """,
                (project_id, file_path),
            ).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def _pg_any_session_id(pg_config: Dict[str, Any]) -> str:
    conn = _pg_connect(pg_config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id FROM runtime_lock_sessions
                ORDER BY CASE WHEN role = 'daemon' THEN 0 ELSE 1 END, started_at DESC NULLS LAST
                LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise RuntimeError(
            "No rows in runtime_lock_sessions. Start the server against this DB first."
        )
    return str(row[0]).strip()


def _pg_db_snapshot(pg_config: Dict[str, Any]) -> Dict[str, Any]:
    conn = _pg_connect(pg_config)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM runtime_lock_sessions")
            n_sess = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM file_advisory_lock_leases")
            n_lease = cur.fetchone()[0]
            cur.execute(
                "SELECT session_id, pid, role FROM runtime_lock_sessions WHERE role = 'daemon'"
            )
            daemons = cur.fetchall()
    finally:
        conn.close()
    return {
        "runtime_lock_sessions": int(n_sess),
        "file_advisory_lock_leases": int(n_lease),
        "daemon_rows": [
            {
                "session_id": str(r[0]),
                "pid": int(r[1]) if r[1] is not None else None,
                "role": str(r[2]),
            }
            for r in daemons
        ],
    }


def _pg_lease_count(
    pg_config: Dict[str, Any],
    *,
    project_id: str,
    file_path: str,
    session_id: Optional[str] = None,
) -> int:
    conn = _pg_connect(pg_config)
    try:
        with conn.cursor() as cur:
            if session_id:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM file_advisory_lock_leases
                    WHERE project_id = %s AND file_path = %s AND session_id = %s
                    """,
                    (project_id, file_path, session_id),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM file_advisory_lock_leases
                    WHERE project_id = %s AND file_path = %s
                    """,
                    (project_id, file_path),
                )
            row = cur.fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def _fetch_file_pairs(db: _DbTarget) -> Tuple[str, str, str, str, str, bool]:
    if db.is_postgres:
        assert db.postgres_config is not None
        return _fetch_file_pairs_postgres(db.postgres_config)
    assert db.sqlite_path is not None
    return _fetch_file_pairs_sqlite(db.sqlite_path)


def _any_session_id(db: _DbTarget) -> str:
    if db.is_postgres:
        assert db.postgres_config is not None
        return _pg_any_session_id(db.postgres_config)
    assert db.sqlite_path is not None
    return _sqlite_any_session_id(db.sqlite_path)


def _db_snapshot(db: _DbTarget) -> Dict[str, Any]:
    if db.is_postgres:
        assert db.postgres_config is not None
        return _pg_db_snapshot(db.postgres_config)
    assert db.sqlite_path is not None
    return _sqlite_db_snapshot(db.sqlite_path)


def _lease_count(
    db: _DbTarget,
    *,
    project_id: str,
    file_path: str,
    session_id: Optional[str] = None,
) -> int:
    if db.is_postgres:
        assert db.postgres_config is not None
        return _pg_lease_count(
            db.postgres_config,
            project_id=project_id,
            file_path=file_path,
            session_id=session_id,
        )
    assert db.sqlite_path is not None
    return _sqlite_lease_count(
        db.sqlite_path,
        project_id=project_id,
        file_path=file_path,
        session_id=session_id,
    )


async def _run_pipeline(
    *,
    config_path: Path,
    connect_host: str,
    connect_port: Optional[int],
    timeout: float,
    skip_transfer_roundtrip: bool,
    upload_compression: str,
    allow_foreign_session: bool,
) -> None:
    load_dotenv_near_config(config_path, override=False)
    config = _load_config(config_path)
    repo_root = config_path.resolve().parent

    db = _resolve_db_target(config, repo_root)
    if db.is_postgres:
        print("Using PostgreSQL (config.ai_editor.database.driver)")
    else:
        print(f"Using SQLite DB: {db.sqlite_path}")

    snap0 = _db_snapshot(db)
    print(f"DB snapshot (start): {json.dumps(snap0, indent=2)}")
    db_probe_sid = _any_session_id(db)
    print(f"DB session_id (probe, prefer daemon): {db_probe_sid}")

    project_id, src_id, src_rel, dst_id, dst_rel, _strict = _fetch_file_pairs(db)
    print(
        f"Files: project_id={project_id}\n"
        f"  source id={src_id} path={src_rel}\n"
        f"  target id={dst_id} path={dst_rel}"
    )

    client = _build_jsonrpc_client(
        config,
        repo_root,
        connect_host=connect_host,
        connect_port=connect_port,
        timeout=timeout,
    )

    lp = await client.execute_command("list_projects", {"include_deleted": False})
    lp_data = _unwrap_command_payload(cast(Dict[str, Any], lp))
    projects = lp_data.get("projects") or lp_data.get("items") or []
    if isinstance(projects, list):
        pids = {
            str(p.get("id") or p.get("project_id") or "")
            for p in projects
            if isinstance(p, dict)
        }
        if project_id not in pids:
            print(
                f"Warning: project_id {project_id} not in list_projects result keys {pids!r}"
            )
    print("list_projects: OK")

    # Resolve the server's in-process session id (matches batch enforcement).
    probe = await client.execute_command(
        "project_file_advisory_lock_batch",
        {
            "allow_foreign_session": True,
            "items": [
                {
                    "session_id": db_probe_sid,
                    "project_id": project_id,
                    "file_path": "nonexistent_probe_unlock_only.py",
                    "action": "unlock",
                },
            ],
        },
    )
    probe_data = _unwrap_command_payload(cast(Dict[str, Any], probe))
    server_sid = str(probe_data.get("current_session_id") or "").strip()
    if not server_sid:
        raise RuntimeError("batch response missing current_session_id")
    print(f"Server current_session_id (from batch): {server_sid}")
    eff_allow_foreign = bool(allow_foreign_session) or (server_sid != db_probe_sid)
    if eff_allow_foreign and not allow_foreign_session:
        print(
            "Auto-enabling effective allow_foreign_session for batch items "
            "(probe session_id differs from server's in-process session)."
        )
    batch_sid = server_sid

    # --- Batch advisory lock ---
    batch_raw = await client.execute_command(
        "project_file_advisory_lock_batch",
        {
            "allow_foreign_session": eff_allow_foreign,
            "items": [
                {
                    "session_id": batch_sid,
                    "project_id": project_id,
                    "file_path": "nonexistent_pipeline_lock_path_zz99.py",
                    "action": "unlock",
                },
                {
                    "session_id": batch_sid,
                    "project_id": project_id,
                    "file_path": "nonexistent_pipeline_lock_path_zz99.py",
                    "action": "lock",
                    "lock_mode": "full",
                },
                {
                    "session_id": batch_sid,
                    "project_id": project_id,
                    "file_path": src_rel,
                    "action": "lock",
                    "lock_mode": "block_write",
                },
            ],
        },
    )
    batch = _unwrap_command_payload(cast(Dict[str, Any], batch_raw))
    results = batch.get("results") or []
    assert len(results) == 3, results
    assert results[0].get("ok") is True, results[0]
    assert results[1].get("ok") is False, results[1]
    assert results[2].get("ok") is True, results[2]
    n_lease_src = _lease_count(
        db, project_id=project_id, file_path=src_rel, session_id=batch_sid
    )
    if n_lease_src < 1:
        raise RuntimeError(f"Expected lease row for {src_rel}, got count={n_lease_src}")
    print(
        f"project_file_advisory_lock_batch: OK "
        f"(partial failure as expected); leases on source path={n_lease_src}"
    )

    batch_unlock = await client.execute_command(
        "project_file_advisory_lock_batch",
        {
            "allow_foreign_session": eff_allow_foreign,
            "items": [
                {
                    "session_id": batch_sid,
                    "project_id": project_id,
                    "file_path": src_rel,
                    "action": "unlock",
                },
            ],
        },
    )
    bu = _unwrap_command_payload(cast(Dict[str, Any], batch_unlock))
    assert bu.get("results", [{}])[0].get("ok") is True, bu
    n_after = _lease_count(
        db, project_id=project_id, file_path=src_rel, session_id=batch_sid
    )
    if n_after != 0:
        raise RuntimeError(f"Expected 0 leases after unlock, got {n_after}")
    print("project_file_advisory_lock_batch unlock + DB clear: OK")

    # --- Transfer download with lock ---
    dl_begin = await client.execute_command(
        "project_file_transfer_download_begin",
        {
            "project_id": project_id,
            "file_id": src_id,
            "compression": "identity",
            "include_backup_history": False,
            "lock_mode": "full",
        },
    )
    dl_payload = _unwrap_command_payload(cast(Dict[str, Any], dl_begin))
    transfer_id = str(dl_payload.get("transfer_id") or "")
    if not transfer_id:
        raise RuntimeError("download_begin: no transfer_id")
    lock_sid = str(dl_payload.get("lock_session_id") or server_sid).strip()
    n_lease_dl = _lease_count(
        db,
        project_id=project_id,
        file_path=src_rel,
        session_id=str(lock_sid),
    )
    if n_lease_dl < 1:
        raise RuntimeError(
            f"After download_begin with lock, expected lease for {src_rel}, got {n_lease_dl}"
        )
    print(
        f"project_file_transfer_download_begin (lock_mode=full): OK "
        f"transfer_id={transfer_id} lease_rows={n_lease_dl}"
    )

    with tempfile.TemporaryDirectory() as tmp:
        downloaded = Path(tmp) / "locked_dl.bin"
        dlr = await client.download_file(transfer_id, str(downloaded))
        print(
            f"download_file: bytes={downloaded.stat().st_size} "
            f"checksum_verified={dlr.checksum_verified}"
        )

    n_lease_after_dl = _lease_count(
        db,
        project_id=project_id,
        file_path=src_rel,
        session_id=str(lock_sid),
    )
    if n_lease_after_dl != 0:
        raise RuntimeError(
            f"After full download, expected lease released; still {n_lease_after_dl} row(s)"
        )
    print("Transfer download lock released after last chunk: OK")

    if skip_transfer_roundtrip:
        print("Skipping upload/save round-trip (--skip-transfer-roundtrip).")
        snap1 = _db_snapshot(db)
        print(f"DB snapshot (end): {json.dumps(snap1, indent=2)}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        dl2 = await client.execute_command(
            "project_file_transfer_download_begin",
            {
                "project_id": project_id,
                "file_id": src_id,
                "compression": "identity",
                "include_backup_history": False,
                "lock_mode": "block_write",
            },
        )
        pl = _unwrap_command_payload(cast(Dict[str, Any], dl2))
        tid0 = str(pl.get("transfer_id") or "")
        p_src = Path(tmp) / "src.bin"
        await client.download_file(tid0, str(p_src))
        payload = p_src.read_bytes()

        up_receipt = await client.upload_file(
            str(p_src),
            filename=Path(dst_rel).name,
            compression=upload_compression,
        )
        if not up_receipt.completed:
            raise RuntimeError(f"Upload incomplete: {up_receipt!r}")

        save_raw = await client.execute_command(
            "project_file_transfer_upload_save",
            {
                "project_id": project_id,
                "file_id": dst_id,
                "transfer_id": up_receipt.transfer_id,
                "backup": True,
                "dry_run": False,
                "unlock_after_write": True,
                "lock_mode": "full",
            },
        )
        save_payload = _unwrap_command_payload(cast(Dict[str, Any], save_raw))
        print(
            f"project_file_transfer_upload_save: changed={save_payload.get('changed')} "
            f"lock_released={save_payload.get('lock_released')}"
        )

    snap1 = _db_snapshot(db)
    print(f"DB snapshot (end): {json.dumps(snap1, indent=2)}")
    print("Full pipeline OK.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "config.json",
        help="Path to ai-editor config.json",
    )
    parser.add_argument(
        "--connect-host",
        default="127.0.0.1",
        help="JSON-RPC host (use 127.0.0.1 when server listens on 0.0.0.0)",
    )
    parser.add_argument(
        "--connect-port",
        type=int,
        default=None,
        help="Override server port",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="HTTP client timeout seconds",
    )
    parser.add_argument(
        "--skip-transfer-roundtrip",
        action="store_true",
        help="Do not run upload + project_file_transfer_upload_save (avoids overwriting target).",
    )
    parser.add_argument(
        "--allow-foreign-session",
        action="store_true",
        help=(
            "Pass allow_foreign_session=true to project_file_advisory_lock_batch "
            "(use if session_id from DB does not match the server's in-process session)."
        ),
    )
    parser.add_argument(
        "--upload-compression",
        choices=("identity", "gzip"),
        default="identity",
        help="Wire compression for upload (when round-trip enabled)",
    )
    args = parser.parse_args()
    cfg_path = args.config.expanduser().resolve()
    if not cfg_path.is_file():
        sys.exit(f"Config not found: {cfg_path}")

    asyncio.run(
        _run_pipeline(
            config_path=cfg_path,
            connect_host=args.connect_host,
            connect_port=args.connect_port,
            timeout=args.timeout,
            skip_transfer_roundtrip=args.skip_transfer_roundtrip,
            upload_compression=args.upload_compression,
            allow_foreign_session=args.allow_foreign_session,
        )
    )


if __name__ == "__main__":
    main()
