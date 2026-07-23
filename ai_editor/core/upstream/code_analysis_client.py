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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional
from uuid import uuid4

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
    upload_create_save_via_text_stage_move,
    is_ca_save_unsupported_extension_error,
    invalidate_cached_file_id,
    is_file_id_not_found_error,
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
        err = (
            response.get("error")
            or response.get("message")
            or "upstream command failed"
        )
        raise RuntimeError(str(err))
    data = response.get("data")
    if data is not None:
        return data
    return response


def _queued_job_id(response: Any) -> Optional[str]:
    """Return a queued job identifier from the known upstream envelope shapes."""
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    candidates = (
        response.get("job_id"),
        response.get("jobId"),
        data.get("job_id") if isinstance(data, dict) else None,
        data.get("jobId") if isinstance(data, dict) else None,
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _queued_poll_command(response: Any) -> Optional[str]:
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    candidates = [
        response.get("poll_with"),
        data.get("poll_with") if isinstance(data, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _is_queued_response(response: Any) -> bool:
    """Recognize queued envelopes without changing their downstream result."""
    if not isinstance(response, dict):
        return False
    if _queued_poll_command(response) == "queue_get_job_status":
        return _queued_job_id(response) is not None
    if str(response.get("mode") or "").strip().lower() == "queued":
        return True
    if response.get("queued") is True:
        return True
    data = response.get("data")
    statuses = [
        response.get("status"),
        data.get("status") if isinstance(data, dict) else None,
    ]
    if _queued_job_id(response) is not None and any(
        str(status or "").strip().lower() in {"queued", "pending", "running"}
        for status in statuses
    ):
        return True
    return False


class CaSessionStatus(str, enum.Enum):
    VALID = "valid"
    NOT_FOUND = "not_found"
    INVALID = "invalid"


class EditOutcome(str, enum.Enum):
    """Normalized outcome for a direct or queued upstream command."""

    SUCCESS = "success"
    NO_OP = "no_op"
    VALIDATION_ERROR = "validation_error"
    EDIT_ERROR = "edit_error"
    TIMEOUT_UNKNOWN = "timeout_unknown"


@dataclass(frozen=True)
class UpstreamCommandResult:
    """Identity and normalized result for one upstream command attempt."""

    call_id: str
    command: str
    params: Dict[str, Any]
    response: Any
    result: Any
    is_queued: bool = False
    queue_job_id: Optional[str] = None
    outcome: EditOutcome = EditOutcome.SUCCESS
    queue_status: Optional[str] = None


# Kept as an import-compatible name for the G-001 identity contract.
UpstreamCallResult = UpstreamCommandResult


_QUEUE_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "error", "stopped", "deleted", "cancelled", "timeout"}
)
_QUEUE_POLL_INTERVAL_SECONDS = 0.2
_QUEUE_POLL_TIMEOUT_SECONDS = 120.0


def _response_data(response: Any) -> Any:
    if isinstance(response, dict) and response.get("data") is not None:
        return response["data"]
    return response


def _status_from_response(response: Any) -> Optional[str]:
    data = _response_data(response)
    if isinstance(data, dict):
        status = data.get("status") or response.get("status")
        if isinstance(status, str) and status.strip():
            return status.strip().lower()
    return None


def _classify_outcome(result: Any, status: Optional[str] = None) -> EditOutcome:
    if isinstance(result, dict):
        kind = str(result.get("kind") or result.get("outcome") or "").strip().lower()
        if kind in {item.value for item in EditOutcome}:
            return EditOutcome(kind)
        if result.get("success") is False:
            error = result.get("error")
            if isinstance(error, dict):
                error = error.get("message") or error.get("detail") or error.get("code")
            message = str(error or result.get("message") or "").lower()
            if "validation" in message or "invalid" in message:
                return EditOutcome.VALIDATION_ERROR
            return EditOutcome.EDIT_ERROR
        if result.get("success") is True or status == "completed":
            return EditOutcome.SUCCESS

    if status == "timeout":
        return EditOutcome.TIMEOUT_UNKNOWN
    if status in {"failed", "error", "stopped", "deleted", "cancelled"}:
        return EditOutcome.EDIT_ERROR
    if not isinstance(result, dict):
        return EditOutcome.SUCCESS
    return EditOutcome.SUCCESS


def _unwrap_queued_terminal_payload(payload: Any) -> Any:
    """Normalize queue terminal payloads to the original command's public result."""
    while isinstance(payload, dict):
        if payload.get("success") is False:
            return payload
        if "result" in payload and any(
            key in payload
            for key in ("command", "job_id", "jobId", "queue_job_id", "status")
        ):
            payload = payload["result"]
            continue
        if payload.get("success") is True and "data" in payload:
            payload = payload["data"]
            continue
        return payload
    return payload


def _terminal_result(response: Any) -> tuple[Any, Optional[str], EditOutcome]:
    data = _response_data(response)
    status = _status_from_response(response)
    payload = data
    if isinstance(data, dict) and "result" in data:
        payload = data["result"]
    payload = _unwrap_queued_terminal_payload(payload)
    return payload, status, _classify_outcome(payload, status)


def _queued_failure_message(outcome: UpstreamCommandResult) -> str:
    result = outcome.result
    response = outcome.response
    for payload in (result, _response_data(response), response):
        if not isinstance(payload, dict):
            continue
        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("message") or error.get("detail") or error.get("code")
        message = error or payload.get("message") or payload.get("detail")
        if message:
            return str(message)
    status = outcome.queue_status or "unknown"
    return f"Queued upstream command ended with status {status}"


def _raise_if_failed_queued_outcome(outcome: UpstreamCommandResult) -> None:
    if not outcome.is_queued:
        return
    if outcome.outcome in {EditOutcome.SUCCESS, EditOutcome.NO_OP}:
        return
    message = _queued_failure_message(outcome)
    raise RuntimeError(
        f"{message} (job_id={outcome.queue_job_id}, status={outcome.queue_status})"
    )


def describe_exception(exc: BaseException, context: str = "") -> str:
    """Build a never-empty human-readable description of an exception.

    ``str(exc)`` is empty for several stdlib/httpx exception types (for
    example ``httpx.ReadTimeout()``), which previously surfaced as an
    OPEN_ERROR (or UPSTREAM_LOCK_FAILED / UPSTREAM_UPLOAD_FAILED) with an
    empty ``message``. This helper always returns a non-empty string: the
    exception's class name, plus ``str(exc)`` when it is non-empty, else the
    caller-supplied ``context``, else a fixed fallback phrase.

    Args:
        exc: The exception instance to describe.
        context: Optional short description of the operation being
            attempted when ``exc`` was raised (for example a command
            name). Used only when ``str(exc)`` is empty.

    Returns:
        A non-empty string of the form ``"<ExcClassName>: <detail>"``.
    """
    cls_name = type(exc).__name__
    detail = str(exc).strip()
    if not detail:
        detail = context.strip() if context.strip() else "no additional details"
    return f"{cls_name}: {detail}"


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

    def _reraise_connect_error(self, command: str, exc: BaseException) -> NoReturn:
        if httpx is not None and isinstance(
            exc, (httpx.ConnectTimeout, httpx.ConnectError)
        ):
            raise RuntimeError(
                "Code Analysis Server unreachable at "
                f"{self._upstream_target_label()} while calling {command!r}: "
                f"{describe_exception(exc, context=command)}"
            ) from exc
        raise exc

    def _execute_unified_or_legacy(
        self,
        rpc: JsonRpcClient,
        loop: asyncio.AbstractEventLoop,
        command: str,
        params: Dict[str, Any],
        call_timeout: float,
    ) -> Any:
        """Return the upstream response, preferring the adapter-native unified path.

        Tries ``execute_command_unified(auto_poll=True)`` first (adapter-driven
        WebSocket CommandSession + wait_for_terminal + unwrap -- the safe path
        per adapter docs). Falls back to the legacy bare ``execute_command``
        call when the unified path itself raises (missing API, or a transport
        failure such as WebSocket being unavailable in the deployed mTLS
        topology); the hand-rolled queue detection/polling in the caller then
        handles the raw legacy response unchanged.

        Args:
            rpc: The JsonRpcClient instance for this call.
            loop: The event loop driving both the unified and legacy attempts.
            command: Upstream command name.
            params: Upstream command parameters.
            call_timeout: Timeout in seconds passed to the unified path.

        Returns:
            The raw upstream response object, from whichever path served it.
        """
        try:
            response = loop.run_until_complete(
                rpc.execute_command_unified(
                    command=command,
                    params=params,
                    auto_poll=True,
                    timeout=call_timeout,
                )
            )
            logger.debug(
                "CA call %r served via execute_command_unified(auto_poll=True)",
                command,
            )
            return response
        except AttributeError:
            # Adapter build without execute_command_unified: legacy path.
            response = loop.run_until_complete(
                rpc.execute_command(command=command, params=params)
            )
            logger.debug(
                "CA call %r served via legacy execute_command (no unified API)",
                command,
            )
            return response
        except Exception as unified_exc:
            logger.warning(
                "execute_command_unified failed for %r (%s); falling back to "
                "legacy execute_command + hand-rolled queue polling",
                command,
                describe_exception(unified_exc),
            )
            response = loop.run_until_complete(
                rpc.execute_command(command=command, params=params)
            )
            logger.debug(
                "CA call %r served via legacy execute_command (fallback)",
                command,
            )
            return response

    def _call_blocking(
        self, command: str, params: Dict[str, Any]
    ) -> UpstreamCallResult:
        """Run one CA RPC in a fresh event loop (safe from any thread).

        Prefers the adapter-native synchronous-emulation path
        (``execute_command_unified`` with ``auto_poll=True``) via
        ``_execute_unified_or_legacy``, falling back to the legacy bare
        ``execute_command`` call (with the hand-rolled queue detection/polling
        below kept intact) when the unified path itself raises -- for example
        when WebSocket transport is unavailable in the deployed mTLS topology --
        so a transport failure of the preferred path never loses queue-handoff
        correctness.
        """
        call_id = str(uuid4())
        loop = asyncio.new_event_loop()
        jsonrpc_kwargs = _build_jsonrpc_kwargs(self._section)
        rpc = JsonRpcClient(**jsonrpc_kwargs)
        call_timeout = float(jsonrpc_kwargs.get("timeout") or 300.0)
        try:
            response = self._execute_unified_or_legacy(
                rpc, loop, command, params, call_timeout
            )
            queued = _is_queued_response(response)
            queue_job_id = _queued_job_id(response)
            if queued and queue_job_id:
                deadline = time.monotonic() + _QUEUE_POLL_TIMEOUT_SECONDS
                terminal_response = response
                terminal_status: Optional[str] = None
                while time.monotonic() < deadline:
                    terminal_response = loop.run_until_complete(
                        rpc.execute_command(
                            command="queue_get_job_status",
                            params={"job_id": queue_job_id},
                        )
                    )
                    terminal_status = _status_from_response(terminal_response)
                    if terminal_status in _QUEUE_TERMINAL_STATUSES:
                        break
                    time.sleep(_QUEUE_POLL_INTERVAL_SECONDS)
                else:
                    terminal_status = "timeout"
                    terminal_response = {
                        "success": False,
                        "status": "timeout",
                        "error": (
                            "Queued upstream command did not reach a terminal state"
                        ),
                        "job_id": queue_job_id,
                        "last_response": terminal_response,
                    }

                result, _, outcome = _terminal_result(terminal_response)
                return UpstreamCommandResult(
                    call_id=call_id,
                    command=command,
                    params=dict(params),
                    response=terminal_response,
                    result=result,
                    is_queued=True,
                    queue_job_id=queue_job_id,
                    outcome=outcome,
                    queue_status=terminal_status,
                )
            normalized_result = _unwrap_command_result(response)
            return UpstreamCallResult(
                call_id=call_id,
                command=command,
                params=dict(params),
                response=response,
                result=normalized_result,
                is_queued=queued,
                queue_job_id=queue_job_id,
                outcome=_classify_outcome(normalized_result),
            )
        except BaseException as exc:
            self._reraise_connect_error(command, exc)
        finally:
            loop.close()

    def call_with_identity(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> UpstreamCallResult:
        """Execute once and expose the attempt identity with its normalized result."""
        payload = params or {}
        try:
            asyncio.get_running_loop()
            in_async = True
        except RuntimeError:
            in_async = False
        if in_async:
            with ThreadPoolExecutor(max_workers=1) as pool:
                outcome = pool.submit(self._call_blocking, command, payload).result()
        else:
            outcome = self._call_blocking(command, payload)
        if isinstance(outcome, UpstreamCallResult):
            return outcome
        raise TypeError("_call_blocking must return UpstreamCallResult")

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
                    outcome = pool.submit(
                        self._call_blocking, command, payload
                    ).result()
                    if isinstance(outcome, UpstreamCallResult):
                        _raise_if_failed_queued_outcome(outcome)
                        return outcome.result
                    return outcome
                except BaseException as exc:
                    self._reraise_connect_error(command, exc)

        try:
            outcome = self._call_blocking(command, payload)
            if isinstance(outcome, UpstreamCallResult):
                _raise_if_failed_queued_outcome(outcome)
                return outcome.result
            return outcome
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

    def ensure_session_file_lock(
        self, *, session_id: str, project_id: str, file_path: str
    ) -> str:
        """Ensure an existing CA file is locked by this session before write.

        Existing files are normally locked during universal_file_open, but commit
        re-affirms the lock immediately before upload so a lost/stale lock fails
        as a write error instead of writing unlocked. A cached file_id that has
        gone stale (the target path was moved or deleted elsewhere) is detected
        from the shape of the session_open_file failure, invalidated, and
        re-resolved exactly once before giving up.
        """
        sid, pid, rel = _normalized_session_path(session_id, project_id, file_path)
        if not sid or not pid or not rel:
            _raise_missing_session_path(session_id, project_id, file_path)
        try:
            file_id = resolve_file_id_for_path(self, pid, rel)
        except RuntimeError as exc:
            if "file not found in project index" not in str(exc):
                raise
            file_id = ensure_file_id_for_path(self, pid, rel, session_id=sid)
        try:
            self.call(
                "session_open_file",
                {"session_id": sid, "project_id": pid, "file_id": file_id},
            )
        except RuntimeError as exc:
            if not is_file_id_not_found_error(exc):
                raise
            invalidate_cached_file_id(pid, rel)
            file_id = ensure_file_id_for_path(self, pid, rel, session_id=sid)
            self.call(
                "session_open_file",
                {"session_id": sid, "project_id": pid, "file_id": file_id},
            )
        return file_id

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
        # Resolve file_id and re-affirm the session lock immediately before
        # upload. If the file cannot be locked, the write must fail.
        file_id = self.ensure_session_file_lock(
            session_id=sid, project_id=pid, file_path=rel
        )
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
        return download_bytes_without_lock(
            self, project_id=project_id, file_path=file_path
        )

    def upload_create_and_lock(
        self, *, session_id: str, project_id: str, file_path: str, content: bytes
    ) -> bytes:
        """Write Stage create path: upload + atomic lock, then confirm (C-010).

        The transfer save itself acquires the session lock (lock_mode="full",
        unlock_after_write=False), so the brand-new file is never registered in
        CA without a lock. session_open_file then re-affirms the same
        session-scoped lock (idempotent for the owning session) and keeps the
        open/close lifecycle symmetric with session_close_file on close.
        """
        sid, pid, rel = _normalized_session_path(session_id, project_id, file_path)
        try:
            saved = upload_create_save(
                self,
                session_id=sid,
                project_id=pid,
                file_path=rel,
                content=content,
                lock_mode="full",
            )
        except RuntimeError as exc:
            if not is_ca_save_unsupported_extension_error(exc):
                raise
            saved = upload_create_save_via_text_stage_move(
                self,
                session_id=sid,
                project_id=pid,
                file_path=rel,
                content=content,
            )
        file_id = str(saved.get("file_id") or "").strip()
        if not file_id:
            try:
                file_id = resolve_file_id_for_path(self, pid, rel)
            except RuntimeError:
                file_id = ""
        if file_id:
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
