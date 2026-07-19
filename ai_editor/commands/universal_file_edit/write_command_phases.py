"""Write phase helpers for universal_file_write (preview diffs vs origin).

Restored from pre-thin-server write_command; commit uses CA upload in runtime.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    LOCKFILE_WRITE_PREVIEW_READY,
)
from ai_editor.commands.universal_file_edit.session import EditSession
from ai_editor.commands.universal_file_edit.write_compare import (
    PreviewDiffStatus,
    compare_session_to_origin,
    export_canonical_bytes,
    failure_preview_diff,
)
from ai_editor.core.file_validation.pre_write_pipeline import (
    PreWriteValidationOutcome,
    validate_before_promote,
    write_source_to_temp,
)


def _origin_text(session: EditSession) -> str:
    if session.abs_path.is_file():
        return session.abs_path.read_text(encoding="utf-8")
    return ""


def _preview_success(preview_diff: Any) -> SuccessResult:
    has_changes = preview_diff.content_changed
    return SuccessResult(
        data={
            "success": True,
            "phase": "preview",
            "write_mode": "preview",
            "has_changes": has_changes,
            "unchanged": not has_changes,
            "diff": preview_diff.diff,
            "preview_diff": preview_diff.as_dict(),
        }
    )


def _read_session_lockfile(session: EditSession) -> Optional[Tuple[int, str]]:
    lf = session.lockfile_path
    try:
        parts = lf.read_text(encoding="utf-8").strip().splitlines()
        if len(parts) < 2:
            return None
        return int(parts[0]), parts[1].strip()
    except (OSError, ValueError):
        return None


def lockfile_write_preview_ready(session: EditSession) -> bool:
    lf = session.lockfile_path
    try:
        parts = lf.read_text(encoding="utf-8").strip().splitlines()
        return len(parts) >= 3 and parts[2].strip() == LOCKFILE_WRITE_PREVIEW_READY
    except OSError:
        return False


def write_session_lockfile(
    session: EditSession,
    pid: int,
    *,
    write_preview_ready: bool = False,
) -> None:
    lf = session.lockfile_path
    tmp = Path(f"{lf}.tmp")
    body = f"{pid}\n{session.session_id}"
    if write_preview_ready:
        body = f"{body}\n{LOCKFILE_WRITE_PREVIEW_READY}"
    lf.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(lf)


def generate_code(session: EditSession) -> str:
    """Canonical export as text (no optional black pass)."""
    return export_canonical_bytes(session).decode("utf-8")


def validate_draft_in_project_context(
    handler_id: str,
    *,
    source_code: str,
    target_path: Path,
    project_root: Optional[Path],
    skip_quality_tools: bool = False,
    validate_docstrings: bool = True,
) -> PreWriteValidationOutcome:
    """Validate a draft from the authoritative project environment.

    Edit sessions may keep their draft outside the project tree. Running mypy
    directly against that path changes import resolution and can report a false
    ``import-not-found``. When the real target is inside ``project_root``, write
    the QA temp file beside the real target so validation sees the same package
    and sibling-module context while leaving the project file untouched.
    """
    if project_root is None:
        return validate_before_promote(
            handler_id,
            source_code=source_code,
            target_path=target_path,
            skip_quality_tools=skip_quality_tools,
            validate_docstrings=validate_docstrings,
            project_root=None,
        )

    root = project_root.resolve()
    target = target_path.resolve()
    try:
        relative_target = target.relative_to(root)
    except ValueError:
        relative_target = Path(target.name)

    if target.is_relative_to(root):
        return validate_before_promote(
            handler_id,
            source_code=source_code,
            target_path=target,
            skip_quality_tools=skip_quality_tools,
            validate_docstrings=validate_docstrings,
            project_root=root,
        )

    staging_root = Path(tempfile.mkdtemp(prefix=".ai_editor_validation_", dir=root))
    staged_target = staging_root / relative_target
    staged_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        outcome = validate_before_promote(
            handler_id,
            source_code=source_code,
            target_path=staged_target,
            skip_quality_tools=skip_quality_tools,
            validate_docstrings=validate_docstrings,
            project_root=root,
        )
        if outcome.temp_path is not None:
            outcome.temp_path.unlink(missing_ok=True)
        if not outcome.success:
            return replace(outcome, temp_path=None)
        try:
            promotion_temp = write_source_to_temp(source_code, target)
        except OSError as exc:
            return replace(
                outcome,
                success=False,
                temp_path=None,
                error_message=f"Failed to write temporary file: {exc}",
            )
        return replace(outcome, temp_path=promotion_temp)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def preview_export_vs_origin(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    """Unified diff: origin snapshot (last write) vs canonical session export."""
    try:
        comparison = compare_session_to_origin(session, format_python=format_python)
    except Exception as exc:
        return error_result_from_make_error(
            make_error(
                WRITE_FAILED,
                f"Preview generation failed: {exc}",
                details={
                    "preview_diff": failure_preview_diff(
                        PreviewDiffStatus.EDIT_FAILURE,
                        diagnostics=[str(exc)],
                    ).as_dict()
                },
            )
        )
    return _preview_success(comparison.preview_diff)


def tree_temp_preview(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session, format_python=format_python)


def text_preview(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session, format_python=format_python)


def sidecar_preview(
    session: EditSession,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    return preview_export_vs_origin(session, format_python=format_python)


def sidecar_first_call_preview(
    session: EditSession,
    current_pid: int,
    *,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    """Sidecar legacy two-phase: preview diff + session lockfile (no disk write)."""
    result = preview_export_vs_origin(session, format_python=format_python)
    if isinstance(result, ErrorResult):
        return result
    write_session_lockfile(
        session,
        current_pid,
        write_preview_ready=True,
    )
    return result
