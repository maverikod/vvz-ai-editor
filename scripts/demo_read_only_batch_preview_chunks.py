#!/usr/bin/env python3
"""Demo: read_only_batch with identifier preview (normal) and line pagination (invalid)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_CLIENT = _REPO / "client"
_EXAMPLES = _CLIENT / "examples"
for p in (_CLIENT, _EXAMPLES):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from _common import (
    chdir_repo_root,
    default_config_path,
    ensure_client_package_on_path,
)  # noqa: E402

ensure_client_package_on_path()
chdir_repo_root()

from ai_editor_client import CodeAnalysisAsyncClient  # noqa: E402

PROJECT_ID = json.loads((_REPO / "projectid").read_text(encoding="utf-8"))["id"]
VALID_FILE = "ai_editor/core/config_models.py"
INVALID_FILE = "_tmp_demo_broken_preview.json"


def _data(resp: dict[str, Any]) -> dict[str, Any]:
    if resp.get("success") is not True:
        raise RuntimeError(resp)
    payload = resp.get("data")
    if not isinstance(payload, dict):
        raise RuntimeError(resp)
    return payload


async def main() -> None:
    broken = _REPO / INVALID_FILE
    broken.write_text('{"items": [' + ("1," * 200) + "", encoding="utf-8")
    try:
        async with CodeAnalysisAsyncClient.from_server_config_path(
            default_config_path(), timeout=120.0
        ) as client:
            root = _data(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "file_path": VALID_FILE,
                        "preview_lines": 3,
                    },
                )
            )
            blocks = root.get("blocks") or []
            if not blocks:
                print("No blocks at root; skipping drill-down demo")
                return
            first_ref = blocks[0].get("node_ref")
            batch = _data(
                await client.call(
                    "read_only_batch",
                    {
                        "invocations": [
                            {
                                "command": "universal_file_preview",
                                "params": {
                                    "project_id": PROJECT_ID,
                                    "file_path": VALID_FILE,
                                    "preview_lines": 3,
                                },
                            },
                            {
                                "command": "universal_file_preview",
                                "params": {
                                    "project_id": PROJECT_ID,
                                    "file_path": VALID_FILE,
                                    "node_ref": str(first_ref),
                                    "preview_lines": 5,
                                },
                            },
                        ],
                        "max_response_bytes": 500_000,
                    },
                )
            )
            print("=== Normal: batch identifier preview ===")
            print("inline=", batch.get("inline"))
            for entry in batch.get("results") or []:
                page = (entry.get("result") or {}).get("data") or {}
                print(
                    f"  blocks={len(page.get('blocks') or [])} "
                    f"preview_chunk={'yes' if page.get('preview_chunk') else 'no'}"
                )

            invalid = _data(
                await client.call(
                    "universal_file_preview",
                    {
                        "project_id": PROJECT_ID,
                        "file_path": INVALID_FILE,
                        "max_chars": 300,
                        "preview_offset": 0,
                    },
                )
            )
            print("=== Invalid fallback: line pagination ===")
            print("is_invalid=", invalid.get("focus", {}).get("is_invalid"))
            print("chunk_len=", len(str(invalid.get("preview_chunk") or "")))
            print("next_offset=", invalid.get("preview_next_offset"))
    finally:
        if broken.is_file():
            broken.unlink()


if __name__ == "__main__":
    asyncio.run(main())
