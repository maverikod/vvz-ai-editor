"""
Sync wrapper around mcp-proxy-adapter JsonRpcClient for code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import enum
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_editor.core.exceptions import ValidationError

from .ca_config_bridge import (
    build_jsonrpc_kwargs_from_ca_section,
    load_resolved_ca_section,
)

from .code_analysis_file_transfer import (
    download_bytes_without_lock,
    download_file_bytes,
    ensure_file_id_for_path,
    normalize_rel_path,
    resolve_file_id_for_path,
    upload_bytes_transfer_id,
    upload_create_save,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger(__name__)

try:
    from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient
except Exception:  # pragma: no cover
    from mcp_proxy_adapter.client.jsonrpc_client import JsonRpcClient

_client_lock = threading.Lock()
_client_instance: Optional["CodeAnalysisClient"] = None


def _normalized_session_path(
    session_id: Any, project_id: Any, file_path: str
) -> tuple[str, str, str]:
    return (
        str(session_id or "").strip(),
        str(project_id or "").strip(),
        normalize_rel_path(file_path),
    )


def _raise_missing_session_path(
    session_id: Any, project_id: Any, file_path: str
) -> None:
    raise ValidationError(
        "session_id, project_id, and file_path are required",
        field="session_id",
        details={
            "session_id": session_id,
            "project_id": project_id,
            "file_path": file_path,
        },
    )


def _accepted_upload_bytes(saved: Any, content: bytes) -> bytes:
    if isinstance(saved, dict):
        accepted = saved.get("content_bytes") or saved.get("bytes")
        if isinstance(accepted, (bytes, bytearray)):
            return bytes(accepted)
    return content


def _load_ca_section(config_path: Optional[Path] = None) -> Dict[str, Any]:
    return load_resolved_ca_section(config_path)


def _build_jsonrpc_kwargs(section: Dict[str, Any]) -> Dict[str, Any]:
    return build_jsonrpc_kwargs_from_ca_section(section)


def _unwrap_command_result(response: Any) -> Any:
    if not isinstance(response, dict):
        return response
    if response.get("success") is False:
        err = response.get("error") or response.get("message") or "upstream command failed"  # fmt: skip
        raise RuntimeError(str(err))
    data = response.get("data")
    if data is not None:
        return data
    return response


class CaSessionStatus(str, enum.Enum):
    VALID = "valid"
    NOT_FOUND = "not_found"
    INVALID = "invalid"


class CodeAnalysisClient:
    """Synchronous JSON-RPC client for code-analysis-server."""

    def __init__(self, *, config_path: Optional[Path] = None) -> None:
        self._config_path = config_path
        self._section = _load_ca_section(config_path)
        self._rpc: Optional[JsonRpcClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server_id = str(self._section.get("server_id") or "code-analysis-server")

    def _run_async(self, coroutine: Any) -> Any:
        """Run awaitable from sync code; safe inside Hypercorn async handlers."""

        def _blocking() -> Any:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coroutine)
            finally:
                loop.close()

        try:
            asyncio.get_running_loop()
            in_async = True
        except RuntimeError:
            in_async = False

        if in_async:
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_blocking).result()

        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(coroutine)

    def run_in_isolated_loop(self, coroutine_factory: Any) -> Any:
        """Build coroutine with a fresh JsonRpcClient in an isolated event loop."""

        def _blocking() -> Any:
            loop = asyncio.new_event_loop()
            rpc = JsonRpcClient(**_build_jsonrpc_kwargs(self._section))
            try:
                return loop.run_until_complete(coroutine_factory(rpc))
            finally:
                loop.close()

        try:
            asyncio.get_running_loop()
            in_async = True
        except RuntimeError:
            in_async = False

        if in_async:
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_blocking).result()
        return _blocking()

    def _upstream_target_label(self) -> str:
        kwargs = _build_jsonrpc_kwargs(self._section)
        return (
            f"{kwargs.get('protocol', 'https')}://"
            f"{kwargs.get('host', '127.0.0.1')}:{kwargs.get('port', 15010)}"
        )

    def _reraise_connect_error(self, command: str, exc: BaseException) -> None:
        if httpx is not None and isinstance(
            exc, (httpx.ConnectTimeout, httpx.ConnectError)
        ):
            raise RuntimeError(
                "Code Analysis Server unreachable at "
                f"{self._upstream_target_label()} while calling {command!r}: {exc}"
            ) from exc
        raise exc

    def _call_blocking(self, command: str, params: Dict[str, Any]) -> Any:
        """Run one CA RPC in a fresh event loop (safe from any thread)."""
        loop = asyncio.new_event_loop()
        rpc = JsonRpcClient(**_build_jsonrpc_kwargs(self._section))
        try:
            response = loop.run_until_complete(
                rpc.execute_command(command=command, params=params)
            )
            return _unwrap_command_result(response)
        except BaseException as exc:
            self._reraise_connect_error(command, exc)
        finally:
            loop.close()

    def _ensure_rpc(self) -> JsonRpcClient:
        if self._rpc is None:
            self._rpc = JsonRpcClient(**_build_jsonrpc_kwargs(self._section))
        return self._rpc

    def call(self, command: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a command on code-analysis-server and return unwrapped data."""
        payload = params or {}
        try:
            asyncio.get_running_loop()
            in_async = True
        except RuntimeError:
            in_async = False

        if in_async:
            with ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    return pool.submit(self._call_blocking, command, payload).result()
                except BaseException as exc:
                    self._reraise_connect_error(command, exc)

        rpc = self._ensure_rpc()
        try:
            response = self._run_async(
                rpc.execute_command(command=command, params=payload)
            )
            return _unwrap_command_result(response)
        except BaseException as exc:
            self._reraise_connect_error(command, exc)

    def list_projects(self, *, include_deleted: bool = False) -> List[Dict[str, Any]]:
        data = self.call("list_projects", {"include_deleted": include_deleted})
        if isinstance(data, dict):
            projects = data.get("projects")
            if isinstance(projects, list):
                return [dict(p) for p in projects if isinstance(p, dict)]
        if isinstance(data, list):
            return [dict(p) for p in data if isinstance(p, dict)]
        return []

    @property
    def server_id(self) -> str:
        """Configured MCP proxy downstream server id for logging."""
        return self._server_id

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        pid = str(project_id or "").strip()
        if not pid:
            return None
        for row in self.list_projects(include_deleted=True):
            if str(row.get("id") or row.get("project_id") or "").strip() == pid:
                return row
        return None

    def get_project_root(self, project_id: str) -> Path:
        """Deprecated; use C-023 RPC wrappers instead."""
        project = self.get_project(project_id)
        if not project:
            raise ValidationError(
                f"Project with ID {project_id!r} not found.",
                field="project_id",
                details={"project_id": project_id},
            )
        stored = str(project.get("root_path") or "").strip()
        watch_dir = str(
            project.get("watch_dir") or project.get("watch_dir_path") or ""
        ).strip()
        if stored and Path(stored).is_absolute():
            root = Path(stored).resolve()
        elif watch_dir and stored:
            root = (Path(watch_dir) / stored).resolve()
        elif watch_dir and project.get("name"):
            root = (Path(watch_dir) / str(project["name"])).resolve()
        else:
            raise ValidationError(
                f"Cannot resolve absolute project root for project_id {project_id!r}",
                field="project_id",
                details={"project_id": project_id, "project": project},
            )
        if not root.is_dir():
            raise ValidationError(
                f"Project root path does not exist: {root}",
                field="project_id",
                details={"project_id": project_id, "root_path": str(root)},
            )
        return root

    def resolve_file_by_id(
        self, file_id: str, project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        fid = str(file_id or "").strip()
        if not fid:
            return None
        if project_id:
            project_ids = [str(project_id).strip()]
        else:
            project_ids = [
                str(p.get("id") or p.get("project_id") or "").strip()
                for p in self.list_projects(include_deleted=False)
            ]
        for pid in project_ids:
            if not pid:
                continue
            try:
                data = self.call("list_project_files", {"project_id": pid})
            except Exception as exc:
                logger.debug("list_project_files failed for %s: %s", pid, exc)
                continue
            files = data.get("files") if isinstance(data, dict) else data
            if not isinstance(files, list):
                continue
            for item in files:
                if not isinstance(item, dict):
                    continue
                row_fid = str(item.get("file_id") or item.get("id") or "").strip()
                if row_fid != fid:
                    continue
                rel = str(
                    item.get("relative_path")
                    or item.get("path")
                    or item.get("file_path")
                    or ""
                ).strip()
                return {
                    "id": fid,
                    "project_id": pid,
                    "relative_path": rel.replace("\\", "/"),
                    "path": rel.replace("\\", "/"),
                    "deleted": bool(item.get("deleted")),
                }
        return None

    def validate_ca_session(self, session_id: str) -> CaSessionStatus:
        sid = str(session_id or "").strip()
        if not sid:
            return CaSessionStatus.INVALID
        try:
            self.call("session_list_file_locks", {"session_id": sid})
            return CaSessionStatus.VALID
        except RuntimeError as exc:
            msg = str(exc).upper()
            if "SESSION_NOT_FOUND" in msg:
                return CaSessionStatus.NOT_FOUND
            return CaSessionStatus.INVALID

    def lock_file_and_download(
        self, session_id: str, project_id: str, file_path: str
    ) -> bytes:
        """Open Stage: session_open_file lock then chunked download (C-023)."""
        sid, pid, rel = _normalized_session_path(session_id, project_id, file_path)
        if not sid or not pid or not rel:
            _raise_missing_session_path(session_id, project_id, file_path)
        file_id = ensure_file_id_for_path(self, pid, rel, session_id=sid)
        self.call(
            "session_open_file",
            {"session_id": sid, "project_id": pid, "file_id": file_id},
        )
        return download_file_bytes(
            self, session_id=sid, project_id=pid, file_id=file_id, lock_mode="none"
        )

    def unlock_session_file(
        self, *, session_id: str, project_id: str, file_path: str
    ) -> bool:
        """Close Stage unlock via session_close_file; best-effort on broken session."""
        sid, pid, rel = _normalized_session_path(session_id, project_id, file_path)
        if not sid or not pid or not rel:
            return False
        try:
            file_id = resolve_file_id_for_path(self, pid, rel)
        except (ValidationError, RuntimeError):
            return False
        try:
            self.call(
                "session_close_file",
                {"session_id": sid, "project_id": pid, "file_id": file_id},
            )
            return True
        except RuntimeError as exc:
            msg = str(exc).upper()
            if "SESSION_NOT_FOUND" in msg or "NOT_LOCKED" in msg or "NO_LOCK" in msg:
                return False
            return False

    def upload_session_file_content(
        self, *, session_id: str, project_id: str, file_path: str, content: bytes
    ) -> bytes:
        """Write Stage upload via project_file_transfer_upload_save (C-012)."""
        sid, pid, rel = _normalized_session_path(session_id, project_id, file_path)
        if not sid or not pid or not rel:
            _raise_missing_session_path(session_id, project_id, file_path)
        # At commit time the file is always already in the CA index: existing files
        # were indexed before open, and create=true files were registered at open via
        # upload_create_and_lock. project_file_transfer_upload_save therefore needs the
        # "update existing" mode, which is keyed by file_id (sending file_path triggers
        # the create-new branch and CA rejects it with FILE_ALREADY_INDEXED).
        file_id = resolve_file_id_for_path(self, pid, rel)
        transfer_id = upload_bytes_transfer_id(
            self, content, filename=Path(rel).name or "upload.bin"
        )
        # validate_syntax_only=True: the editor has already run full local validation
        # (black, flake8, mypy, docstrings) on the exact bytes being uploaded.
        # Telling CA to check syntax only avoids a false VALIDATION_ERROR that arises
        # when the CA runs semantic validation against its own in-memory session state
        # (the pre-edit original) rather than the uploaded content.
        saved = self.call(
            "project_file_transfer_upload_save",
            {
                "session_id": sid,
                "project_id": pid,
                "file_id": file_id,
                "transfer_id": transfer_id,
                "unlock_after_write": False,
                "backup": True,
                "dry_run": False,
                "validate_syntax_only": True,
            },
        )
        return _accepted_upload_bytes(saved, content)

    def download_without_lock(self, *, project_id: str, file_path: str) -> bytes:
        """Edit Stage one-shot preview: download without session_open_file (C-011)."""
        return download_bytes_without_lock(self, project_id=project_id, file_path=file_path)  # fmt: skip

    def upload_create_and_lock(
        self, *, session_id: str, project_id: str, file_path: str, content: bytes
    ) -> bytes:
        """Open Stage create path: upload + atomic lock, then confirm (C-010).

        The transfer save itself acquires the session lock (lock_mode="full",
        unlock_after_write=False), so the brand-new file is never registered in
        CA without a lock. session_open_file then re-affirms the same
        session-scoped lock (idempotent for the owning session) and keeps the
        open/close lifecycle symmetric with session_close_file on close.
        """
        sid, pid, rel = _normalized_session_path(session_id, project_id, file_path)
        saved = upload_create_save(
            self,
            session_id=sid,
            project_id=pid,
            file_path=rel,
            content=content,
            lock_mode="full",
        )
        file_id = str(saved.get("file_id") or "").strip() or resolve_file_id_for_path(
            self, pid, rel
        )
        self.call(
            "session_open_file",
            {"session_id": sid, "project_id": pid, "file_id": file_id},
        )
        return _accepted_upload_bytes(saved, content)


def get_code_analysis_client(
    *, config_path: Optional[Path] = None
) -> CodeAnalysisClient:
    """Return process-wide CodeAnalysisClient singleton."""
    global _client_instance
    with _client_lock:
        if _client_instance is None:
            _client_instance = CodeAnalysisClient(config_path=config_path)
        return _client_instance
