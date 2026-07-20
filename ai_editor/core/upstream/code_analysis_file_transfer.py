"""
Transfer-layer helpers for code-analysis-server chunked upload/download.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from uuid import uuid4
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ai_editor.core.host_filesystem import (
    guard_host_file_operation,
    handle_host_file_error,
)

if TYPE_CHECKING:
    from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient

logger = logging.getLogger(__name__)

_CA_SAVE_UNSUPPORTED_SUFFIXES = {".ini", ".cfg", ".toml"}


def normalize_rel_path(file_path: str) -> str:
    """Normalize project-relative path for CA file index matching (C-023)."""
    return str(file_path or "").strip().replace("\\", "/")


def _row_relative_path(item: Dict[str, Any]) -> str:
    return normalize_rel_path(
        str(
            item.get("relative_path") or item.get("path") or item.get("file_path") or ""
        )
    )


def _file_id_from_row(item: Dict[str, Any]) -> str:
    return str(item.get("file_id") or item.get("id") or "").strip()


def _transfer_id_from_payload(payload: Any) -> str:
    """Extract transfer_id from object, dict, or wrapped domain payloads."""
    value = getattr(payload, "transfer_id", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("transfer_id", "transferId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("data", "result"):
        nested = payload.get(key)
        transfer_id = _transfer_id_from_payload(nested)
        if transfer_id:
            return transfer_id
    return ""


def _project_name(client: "CodeAnalysisClient", project_id: str) -> str:
    try:
        project = client.get_project(project_id)
    except Exception:
        return ""
    if not isinstance(project, dict):
        return ""
    return str(project.get("name") or "").strip().replace("\\", "/").strip("/")


def candidate_rel_paths_for_project(
    client: "CodeAnalysisClient",
    project_id: str,
    file_path: str,
) -> List[str]:
    """Return project-relative lookup candidates for a caller-supplied path.

    The public editor API expects project-relative paths, but agents sometimes
    pass ``<project-name>/path.py`` after selecting a project_id for that same
    project. CA treats the shorter suffix as canonical, so use it as a recovery
    candidate without changing the caller-visible file_path stored in the editor
    session.
    """
    rel = normalize_rel_path(file_path)
    candidates: List[str] = []
    if rel:
        candidates.append(rel)
    project_name = _project_name(client, project_id)
    prefix = f"{project_name}/" if project_name else ""
    if prefix and rel.startswith(prefix):
        stripped = rel[len(prefix) :]
        if stripped:
            candidates.append(stripped)
    seen = set()
    unique: List[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def list_project_file_rows_for_path(
    client: "CodeAnalysisClient",
    project_id: str,
    file_path: str,
) -> List[Dict[str, Any]]:
    """Return ``list_project_files`` rows for one exact project-relative path."""
    pid = str(project_id or "").strip()
    candidates = candidate_rel_paths_for_project(client, pid, file_path)
    last_files: Any = None
    for rel in candidates:
        data = client.call(
            "list_project_files",
            {"project_id": pid, "file_pattern": rel},
        )
        files = data.get("files") if isinstance(data, dict) else data
        last_files = files
        if not isinstance(files, list):
            raise RuntimeError("list_project_files returned no files list")
        rows = [
            item
            for item in files
            if isinstance(item, dict) and _row_relative_path(item) == rel
        ]
        if rows:
            return rows
    if last_files is None:
        return []
    return []


def _read_project_file_bytes_via_lines_one_path(
    client: "CodeAnalysisClient",
    project_id: str,
    rel: str,
    *,
    chunk_size: int,
) -> bytes:
    """Read one canonical relative path through CA's raw line API."""
    pid = str(project_id or "").strip()
    probe = client.call(
        "get_file_lines",
        {
            "project_id": pid,
            "file_path": rel,
            "start_line": 1,
            "end_line": 1,
        },
    )
    if not isinstance(probe, dict):
        raise RuntimeError("get_file_lines returned invalid payload")
    try:
        total_lines = int(probe.get("total_lines") or 0)
    except (TypeError, ValueError):
        total_lines = 0
    if total_lines <= 0:
        return b""
    start_line = 1
    parts: List[str] = []
    while start_line <= total_lines:
        end_line = min(start_line + chunk_size - 1, total_lines)
        data = client.call(
            "get_file_lines",
            {
                "project_id": pid,
                "file_path": rel,
                "start_line": start_line,
                "end_line": end_line,
            },
        )
        if not isinstance(data, dict):
            raise RuntimeError("get_file_lines returned invalid payload")
        lines = data.get("lines")
        if not isinstance(lines, list):
            raise RuntimeError("get_file_lines returned no lines list")
        if not lines:
            break
        parts.extend(str(line) for line in lines)
        start_line += len(lines)
        if start_line > total_lines:
            break
    if not parts:
        return b""
    text = "\n".join(parts)
    if total_lines > 0:
        text += "\n"
    return text.encode("utf-8")


