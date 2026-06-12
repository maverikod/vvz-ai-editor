"""
Transfer-layer helpers for code-analysis-server chunked upload/download.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ai_editor.core.upstream.code_analysis_client import CodeAnalysisClient


def normalize_rel_path(file_path: str) -> str:
    """Normalize project-relative path for CA file index matching (C-023)."""
    return str(file_path or "").strip().replace("\\", "/")


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
    data = client.call("list_project_files", {"project_id": pid})
    files = data.get("files") if isinstance(data, dict) else data
    if not isinstance(files, list):
        raise RuntimeError("list_project_files returned no files list")
    for item in files:
        if not isinstance(item, dict):
            continue
        row_path = normalize_rel_path(
            str(
                item.get("relative_path")
                or item.get("path")
                or item.get("file_path")
                or ""
            )
        )
        if row_path == rel:
            fid = str(item.get("file_id") or item.get("id") or "").strip()
            if fid:
                return fid
    raise RuntimeError(f"file not found in project index: {rel!r}")


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
        transfer_id = str(getattr(receipt, "transfer_id", "") or "").strip()
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
    file_id = resolve_file_id_for_path(client, pid, rel)
    return download_file_bytes(
        client,
        session_id=None,
        project_id=pid,
        file_id=file_id,
        lock_mode="none",
    )


def upload_create_save(
    client: "CodeAnalysisClient",
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    content: bytes,
) -> Dict[str, Any]:
    """Upload new file content and save on CA in create mode (C-010, C-023)."""
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
    saved = client.call(
        "project_file_transfer_upload_save",
        {
            "session_id": sid,
            "project_id": pid,
            "file_path": rel,
            "transfer_id": transfer_id,
            "unlock_after_write": False,
            "backup": True,
            "dry_run": False,
        },
    )
    if not isinstance(saved, dict):
        raise RuntimeError("project_file_transfer_upload_save returned invalid payload")
    return saved
