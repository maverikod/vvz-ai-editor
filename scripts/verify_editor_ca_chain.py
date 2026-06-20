#!/usr/bin/env python3
"""Smoke-test: CA project + session → editor open/edit/write → CA read-back.

Uses direct JSON-RPC (same contract as MCP proxy). Run from repo root with venv:

    source .venv/bin/activate
    python scripts/verify_editor_ca_chain.py

Environment (optional):
    AI_EDITOR_CA_HOST, AI_EDITOR_CA_PORT
    AI_EDITOR_HOST, AI_EDITOR_PORT
    AI_EDITOR_WATCH_DIR_ID
    AI_EDITOR_MTLS_DIR — default mtls_certificates/mtls_certificates

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _client(host: str, port: int, mtls_dir: Path) -> JsonRpcClient:
    cert = mtls_dir / "client" / "ai-editor.crt"
    key = mtls_dir / "client" / "ai-editor.key"
    ca = mtls_dir / "ca" / "ca.crt"
    return JsonRpcClient(
        host=host,
        port=port,
        protocol="https",
        cert=str(cert),
        key=str(key),
        ca=str(ca),
        check_hostname=False,
        timeout=120.0,
    )


def _unwrap(resp: Dict[str, Any]) -> Dict[str, Any]:
    if resp.get("success") is False:
        raise RuntimeError(json.dumps(resp, ensure_ascii=False))
    data = resp.get("data")
    if isinstance(data, dict):
        return data
    return resp


async def _call(
    client: JsonRpcClient, command: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    return _unwrap(await client.execute_command(command, params))


async def run_chain(
    *,
    watch_dir_id: str,
    verify_after_upload: bool,
    format_python: bool,
    ca_host: str,
    ca_port: int,
    editor_host: str,
    editor_port: int,
    mtls_dir: Path,
) -> Dict[str, Any]:
    ca = _client(ca_host, ca_port, mtls_dir)
    ed = _client(editor_host, editor_port, mtls_dir)

    pname = f"verify_chain_{uuid.uuid4().hex[:8]}"
    proj = await _call(
        ca,
        "create_project",
        {
            "watch_dir_id": watch_dir_id,
            "project_name": pname,
            "description": "verify_editor_ca_chain",
            "create_venv": False,
            "apply_template": False,
        },
    )
    project_id = proj["project_id"]
    session_id = (await _call(ca, "session_create", {"comment": "verify chain"}))[
        "session_id"
    ]

    file_path = "scripts/verify_chain.txt"
    initial = "verify chain initial\nsecond line\n"
    await _call(
        ed,
        "universal_file_open",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
            "create": True,
            "initial_content": initial,
        },
    )
    await _call(
        ed,
        "universal_file_edit",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
            "operations": [
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "verify chain COMMITTED\n",
                }
            ],
        },
    )
    preview_params: Dict[str, Any] = {
        "project_id": project_id,
        "session_id": session_id,
        "file_path": file_path,
        "write_mode": "preview",
    }
    if format_python:
        preview_params["format_python"] = True
    preview = await _call(ed, "universal_file_write", preview_params)
    if not preview.get("has_changes"):
        raise RuntimeError("preview expected has_changes=true")

    commit_params: Dict[str, Any] = {
        "project_id": project_id,
        "session_id": session_id,
        "file_path": file_path,
        "write_mode": "commit",
    }
    if format_python:
        commit_params["format_python"] = True
    if verify_after_upload:
        commit_params["verify_after_upload"] = True
    commit = await _call(ed, "universal_file_write", commit_params)
    if not commit.get("uploaded"):
        raise RuntimeError(f"commit not uploaded: {commit}")

    if verify_after_upload:
        ca_verify = commit.get("ca_verify") or {}
        if not ca_verify.get("verified"):
            raise RuntimeError(f"ca_verify failed: {ca_verify}")

    await _call(
        ed,
        "universal_file_close",
        {
            "project_id": project_id,
            "session_id": session_id,
            "file_path": file_path,
        },
    )

    lines = await _call(
        ca,
        "get_file_lines",
        {
            "project_id": project_id,
            "file_path": file_path,
            "start_line": 1,
            "end_line": 2,
        },
    )
    got = lines.get("lines") or []
    if got[0] != "verify chain COMMITTED":
        raise RuntimeError(f"CA content mismatch: {got}")

    return {
        "project_id": project_id,
        "session_id": session_id,
        "project_name": pname,
        "file_path": file_path,
        "preview_has_changes": preview.get("has_changes"),
        "commit_uploaded": commit.get("uploaded"),
        "ca_verify": commit.get("ca_verify"),
        "ca_lines": got,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify editor→CA write chain")
    parser.add_argument(
        "--watch-dir-id",
        default=_env("AI_EDITOR_WATCH_DIR_ID", "06259dc1-8383-4424-9123-6044f1721664"),
    )
    parser.add_argument("--verify-after-upload", action="store_true", default=True)
    parser.add_argument(
        "--no-verify-after-upload", action="store_false", dest="verify_after_upload"
    )
    parser.add_argument("--format-python", action="store_true", default=False)
    parser.add_argument(
        "--ca-host", default=_env("AI_EDITOR_CA_HOST", "192.168.254.26")
    )
    parser.add_argument(
        "--ca-port", type=int, default=int(_env("AI_EDITOR_CA_PORT", "15010"))
    )
    parser.add_argument(
        "--editor-host", default=_env("AI_EDITOR_HOST", "192.168.254.28")
    )
    parser.add_argument(
        "--editor-port", type=int, default=int(_env("AI_EDITOR_PORT", "15000"))
    )
    parser.add_argument(
        "--mtls-dir",
        type=Path,
        default=Path(
            _env(
                "AI_EDITOR_MTLS_DIR",
                str(REPO_ROOT / "mtls_certificates/mtls_certificates"),
            )
        ),
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_chain(
            watch_dir_id=args.watch_dir_id,
            verify_after_upload=args.verify_after_upload,
            format_python=args.format_python,
            ca_host=args.ca_host,
            ca_port=args.ca_port,
            editor_host=args.editor_host,
            editor_port=args.editor_port,
            mtls_dir=args.mtls_dir,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("OK: editor→CA chain verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