def read_project_file_bytes_via_lines(
    client: "CodeAnalysisClient",
    project_id: str,
    file_path: str,
    *,
    chunk_size: int = 500,
) -> bytes:
    """Read a project file via ``get_file_lines`` (works without ``files.id``)."""
    pid = str(project_id or "").strip()
    errors: List[str] = []
    for rel in candidate_rel_paths_for_project(client, pid, file_path):
        try:
            return _read_project_file_bytes_via_lines_one_path(
                client, pid, rel, chunk_size=chunk_size
            )
        except RuntimeError as exc:
            errors.append(str(exc))
    if errors:
        raise RuntimeError(errors[-1])
    raise RuntimeError(
        f"file not found in project index: {normalize_rel_path(file_path)!r}"
    )


def resolve_file_id_for_path(
    client: "CodeAnalysisClient",
    project_id: str,
    file_path: str,
) -> str:
    """Resolve relative path to files-table UUID via list_project_files (C-023)."""
    from ai_editor.core.exceptions import ValidationError

    pid = str(project_id or "").strip()
    rel = normalize_rel_path(file_path)
    if not pid or not rel:
        raise ValidationError(
            "project_id and file_path are required",
            field="file_path",
            details={"project_id": project_id, "file_path": file_path},
        )
    for item in list_project_file_rows_for_path(client, pid, rel):
        fid = _file_id_from_row(item)
        if fid:
            return fid
    raise RuntimeError(f"file not found in project index: {rel!r}")


def ensure_file_id_for_path(
    client: "CodeAnalysisClient",
    project_id: str,
    file_path: str,
    *,
    session_id: str,
) -> str:
    """Resolve ``files.id``, registering disk-only paths on CA when needed."""
    from ai_editor.core.exceptions import ValidationError

    pid = str(project_id or "").strip()
    rel = normalize_rel_path(file_path)
    sid = str(session_id or "").strip()
    if not sid:
        raise ValidationError(
            "session_id is required to register an unindexed project file",
            field="session_id",
            details={"project_id": project_id, "file_path": file_path},
        )
    rows = list_project_file_rows_for_path(client, pid, rel)
    if not rows:
        disk_registration = _read_project_file_bytes_from_disk(
            client,
            pid,
            rel,
        )
        if disk_registration is None:
            raise RuntimeError(f"file not found in project index: {rel!r}")
        canonical_rel, content = disk_registration
        saved = upload_create_save(
            client,
            session_id=sid,
            project_id=pid,
            file_path=canonical_rel,
            content=content,
        )
        fid = str(saved.get("file_id") or "").strip()
        if fid:
            return fid
        for item in list_project_file_rows_for_path(client, pid, canonical_rel):
            fid = _file_id_from_row(item)
            if fid:
                return fid
        raise RuntimeError(f"file not found in project index: {rel!r}")
    for item in rows:
        fid = _file_id_from_row(item)
        if fid:
            return fid
    canonical_rel = _row_relative_path(rows[0]) or rel
    content = read_project_file_bytes_via_lines(client, pid, canonical_rel)
    saved = upload_create_save(
        client,
        session_id=sid,
        project_id=pid,
        file_path=canonical_rel,
        content=content,
    )
    fid = str(saved.get("file_id") or "").strip()
    if fid:
        return fid
    for item in list_project_file_rows_for_path(client, pid, canonical_rel):
        fid = _file_id_from_row(item)
        if fid:
            return fid
    raise RuntimeError(f"file not found in project index: {rel!r}")


