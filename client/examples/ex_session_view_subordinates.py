#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_session_view_subordinates — live-server demo of ``session_view`` and
    ``subordinate_session_*`` via ``FileSessionClient``.

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/ai_editor_repository
    source .venv/bin/activate
    casmgr --config config.json start
    python client/examples/ex_session_view_subordinates.py

================================================================================
DESCRIPTION
================================================================================
Integration driver for the session aggregation and subordinate-link APIs added
alongside ``session_delete`` ``force`` semantics:

* ``view_session`` — locked files grouped by project + linked subordinates
* ``create/get/update/delete/list_subordinate_session(s)``
* safe ``delete_session`` vs ``force=True`` when subordinates exist

Exit **0** only when every case passes against the running daemon.

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

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
        "CodeAnalysisAsyncClient.file_sessions",
        "CodeAnalysisAsyncClient.call",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "FileSessionClient.create_session",
        "FileSessionClient.delete_session",
        "FileSessionClient.view_session",
        "FileSessionClient.create_subordinate_session",
        "FileSessionClient.get_subordinate_session",
        "FileSessionClient.update_subordinate_session",
        "FileSessionClient.delete_subordinate_session",
        "FileSessionClient.list_subordinate_sessions",
        "FileSessionClient.lock_file",
        "FileSessionClient.unlock_file",
    }
)

CaseFn = Callable[[], Awaitable[None]]


@dataclass
class Fixture:
    project_id: str
    file_id: str
    file_path: str


@dataclass
class Runner:
    passed: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)

    def ok(self, name: str) -> None:
        self.passed += 1
        print(f"  OK  {name}")

    def fail(self, name: str, exc: BaseException) -> None:
        self.failed += 1
        msg = f"{type(exc).__name__}: {exc}"
        self.errors.append(f"{name}: {msg}")
        print(f"  FAIL {name}: {msg}")


def _error_code(resp: Dict[str, Any]) -> str:
    if resp.get("success") is True:
        return ""
    top = resp.get("code")
    if top is not None and str(top).strip():
        return str(top).strip()
    err = resp.get("error")
    if isinstance(err, dict):
        nested = err.get("code")
        if nested is not None:
            return str(nested).strip()
    return ""


def expect_error(resp: Dict[str, Any], code: str, label: str) -> None:
    if resp.get("success") is True:
        raise AssertionError(f"{label}: expected error {code}, got success {resp!r}")
    got = _error_code(resp)
    if got == code or code in got:
        return
    err = resp.get("error")
    if isinstance(err, dict) and str(err.get("code") or "") == code:
        return
    raise AssertionError(f"{label}: expected code {code!r}, got {got!r}: {resp!r}")


async def discover_fixture(client: CodeAnalysisAsyncClient) -> Fixture:
    resp = await client.call("list_projects", {"include_deleted": False})
    if resp.get("success") is not True:
        raise RuntimeError(f"list_projects failed: {resp!r}")
    data = resp.get("data") or resp
    projects = data.get("projects") or data.get("items") or []
    for proj in projects:
        if not isinstance(proj, dict):
            continue
        pid = str(proj.get("id") or proj.get("project_id") or "").strip()
        if not pid:
            continue
        files_resp = await client.call(
            "list_project_files",
            {"project_id": pid, "limit": 100},
        )
        if files_resp.get("success") is not True:
            continue
        fdata = files_resp.get("data") or files_resp
        for row in fdata.get("files") or []:
            if not isinstance(row, dict):
                continue
            fid = row.get("file_id")
            rel = str(row.get("relative_path") or row.get("path") or "").strip()
            if fid and rel:
                return Fixture(
                    project_id=pid,
                    file_id=str(fid),
                    file_path=rel.replace("\\", "/"),
                )
    raise RuntimeError(
        "No indexed project file found — run update_indexes on a project"
    )


