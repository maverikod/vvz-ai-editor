#!/usr/bin/env python3
r"""
================================================================================
NAME
================================================================================
    ex_file_sessions — integration driver for client sessions and file workflows.

================================================================================
SYNOPSIS
================================================================================
::

    cd /path/to/ai_editor_repository
    source .venv/bin/activate
    aiedmgr --config config.json start
    python client/examples/ex_file_sessions.py
    python client/examples/ex_file_sessions.py --skip-transfer

================================================================================
DESCRIPTION
================================================================================
Live-server integration script for ``ai_editor_client.FileSessionClient`` and
``session_management`` MCP commands (``session_*``, ``subordinate_session_*``) plus
transfer/advisory-lock paths that accept ``session_id``.

Covers:

* **Happy paths** — create, list locks, DB lock/unlock (``session_open_file`` /
  ``session_close_file``), advisory batch lock/unlock, optional transfer
  download+upload roundtrip with the same bytes, clean delete.

* **Edge / negative cases** — schema validation (``ClientValidationError``),
  ``SESSION_NOT_FOUND``, ``SESSION_HAS_LOCKS``, ``SESSION_HAS_SUBORDINATES``,
  ``SESSION_ID_REQUIRED`` (when
  ``sessions.show_session_ids=true``), idempotent lock/unlock, double delete,
  operations on deleted sessions, invalid ``stale_threshold_seconds``.

Exit **0** only when every case passes.

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
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

from ai_editor_client import (  # noqa: E402
    ClientValidationError,
    CodeAnalysisAsyncClient,
    FileSessionClient,
    SessionNotFoundError,
    load_server_config,
)

CLIENT_API_COVERAGE = frozenset(
    {
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.file_sessions",
        "CodeAnalysisAsyncClient.call",
        "CodeAnalysisAsyncClient.call_validated",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        "FileSessionClient.create_session",
        "FileSessionClient.assert_session_exists",
        "FileSessionClient.delete_session",
        "FileSessionClient.list_sessions",
        "FileSessionClient.lock_file",
        "FileSessionClient.unlock_file",
        "FileSessionClient.list_file_locks",
        "FileSessionClient.lock_files_advisory",
        "FileSessionClient.unlock_files_advisory",
        "FileSessionClient.download",
        "FileSessionClient.download_to_path",
        "FileSessionClient.upload_bytes",
        "FileSessionClient.upload",
        "FileSessionClient.upload_new",
        "exceptions.SessionNotFoundError",
        "config.load_server_config",
    }
)

INVALID_UUID = "00000000-0000-0000-0000-000000000000"
CaseFn = Callable[[], Awaitable[None]]


@dataclass
class Fixture:
    """Shared context discovered once against the live server."""

    project_id: str
    file_id: str
    file_path: str
    show_session_ids: bool


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


def _data(resp: Dict[str, Any]) -> Dict[str, Any]:
    inner = resp.get("data")
    return inner if isinstance(inner, dict) else resp


def expect_success(resp: Dict[str, Any], label: str) -> Dict[str, Any]:
    if resp.get("success") is not True:
        raise AssertionError(f"{label}: expected success, got {resp!r}")
    return _data(resp)


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
    if isinstance(err, str) and err.strip():
        return err.strip()
    return ""


def expect_error(resp: Dict[str, Any], code: str, label: str) -> None:
    if resp.get("success") is True:
        raise AssertionError(f"{label}: expected error {code}, got success {resp!r}")
    got = _error_code(resp)
    # Accept domain codes at top level or inside error.code (string or int JSON-RPC).
    if got == code or got.endswith(code) or code in got:
        return
    err = resp.get("error")
    if isinstance(err, dict) and str(err.get("code") or "") == code:
        return
    raise AssertionError(f"{label}: expected code {code!r}, got {got!r}: {resp!r}")


async def _call(
    client: CodeAnalysisAsyncClient, command: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    out = await client.call(command, params)
    if not isinstance(out, dict):
        raise AssertionError(f"{command}: response is not a dict: {out!r}")
    return out


async def discover_fixture(client: CodeAnalysisAsyncClient) -> Fixture:
    raw = load_server_config(default_config_path())
    sessions_cfg = raw.get("sessions") or {}
    show_ids = bool(sessions_cfg.get("show_session_ids", False))

    lp = expect_success(
        await _call(client, "list_projects", {"include_deleted": False}),
        "list_projects",
    )
    projects = lp.get("projects") or lp.get("items") or []
    if not isinstance(projects, list) or not projects:
        raise RuntimeError(
            "list_projects returned no projects — register a test project first"
        )

    for proj in projects:
        if not isinstance(proj, dict):
            continue
        pid = str(proj.get("id") or proj.get("project_id") or "").strip()
        if not pid:
            continue
        files_resp = expect_success(
            await _call(
                client,
                "list_project_files",
                {"project_id": pid, "limit": 500},
            ),
            "list_project_files",
        )
        files = files_resp.get("files") or []
        preferred: Optional[Tuple[str, str, str]] = None
        fallback: Optional[Tuple[str, str, str]] = None
        for row in files:
            if not isinstance(row, dict):
                continue
            fid = row.get("file_id")
            rel = str(row.get("relative_path") or row.get("path") or "").strip()
            if not fid or not rel:
                continue
            tup = (pid, str(fid), rel.replace("\\", "/"))
            suffix = Path(rel).suffix.lower()
            if suffix in {
                ".txt",
                ".md",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".cfg",
                ".ini",
            }:
                preferred = tup
                break
            if fallback is None:
                fallback = tup
        pick = preferred or fallback
        if pick is not None:
            return Fixture(
                project_id=pick[0],
                file_id=pick[1],
                file_path=pick[2],
                show_session_ids=show_ids,
            )

    raise RuntimeError(
        "No indexed file with file_id found in any project — run update_indexes on a project"
    )


async def run_all(*, skip_transfer: bool) -> int:
    chdir_repo_root()
    cfg = default_config_path()
    runner = Runner()
    fixture: Optional[Fixture] = None

    async with CodeAnalysisAsyncClient.from_server_config_path(cfg) as client:
        fs = client.file_sessions

        async def case(name: str, fn: CaseFn) -> None:
            try:
                await fn()
                runner.ok(name)
            except Exception as exc:
                runner.fail(name, exc)

        # ------------------------------------------------------------------ setup
        try:
            fixture = await discover_fixture(client)
            print(
                f"Fixture: project_id={fixture.project_id} "
                f"file_id={fixture.file_id} path={fixture.file_path!r} "
                f"show_session_ids={fixture.show_session_ids}"
            )
        except Exception as exc:
            print(f"FATAL: cannot build fixture: {exc}")
            traceback.print_exc()
            return 1

        assert fixture is not None
        fx = fixture

        # ------------------------------------------------------------------ schema / validation
        async def neg_create_missing_comment() -> None:
            try:
                await client.call_validated("session_create", {})
                raise AssertionError("expected ClientValidationError")
            except ClientValidationError:
                return

        async def neg_stale_threshold_type() -> None:
            sid = await fs.create_session("ex_file_sessions stale-type neg")
            try:
                try:
                    await client.call_validated(
                        "session_list",
                        {"stale_threshold_seconds": "not-an-int"},
                    )
                    raise AssertionError("expected ClientValidationError")
                except ClientValidationError:
                    pass
            finally:
                await fs.delete_session(sid)

        async def edge_stale_threshold_zero() -> None:
            """Schema declares minimum 1; live server may still accept 0 (document behavior)."""
            sid = await fs.create_session("ex_file_sessions stale-zero edge")
            try:
                lst = await fs.list_sessions(stale_threshold_seconds=0)
                if "sessions" not in lst:
                    raise AssertionError(f"unexpected list shape: {lst!r}")
            finally:
                await fs.delete_session(sid, force=True)

        # ------------------------------------------------------------------ lifecycle happy
        async def pos_create_list_delete() -> None:
            sid = await fs.create_session("ex_file_sessions lifecycle")
            await fs.assert_session_exists(sid)
            locks = await fs.list_file_locks(sid)
            if int(locks.get("count") or 0) != 0:
                raise AssertionError(f"expected empty locks, got {locks!r}")
            lst = await fs.list_sessions(session_id=sid)
            if int(lst.get("count") or 0) < 1:
                raise AssertionError(f"session not visible in list: {lst!r}")
            deleted = await fs.delete_session(sid)
            if deleted.get("deleted") is not True:
                raise AssertionError(f"delete payload: {deleted!r}")

        async def pos_list_without_session_id_when_hidden() -> None:
            if fx.show_session_ids:
                resp = await _call(client, "session_list", {})
                expect_error(
                    resp, "SESSION_ID_REQUIRED", "session_list without session_id"
                )
                return
            lst = await fs.list_sessions()
            if "sessions" not in lst:
                raise AssertionError(f"missing sessions key: {lst!r}")
            for row in lst.get("sessions") or []:
                if isinstance(row, dict) and "session_id" in row:
                    raise AssertionError(
                        "session_id must be omitted when show_session_ids=false"
                    )

        async def pos_stale_threshold_large() -> None:
            sid = await fs.create_session("ex_file_sessions stale filter")
            try:
                lst = await fs.list_sessions(stale_threshold_seconds=999_999_999)
                ids = {
                    str(r.get("session_id"))
                    for r in (lst.get("sessions") or [])
                    if isinstance(r, dict) and r.get("session_id")
                }
                if sid in ids:
                    raise AssertionError(
                        "fresh session must be excluded by huge stale threshold"
                    )
            finally:
                await fs.delete_session(sid)

        # ------------------------------------------------------------------ DB file locks
        async def pos_db_lock_unlock_idempotent() -> None:
            sid = await fs.create_session("ex_file_sessions db lock")
            try:
                first = await fs.lock_file(sid, fx.project_id, fx.file_id)
                if first.get("acquired") is not True:
                    raise AssertionError(f"first lock: {first!r}")
                second = await fs.lock_file(sid, fx.project_id, fx.file_id)
                if second.get("acquired") is not False:
                    raise AssertionError(
                        f"second lock should be idempotent: {second!r}"
                    )
                locks = await fs.list_file_locks(sid)
                if int(locks.get("count") or 0) < 1:
                    raise AssertionError(f"expected lock row: {locks!r}")
                rel = await fs.unlock_file(sid, fx.project_id, fx.file_id)
                if rel.get("was_locked") is not True:
                    raise AssertionError(f"unlock was_locked: {rel!r}")
                again = await fs.unlock_file(sid, fx.project_id, fx.file_id)
                if again.get("was_locked") is not False:
                    raise AssertionError(f"second unlock idempotent: {again!r}")
            finally:
                await fs.delete_session(sid, force=True)

        async def edge_lock_nonexistent_file_id() -> None:
            """SQLite allows orphan file_id rows; PostgreSQL enforces FK on files.id."""
            sid = await fs.create_session("ex_file_sessions fake file_id")
            fake_fid = str(uuid.uuid4())
            try:
                resp = await _call(
                    client,
                    "session_open_file",
                    {
                        "session_id": sid,
                        "project_id": fx.project_id,
                        "file_id": fake_fid,
                    },
                )
                if resp.get("success") is True:
                    data = _data(resp)
                    if data.get("acquired") is not True:
                        raise AssertionError(data)
                    return
                body = str(resp).lower()
                if "foreign key" in body or "not present in table" in body:
                    return
                raise AssertionError(f"unexpected failure for fake file_id: {resp!r}")
            finally:
                await fs.delete_session(sid, force=True)

        # ------------------------------------------------------------------ advisory locks
        async def pos_advisory_lock_unlock() -> None:
            sid = await fs.create_session("ex_file_sessions advisory")
            try:
                locked = await fs.lock_files_advisory(
                    sid, fx.project_id, [fx.file_path], lock_mode="block_write"
                )
                results = locked.get("results") or []
                if not results or results[0].get("ok") is not True:
                    raise AssertionError(f"advisory lock failed: {locked!r}")
                unlocked = await fs.unlock_files_advisory(
                    sid, fx.project_id, [fx.file_path]
                )
                uresults = unlocked.get("results") or []
                if not uresults or uresults[0].get("ok") is not True:
                    raise AssertionError(f"advisory unlock failed: {unlocked!r}")
            finally:
                await fs.delete_session(sid, force=True)

        # ------------------------------------------------------------------ delete guards
        async def neg_delete_with_locks_no_force() -> None:
            sid = await fs.create_session("ex_file_sessions delete guard")
            await fs.lock_file(sid, fx.project_id, fx.file_id)
            resp = await _call(
                client, "session_delete", {"session_id": sid, "force": False}
            )
            expect_error(resp, "SESSION_HAS_LOCKS", "delete with open lock")
            forced = await fs.delete_session(sid, force=True)
            if forced.get("deleted") is not True:
                raise AssertionError(forced)

        async def neg_delete_unknown() -> None:
            resp = await _call(
                client,
                "session_delete",
                {"session_id": INVALID_UUID, "force": False},
            )
            expect_error(resp, "SESSION_NOT_FOUND", "delete unknown session")

        async def neg_double_delete() -> None:
            sid = await fs.create_session("ex_file_sessions double delete")
            await fs.delete_session(sid)
            resp = await _call(client, "session_delete", {"session_id": sid})
            expect_error(resp, "SESSION_NOT_FOUND", "second delete")

        async def neg_ops_after_delete() -> None:
            sid = await fs.create_session("ex_file_sessions after delete")
            await fs.delete_session(sid)
            resp = await _call(
                client,
                "session_list_file_locks",
                {"session_id": sid},
            )
            expect_error(resp, "SESSION_NOT_FOUND", "list_file_locks after delete")
            try:
                await fs.assert_session_exists(sid)
                raise AssertionError("assert_session_exists should raise")
            except SessionNotFoundError:
                pass
            resp2 = await _call(
                client,
                "session_open_file",
                {
                    "session_id": sid,
                    "project_id": fx.project_id,
                    "file_id": fx.file_id,
                },
            )
            expect_error(resp2, "SESSION_NOT_FOUND", "open_file after delete")

        async def neg_unknown_session_touch_commands() -> None:
            resp = await _call(
                client,
                "session_list_file_locks",
                {"session_id": INVALID_UUID},
            )
            expect_error(resp, "SESSION_NOT_FOUND", "list_file_locks unknown")
            resp2 = await _call(
                client,
                "session_open_file",
                {
                    "session_id": INVALID_UUID,
                    "project_id": fx.project_id,
                    "file_id": fx.file_id,
                },
            )
            expect_error(resp2, "SESSION_NOT_FOUND", "open_file unknown session")

        async def neg_transfer_begin_unknown_session() -> None:
            resp = await _call(
                client,
                "project_file_transfer_download_begin",
                {
                    "session_id": INVALID_UUID,
                    "project_id": fx.project_id,
                    "file_id": fx.file_id,
                    "compression": "identity",
                    "lock_mode": "full",
                },
            )
            if resp.get("success") is True:
                raise AssertionError(f"expected failure, got {resp!r}")
            code = _error_code(resp)
            body = str(resp)
            if code == "SESSION_NOT_FOUND" or "SESSION_NOT_FOUND" in body:
                return
            if "not found" in body.lower():
                return
            raise AssertionError(f"unexpected error: {code!r} {resp!r}")

        # ------------------------------------------------------------------ transfer roundtrip
        async def pos_transfer_roundtrip_same_bytes() -> None:
            sid = await fs.create_session("ex_file_sessions transfer rt")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "dl.bin"
                    await fs.download(
                        sid,
                        dest,
                        fx.file_id,
                        lock=True,
                    )
                    original = dest.read_bytes()
                    await fs.upload(
                        sid,
                        original,
                        fx.file_id,
                        filename=Path(fx.file_path).name,
                        unlock=True,
                        backup=True,
                    )
                locks = await fs.list_file_locks(sid)
                if int(locks.get("count") or 0) != 0:
                    raise AssertionError(f"locks after roundtrip: {locks!r}")
            finally:
                await fs.delete_session(sid, force=True)

        async def pos_download_without_lock() -> None:
            sid = await fs.create_session("ex_file_sessions download no lock")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "dl_nolock.bin"
                    await fs.download(
                        sid,
                        dest,
                        fx.file_id,
                        lock=False,
                    )
                    if dest.stat().st_size <= 0:
                        raise AssertionError(
                            "download without lock returned empty file"
                        )
                locks = await fs.list_file_locks(sid)
                if int(locks.get("count") or 0) != 0:
                    raise AssertionError(f"locks after lock=False download: {locks!r}")
            finally:
                await fs.delete_session(sid, force=True)

        async def pos_upload_unlock_false() -> None:
            sid = await fs.create_session("ex_file_sessions upload no unlock")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "dl_locked.bin"
                    await fs.download(
                        sid,
                        dest,
                        fx.file_id,
                        lock=True,
                    )
                    payload = dest.read_bytes()
                    await fs.upload(
                        sid,
                        payload,
                        fx.file_id,
                        filename=Path(fx.file_path).name,
                        unlock=False,
                        backup=True,
                    )
                locks = await fs.list_file_locks(sid)
                if int(locks.get("count") or 0) == 0:
                    raise AssertionError(
                        f"expected locks after upload(unlock=False): {locks!r}"
                    )
                await fs.unlock_file(sid, fx.project_id, fx.file_id)
                locks2 = await fs.list_file_locks(sid)
                if int(locks2.get("count") or 0) != 0:
                    raise AssertionError(f"locks after manual unlock: {locks2!r}")
            finally:
                await fs.delete_session(sid, force=True)

        async def pos_transfer_dry_run_upload() -> None:
            sid = await fs.create_session("ex_file_sessions dry run")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "dl2.bin"
                    await fs.download(
                        sid,
                        dest,
                        fx.file_id,
                        lock=True,
                    )
                    payload = dest.read_bytes()
                    await fs.upload(
                        sid,
                        payload,
                        fx.file_id,
                        filename=Path(fx.file_path).name,
                        dry_run=True,
                        unlock=True,
                    )
                locks = await fs.list_file_locks(sid)
                count = int(locks.get("count") or 0)
                if count > 0:
                    # dry_run releases advisory lease but may leave session_file_locks row.
                    for row in locks.get("locks") or []:
                        if not isinstance(row, dict):
                            continue
                        await fs.unlock_file(
                            sid,
                            str(row.get("project_id") or fx.project_id),
                            str(row.get("file_id") or fx.file_id),
                        )
                    locks2 = await fs.list_file_locks(sid)
                    if int(locks2.get("count") or 0) != 0:
                        raise AssertionError(f"locks after dry_run cleanup: {locks2!r}")
            finally:
                await fs.delete_session(sid, force=True)

        async def pos_download_to_path_explicit() -> None:
            sid = await fs.create_session("ex_file_sessions download_to_path")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "explicit.bin"
                    begin = await client.call_validated(
                        "project_file_transfer_download_begin",
                        {
                            "session_id": sid,
                            "file_id": fx.file_id,
                            "compression": "identity",
                            "lock_mode": "none",
                        },
                    )
                    if begin.get("success") is not True:
                        raise AssertionError(begin)
                    payload = _data(begin)
                    tid = str(payload.get("transfer_id") or "").strip()
                    if not tid:
                        raise AssertionError(f"no transfer_id: {payload!r}")
                    await fs.download_to_path(tid, dest)
                    if dest.stat().st_size <= 0:
                        raise AssertionError("download_to_path wrote empty file")
            finally:
                await fs.delete_session(sid, force=True)

        async def pos_upload_bytes_then_save_dry_run() -> None:
            sid = await fs.create_session("ex_file_sessions upload_bytes")
            rel_path = f"tmp/client_ex_{uuid.uuid4().hex[:12]}.txt"
            try:
                receipt = await fs.upload_bytes(
                    b"client example upload_bytes line\n",
                    filename="payload.txt",
                )
                if not getattr(receipt, "completed", False):
                    raise AssertionError(f"upload_bytes incomplete: {receipt!r}")
                saved = await client.call_validated(
                    "project_file_transfer_upload_save",
                    {
                        "session_id": sid,
                        "transfer_id": str(receipt.transfer_id),
                        "project_id": fx.project_id,
                        "file_path": rel_path,
                        "unlock_after_write": True,
                        "backup": True,
                        "dry_run": True,
                    },
                )
                if saved.get("success") is not True:
                    raise AssertionError(saved)
            finally:
                await fs.delete_session(sid, force=True)

        async def pos_upload_new_dry_run() -> None:
            sid = await fs.create_session("ex_file_sessions upload_new")
            rel_path = f"tmp/client_ex_new_{uuid.uuid4().hex[:12]}.txt"
            try:
                out = await fs.upload_new(
                    sid,
                    b"upload_new dry_run content\n",
                    fx.project_id,
                    rel_path,
                    dry_run=True,
                )
                if out is not None and not isinstance(out, str):
                    raise AssertionError(f"upload_new dry_run returned {out!r}")
            finally:
                await fs.delete_session(sid, force=True)

        # ------------------------------------------------------------------ register cases
        sections: List[Tuple[str, List[Tuple[str, CaseFn]]]] = [
            (
                "validation / schema",
                [
                    ("session_create missing comment", neg_create_missing_comment),
                    (
                        "session_list stale_threshold wrong type",
                        neg_stale_threshold_type,
                    ),
                    (
                        "session_list stale_threshold zero (edge)",
                        edge_stale_threshold_zero,
                    ),
                ],
            ),
            (
                "lifecycle",
                [
                    ("create → assert → list → delete", pos_create_list_delete),
                    (
                        "session_list visibility policy",
                        pos_list_without_session_id_when_hidden,
                    ),
                    (
                        "stale_threshold excludes fresh session",
                        pos_stale_threshold_large,
                    ),
                ],
            ),
            (
                "DB file locks (session_open/close_file)",
                [
                    ("lock / unlock idempotent", pos_db_lock_unlock_idempotent),
                    (
                        "nonexistent file_id (FK vs SQLite)",
                        edge_lock_nonexistent_file_id,
                    ),
                ],
            ),
            (
                "advisory locks",
                [
                    ("advisory lock + unlock", pos_advisory_lock_unlock),
                ],
            ),
            (
                "delete guards & SESSION_NOT_FOUND",
                [
                    (
                        "delete with locks requires force",
                        neg_delete_with_locks_no_force,
                    ),
                    ("delete unknown session", neg_delete_unknown),
                    ("double delete", neg_double_delete),
                    ("operations after delete", neg_ops_after_delete),
                    (
                        "unknown session on touch commands",
                        neg_unknown_session_touch_commands,
                    ),
                    (
                        "transfer begin unknown session",
                        neg_transfer_begin_unknown_session,
                    ),
                ],
            ),
        ]

        if not skip_transfer:
            sections.append(
                (
                    "transfer + FileSessionClient",
                    [
                        (
                            "download(lock) + upload(unlock) roundtrip",
                            pos_transfer_roundtrip_same_bytes,
                        ),
                        ("download(lock=False)", pos_download_without_lock),
                        (
                            "upload(unlock=False) then manual unlock",
                            pos_upload_unlock_false,
                        ),
                        ("dry_run upload", pos_transfer_dry_run_upload),
                        (
                            "download_to_path (explicit two-step)",
                            pos_download_to_path_explicit,
                        ),
                        (
                            "upload_bytes + save dry_run",
                            pos_upload_bytes_then_save_dry_run,
                        ),
                        ("upload_new dry_run", pos_upload_new_dry_run),
                    ],
                )
            )
        else:
            print("  (skipping transfer section — --skip-transfer)")

        for section_title, cases in sections:
            print(f"\n== {section_title} ==")
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
    parser = argparse.ArgumentParser(description="Client session integration driver")
    parser.add_argument(
        "--skip-transfer",
        action="store_true",
        help="Skip transfer download/upload cases (faster, no file I/O)",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(run_all(skip_transfer=args.skip_transfer))
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