def _read_project_file_bytes_from_disk(
    client: "CodeAnalysisClient",
    project_id: str,
    file_path: str,
) -> tuple[str, bytes] | None:
    """Read an existing disk file for CA registration when the index is stale."""
    try:
        root = client.get_project_root(project_id)
    except Exception as exc:
        logger.debug("cannot resolve project root for disk fallback: %s", exc)
        return None
    root = root.resolve()
    for rel in candidate_rel_paths_for_project(client, project_id, file_path):
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        try:
            if not candidate.is_file():
                continue
        except OSError as exc:
            raise handle_host_file_error(
                file_name=candidate,
                caller_file=__file__,
                method_name="ensure_file_id_for_path:is_file",
                exc=exc,
                logger=logger,
            ) from exc
        content = guard_host_file_operation(
            file_name=candidate,
            caller_file=__file__,
            method_name="ensure_file_id_for_path:read_bytes",
            operation=candidate.read_bytes,
            logger=logger,
        )
        return rel, content
    return None


def download_transfer_to_bytes(
    client: "CodeAnalysisClient",
    transfer_id: str,
) -> bytes:
    """Download chunked transfer payload to memory via JsonRpcClient.download_file."""
    import tempfile

    tid = str(transfer_id or "").strip()
    if not tid:
        raise RuntimeError("download begin returned no transfer_id")
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        client.run_in_isolated_loop(
            lambda rpc, path=tmp.name, transfer=tid: rpc.download_file(transfer, path)
        )
        return Path(tmp.name).read_bytes()


def download_file_bytes(
    client: "CodeAnalysisClient",
    *,
    session_id: Optional[str],
    project_id: str,
    file_id: str,
    lock_mode: str,
) -> bytes:
    """Begin project_file_transfer_download_begin and materialize bytes (C-023)."""
    params: Dict[str, Any] = {
        "project_id": str(project_id).strip(),
        "file_id": str(file_id).strip(),
        "compression": "identity",
        "lock_mode": lock_mode,
        "include_backup_history": False,
    }
    if session_id:
        params["session_id"] = str(session_id).strip()
    begin = client.call("project_file_transfer_download_begin", params)
    if not isinstance(begin, dict):
        raise RuntimeError(
            "project_file_transfer_download_begin returned invalid payload"
        )
    transfer_id = str(begin.get("transfer_id") or "").strip()
    return download_transfer_to_bytes(client, transfer_id)


def upload_bytes_transfer_id(
    client: "CodeAnalysisClient",
    content: bytes,
    *,
    filename: str,
) -> str:
    """Upload in-memory buffer and return transfer_id for upload_save (C-023)."""
    import tempfile

    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        receipt = client.run_in_isolated_loop(
            lambda rpc, path=tmp_path, name=filename: rpc.upload_file(
                path, filename=name, compression="identity"
            )
        )
        transfer_id = _transfer_id_from_payload(receipt)
        if not transfer_id:
            raise RuntimeError("upload buffer returned no transfer_id")
        return transfer_id
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def download_bytes_without_lock(
    client: "CodeAnalysisClient",
    *,
    project_id: str,
    file_path: str,
) -> bytes:
    """Preview download without session_open_file (C-011, C-023)."""
    from ai_editor.core.exceptions import ValidationError

    pid = str(project_id or "").strip()
    rel = normalize_rel_path(file_path)
    if not pid or not rel:
        raise ValidationError(
            "project_id and file_path are required",
            field="file_path",
            details={"project_id": project_id, "file_path": file_path},
        )
    rows = list_project_file_rows_for_path(client, pid, rel)
    if not rows:
        raise RuntimeError(f"file not found in project index: {rel!r}")
    file_id = _file_id_from_row(rows[0])
    if file_id:
        return download_file_bytes(
            client,
            session_id=None,
            project_id=pid,
            file_id=file_id,
            lock_mode="none",
        )
    return read_project_file_bytes_via_lines(client, pid, rel)