async def run_all() -> int:
    chdir_repo_root()
    cfg = default_config_path()
    runner = Runner()

    async with CodeAnalysisAsyncClient.from_server_config_path(cfg) as client:
        fs = client.file_sessions

        async def case(name: str, fn: CaseFn) -> None:
            try:
                await fn()
                runner.ok(name)
            except Exception as exc:
                runner.fail(name, exc)

        try:
            fx = await discover_fixture(client)
            print(
                f"Fixture: project_id={fx.project_id} file_id={fx.file_id} "
                f"path={fx.file_path!r}"
            )
        except Exception as exc:
            print(f"FATAL: {exc}")
            traceback.print_exc()
            return 1

        async def pos_subordinate_crud_and_view() -> None:
            parent = await fs.create_session("ex_session_view parent")
            try:
                created = await fs.create_subordinate_session(
                    parent,
                    "worker link for view demo",
                )
                server_uuid = str(created.get("server_uuid") or "").strip()
                if not server_uuid:
                    raise AssertionError(f"create missing server_uuid: {created!r}")
                if str(created.get("parent_session_id") or "") != parent:
                    raise AssertionError(f"create parent mismatch: {created!r}")

                got = await fs.get_subordinate_session(parent, server_uuid)
                if str(got.get("parent_session_id") or "") != parent:
                    raise AssertionError(f"get mismatch: {got!r}")

                updated = await fs.update_subordinate_session(
                    parent,
                    server_uuid,
                    "updated comment",
                )
                if str(updated.get("comment") or "") != "updated comment":
                    raise AssertionError(f"update mismatch: {updated!r}")

                listed = await fs.list_subordinate_sessions(parent_session_id=parent)
                links = listed.get("links") or []
                if int(listed.get("count") or 0) < 1:
                    raise AssertionError(f"list empty: {listed!r}")
                servers = {
                    str(row.get("server_uuid"))
                    for row in links
                    if isinstance(row, dict)
                }
                if server_uuid not in servers:
                    raise AssertionError(f"server not in list: {servers!r}")

                await fs.lock_file(parent, fx.project_id, fx.file_id)
                view = await fs.view_session(parent)
                by_proj = view.get("locked_files_by_project") or []
                if not by_proj:
                    raise AssertionError(f"view missing locked files: {view!r}")
                subs = view.get("subordinate_sessions") or []
                sub_servers = {
                    str(row.get("server_uuid")) for row in subs if isinstance(row, dict)
                }
                if server_uuid not in sub_servers:
                    raise AssertionError(f"view missing subordinate: {view!r}")

                await fs.unlock_file(parent, fx.project_id, fx.file_id)
                await fs.delete_subordinate_session(parent, server_uuid)
                empty = await fs.list_subordinate_sessions(parent_session_id=parent)
                if int(empty.get("count") or 0) != 0:
                    raise AssertionError(f"links remain after delete: {empty!r}")
            finally:
                await fs.delete_session(parent, force=True)

        async def neg_delete_parent_with_subordinate_no_force() -> None:
            parent = await fs.create_session("ex_session_view delete guard parent")
            try:
                link = await fs.create_subordinate_session(parent, "guard link")
                server_uuid = str(link.get("server_uuid") or "").strip()
                resp = await client.call(
                    "session_delete",
                    {"session_id": parent, "force": False},
                )
                expect_error(resp, "SESSION_HAS_SUBORDINATES", "delete parent")
                await fs.delete_subordinate_session(parent, server_uuid)
            finally:
                await fs.delete_session(parent, force=True)

        async def pos_force_delete_releases_subordinates() -> None:
            parent = await fs.create_session("ex_session_view force parent")
            await fs.create_subordinate_session(parent, "force link")
            deleted = await fs.delete_session(parent, force=True)
            if deleted.get("deleted") is not True:
                raise AssertionError(deleted)
            if int(deleted.get("released_subordinate_count") or 0) < 1:
                raise AssertionError(
                    f"expected released_subordinate_count >= 1: {deleted!r}"
                )
            resp = await client.call(
                "session_list_file_locks",
                {"session_id": parent},
            )
            expect_error(resp, "SESSION_NOT_FOUND", "parent gone")

        async def neg_view_unknown_session() -> None:
            fake = str(uuid.uuid4())
            resp = await client.call("session_view", {"session_id": fake})
            expect_error(resp, "SESSION_NOT_FOUND", "session_view unknown")

        sections: List[Tuple[str, List[Tuple[str, CaseFn]]]] = [
            (
                "subordinate CRUD + session_view",
                [
                    (
                        "CRUD, view with lock + subordinate",
                        pos_subordinate_crud_and_view,
                    ),
                ],
            ),
            (
                "session_delete force semantics",
                [
                    (
                        "delete parent blocked when subordinates exist",
                        neg_delete_parent_with_subordinate_no_force,
                    ),
                    (
                        "force delete releases subordinate links",
                        pos_force_delete_releases_subordinates,
                    ),
                ],
            ),
            (
                "errors",
                [
                    ("session_view unknown session", neg_view_unknown_session),
                ],
            ),
        ]

        for title, cases in sections:
            print(f"\n== {title} ==")
            for case_name, case_fn in cases:
                await case(case_name, case_fn)

    print(f"\nSummary: {runner.passed} passed, {runner.failed} failed")
    if runner.errors:
        print("\nFailures:")
        for line in runner.errors:
            print(f"  - {line}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="session_view and subordinate_session live examples"
    )
    _ = parser.parse_args()
    try:
        return asyncio.run(run_all())
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
