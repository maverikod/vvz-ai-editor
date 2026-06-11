#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_universal_files — live-server demo of ``UniversalFileClient`` (all methods).

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/ai_editor_repository
    source .venv/bin/activate
    aiedmgr --config config.json start
    python client/examples/ex_universal_files.py

================================================================================
DESCRIPTION
================================================================================
Exercises every public method on :class:`ai_editor_client.UniversalFileClient`
against a running daemon. Demonstrates File Workflow (C-009): open → preview →
edit → write → close with one CA Session context.

``session_id`` is the CA Session identifier (C-004) created by the agent
upstream (C-003) before any ``universal_file_*`` call. The same id is passed
into ``open``, ``preview``, ``edit``, ``write``, and ``close``; it is not
sourced from the ``open`` response for subsequent calls.

The edit workflow uses ``write_mode=preview`` and ``close`` without commit so
the on-disk file is unchanged.

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import asyncio
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict

_EXAMPLES = Path(__file__).resolve().parent
_CLIENT = _EXAMPLES.parent
if str(_CLIENT) not in sys.path:
    sys.path.insert(0, str(_CLIENT))

from _common import (  # noqa: E402
    chdir_repo_root,
    default_config_path,
    ensure_client_package_on_path,
)

ensure_client_package_on_path()

from ai_editor_client import CodeAnalysisAsyncClient  # noqa: E402

CLIENT_API_COVERAGE = frozenset(
    {
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.universal_files",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "UniversalFileClient.open",
        "UniversalFileClient.preview",
        "UniversalFileClient.edit",
        "UniversalFileClient.write",
        "UniversalFileClient.close",
    }
)


def _data(resp: Dict[str, Any]) -> Dict[str, Any]:
    inner = resp.get("data")
    return inner if isinstance(inner, dict) else resp


async def _discover_text_file(client: CodeAnalysisAsyncClient) -> tuple[str, str]:
    resp = await client.call("list_projects", {"include_deleted": False})
    if resp.get("success") is not True:
        raise RuntimeError(f"list_projects failed: {resp!r}")
    data = _data(resp)
    for proj in data.get("projects") or data.get("items") or []:
        if not isinstance(proj, dict):
            continue
        pid = str(proj.get("id") or proj.get("project_id") or "").strip()
        if not pid:
            continue
        files_resp = await client.call(
            "list_project_files",
            {"project_id": pid, "limit": 200},
        )
        if files_resp.get("success") is not True:
            continue
        fdata = _data(files_resp)
        for row in fdata.get("files") or []:
            if not isinstance(row, dict):
                continue
            rel = str(row.get("relative_path") or row.get("path") or "").strip()
            if not rel:
                continue
            if Path(rel).suffix.lower() in {".txt", ".md", ".rst", ".adoc"}:
                return pid, rel.replace("\\", "/")
    raise RuntimeError(
        "No .txt/.md file found in any project — add a text file or run update_indexes"
    )


async def run_all() -> int:
    chdir_repo_root()
    cfg = default_config_path()

    async with CodeAnalysisAsyncClient.from_server_config_path(cfg) as client:
        uf = client.universal_files
        # Agent upstream stand-in (C-003): CA session_id from session_create before workflow.
        ca_session_id = f"demo-ca-{uuid.uuid4().hex}"
        project_id, _sample_path = await _discover_text_file(client)
        file_path = f"tmp/client_uf_ex_{uuid.uuid4().hex[:12]}.txt"
        print(f"Fixture: project_id={project_id} file_path={file_path!r}")
        print(f"  ca_session_id={ca_session_id}")

        opened = await uf.open(
            project_id,
            file_path,
            ca_session_id,
            create=True,
            initial_content="line one\nline two\n",
        )
        echoed = str(opened.get("session_id") or "").strip()
        if echoed and echoed != ca_session_id:
            raise AssertionError(
                f"open echoed unexpected session_id: {echoed!r} != {ca_session_id!r}"
            )
        print(f"  open OK session_id={ca_session_id}")

        prev = await uf.preview(project_id, file_path, ca_session_id)
        if not isinstance(prev, dict):
            raise AssertionError(f"preview unexpected: {prev!r}")
        print("  preview OK")

        edited = await uf.edit(
            project_id,
            ca_session_id,
            operations=[
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "# client example preview-only edit\n",
                }
            ],
        )
        if edited.get("success") is False:
            raise AssertionError(f"edit failed: {edited!r}")
        print("  edit OK")

        wr_preview = await uf.write(project_id, ca_session_id, write_mode="preview")
        if wr_preview.get("phase") != "preview" and "diff" not in wr_preview:
            raise AssertionError(f"write preview unexpected: {wr_preview!r}")
        print("  write(preview) OK")

        closed = await uf.close(project_id, ca_session_id)
        if closed.get("success") is not True and closed.get("closed") is not True:
            if closed.get("success") is not False:
                print(f"  close OK: {closed!r}")
            else:
                raise AssertionError(f"close failed: {closed!r}")
        else:
            print("  close OK")

    print("All UniversalFileClient methods exercised.")
    return 0


def main() -> int:
    try:
        return asyncio.run(run_all())
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
