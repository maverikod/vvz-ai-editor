#!/usr/bin/env python3
"""
Demo: JsonRpcClient transfer download from one ``files`` row, upload into another.

- Loads ``config.json`` (or ``--config``).
- Loads passwords from ``.env`` next to the config (``load_dotenv_near_config``).
- Reads **real** ``project_id``, source ``file_id``, target ``file_id`` from the DB
  (same project, two distinct indexed paths).
- Download by source id → adapter upload buffer → ``project_file_transfer_upload_save``
  on **target** id (same payload; target path and ``files.id`` differ from source).

**Warning:** the target file on disk is **overwritten**. Prefer a dedicated branch or project.
If the index contains a ``.txt`` / ``.md`` / ``.rst`` / ``.adoc`` file in the same project as
another file, that file is chosen as the target so post-save verification can compare bytes;
otherwise verification only notes Python/JSON/YAML normalization.

HTTP/TLS to the running server is taken from ``config.server`` + ``config.client.ssl``
(paths resolved relative to the repository root).

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


_PLAIN_TEXT_SUFFIXES = (".txt", ".md", ".rst", ".adoc")


def _pick_two_files_from_rows(
    rows: List[Dict[str, Any]],
) -> Tuple[str, str, str, str, str, bool]:
    """Return (project_id, src_id, src_rel, dst_id, dst_rel, strict_byte_verify)."""
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
        "Need at least two distinct file rows with paths in the same project."
    )


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


def _fetch_file_pairs_postgres(
    driver_config: Dict[str, Any],
) -> Tuple[str, str, str, str, str, bool]:
    from ai_editor.core.database_driver_pkg.drivers.postgres import (
        _connect_kwargs_from_config,
    )

    import psycopg

    kwargs = _connect_kwargs_from_config(driver_config)
    conn = psycopg.connect(**kwargs)
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


def _resolve_db_file_pairs(
    config: Dict[str, Any], repo_root: Path
) -> Tuple[str, str, str, str, str, bool]:
    ca = config.get("ai_editor")
    if not isinstance(ca, dict):
        raise ValueError("config.ai_editor missing")

    db_block = ca.get("database")
    if isinstance(db_block, dict):
        driver = db_block.get("driver")
        if isinstance(driver, dict):
            dtype = str(driver.get("type", "")).strip().lower()
            dconf = driver.get("config")
            if dtype == "postgres" and isinstance(dconf, dict):
                return _fetch_file_pairs_postgres(dconf)

    db_path_raw = ca.get("db_path")
    if not db_path_raw:
        raise ValueError("No database.driver in config and no ai_editor.db_path")
    db_path = Path(str(db_path_raw))
    if not db_path.is_absolute():
        db_path = (repo_root / db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    return _fetch_file_pairs_sqlite(db_path)


async def _run_roundtrip(
    *,
    config_path: Path,
    connect_host: str,
    connect_port: Optional[int],
    upload_compression: str,
    timeout: float,
) -> None:
    load_dotenv_near_config(config_path, override=False)
    config = _load_config(config_path)
    repo_root = config_path.resolve().parent

    project_id, src_id, src_rel, dst_id, dst_rel, strict_verify = (
        _resolve_db_file_pairs(config, repo_root)
    )
    print(
        f"DB: project_id={project_id}\n"
        f"  source file_id={src_id} path={src_rel}\n"
        f"  target file_id={dst_id} path={dst_rel}\n"
        f"  strict_byte_verify_after_save={strict_verify}"
    )

    client = _build_jsonrpc_client(
        config,
        repo_root,
        connect_host=connect_host,
        connect_port=connect_port,
        timeout=timeout,
    )

    dl_begin = await client.execute_command(
        "project_file_transfer_download_begin",
        {
            "project_id": project_id,
            "file_id": src_id,
            "compression": "identity",
            "include_backup_history": False,
            "lock_mode": "block_write",
        },
    )
    dl_payload = _unwrap_command_payload(cast(Dict[str, Any], dl_begin))
    transfer_id = str(dl_payload.get("transfer_id") or "")
    if not transfer_id:
        raise RuntimeError(f"No transfer_id in response: {dl_payload!r}")

    with tempfile.TemporaryDirectory() as tmp:
        downloaded = Path(tmp) / "source_payload.bin"
        dlr = await client.download_file(transfer_id, str(downloaded))
        payload = downloaded.read_bytes()
        print(
            f"Downloaded from source: bytes={len(payload)} "
            f"checksum_verified={dlr.checksum_verified}"
        )

        upload_path = Path(tmp) / "payload_for_target.bin"
        upload_path.write_bytes(payload)

        up_receipt = await client.upload_file(
            str(upload_path),
            filename=Path(dst_rel).name,
            compression=upload_compression,
        )
        if not up_receipt.completed:
            raise RuntimeError(f"Upload incomplete: {up_receipt!r}")
        print(
            f"Uploaded buffer transfer_id={up_receipt.transfer_id} "
            f"filename={Path(dst_rel).name!r} compression={upload_compression}"
        )

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
            f"project_file_transfer_upload_save (target) "
            f"changed={save_payload.get('changed')} handler_id={save_payload.get('handler_id')}"
        )

        dl2 = await client.execute_command(
            "project_file_transfer_download_begin",
            {
                "project_id": project_id,
                "file_id": dst_id,
                "compression": "identity",
                "include_backup_history": False,
                "lock_mode": "block_write",
            },
        )
        data2 = _unwrap_command_payload(cast(Dict[str, Any], dl2))
        tid2 = str(data2.get("transfer_id") or "")
        verify_path = Path(tmp) / "after_target_save.bin"
        await client.download_file(tid2, str(verify_path))
        after = verify_path.read_bytes()
        if strict_verify:
            if after != payload:
                raise RuntimeError(
                    "Verification failed: target file content != source payload after save."
                )
        else:
            if after != payload:
                print(
                    "Note: target bytes differ from downloaded payload (expected for "
                    "Python/JSON/YAML handlers that normalize on save). Save completed."
                )
            else:
                print("Target bytes match source payload.")
    print("Round-trip OK (source → target by file_id).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "config.json",
        help="Path to ai-editor config.json (default: repo root)",
    )
    parser.add_argument(
        "--connect-host",
        default="127.0.0.1",
        help="Host for JSON-RPC/TLS (use 127.0.0.1 when server listens on 0.0.0.0)",
    )
    parser.add_argument(
        "--connect-port",
        type=int,
        default=None,
        help="Override server port (default: config.server.port)",
    )
    parser.add_argument(
        "--upload-compression",
        choices=("identity", "gzip"),
        default="identity",
        help="Wire compression for upload transfer",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="HTTP client timeout seconds",
    )
    args = parser.parse_args()
    cfg_path = args.config.expanduser().resolve()
    if not cfg_path.is_file():
        sys.exit(f"Config not found: {cfg_path}")

    asyncio.run(
        _run_roundtrip(
            config_path=cfg_path,
            connect_host=args.connect_host,
            connect_port=args.connect_port,
            upload_compression=args.upload_compression,
            timeout=args.timeout,
        )
    )


if __name__ == "__main__":
    main()