def upload_create_save(
    client: "CodeAnalysisClient",
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    content: bytes,
    lock_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload new file content and save on CA in create mode (C-010, C-023).

    When ``lock_mode`` is given (e.g. ``"full"``), the save command acquires the
    session file lock atomically with registering the new file, so the file is
    never registered-but-unlocked. Combined with ``unlock_after_write=False`` the
    lock is retained after the write. Leave ``lock_mode`` as ``None`` for callers
    that only need to register a disk-only path without holding a lock.
    """
    from ai_editor.core.exceptions import ValidationError

    sid = str(session_id or "").strip()
    pid = str(project_id or "").strip()
    rel = normalize_rel_path(file_path)
    if not sid or not pid or not rel:
        raise ValidationError(
            "session_id, project_id, and file_path are required",
            field="session_id",
            details={
                "session_id": session_id,
                "project_id": project_id,
                "file_path": file_path,
            },
        )
    filename = Path(rel).name or "upload.bin"
    transfer_id = upload_bytes_transfer_id(client, content, filename=filename)
    params: Dict[str, Any] = {
        "session_id": sid,
        "project_id": pid,
        "file_path": rel,
        "transfer_id": transfer_id,
        "unlock_after_write": False,
        "backup": True,
        "dry_run": False,
    }
    if lock_mode is not None:
        params["lock_mode"] = lock_mode
    saved = client.call("project_file_transfer_upload_save", params)
    if not isinstance(saved, dict):
        raise RuntimeError("project_file_transfer_upload_save returned invalid payload")
    return saved


def is_ca_save_unsupported_extension_error(exc: BaseException) -> bool:
    """Return true for CA universal-save suffix gaps after editor validation."""
    message = str(exc)
    return (
        "UNSUPPORTED_FILE_EXTENSION" in message
        or "No handler for suffix" in message
    )


def upload_create_save_via_text_stage_move(
    client: "CodeAnalysisClient",
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    content: bytes,
) -> Dict[str, Any]:
    """Persist an editor-validated config file when CA save lacks its suffix.

    Code Analysis transfer-save delegates new-file creation to its own
    universal_file_save registry. AI Editor has structured INI/TOML handlers
    before upload, but older CA deployments do not. Store the exact validated
    bytes through CA's text save path, then move the file to the requested
    project-relative path using CA filesystem lifecycle commands.
    """
    sid = str(session_id or "").strip()
    pid = str(project_id or "").strip()
    rel = normalize_rel_path(file_path)
    suffix = Path(rel).suffix.lower()
    if suffix not in _CA_SAVE_UNSUPPORTED_SUFFIXES:
        raise RuntimeError(f"unsupported staged upload suffix: {suffix or '<none>'}")
    parent = Path(rel).parent
    stage_name = f"__ai_editor_upload_{uuid4().hex}.txt"
    stage_rel = normalize_rel_path(str(parent / stage_name))
    saved = upload_create_save(
        client,
        session_id=sid,
        project_id=pid,
        file_path=stage_rel,
        content=content,
        lock_mode=None,
    )
    try:
        moved = client.call(
            "fs_move",
            {
                "project_id": pid,
                "source_path": stage_rel,
                "dest_path": rel,
                "overwrite": False,
                "backup": True,
            },
        )
    except Exception:
        try:
            client.call(
                "fs_remove",
                {"project_id": pid, "file_path": stage_rel, "backup": False},
            )
        except Exception as cleanup_exc:  # pragma: no cover - diagnostic only
            logger.debug("failed to remove staged upload %s: %s", stage_rel, cleanup_exc)
        raise
    if isinstance(moved, dict):
        return {**saved, **moved, "file_path": rel, "resolved_file_path": rel}
    return {**saved, "file_path": rel, "resolved_file_path": rel}
