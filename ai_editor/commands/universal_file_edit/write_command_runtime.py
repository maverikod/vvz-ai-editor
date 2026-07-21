"""Runtime orchestration for universal_file_write (preview + CA commit).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import re
import ast
from pathlib import Path
from typing import Any, Dict, cast
from unittest.mock import Mock

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.universal_file_edit.errors import (
    READ_ONLY_SESSION,
    SESSION_FILE_PATH_REQUIRED,
    SESSION_NOT_FOUND,
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
)
from ai_editor.commands.universal_file_edit.session import (
    EditSession,
    resolve_session_for_command,
)
from ai_editor.core.file_handlers.registry import HANDLER_PYTHON
from ai_editor.commands.universal_file_edit.write_compare import (
    CompareResult,
    PreviewDiffStatus,
    compare_session_to_origin,
    failure_preview_diff,
)
from ai_editor.core.file_validation.pre_write_pipeline import validation_error_result
from ai_editor.core.host_filesystem import (
    HostFileOperationError,
    guard_host_file_operation,
)
from ai_editor.commands.universal_file_edit.write_command_extras import (
    verify_ca_readback,
)
from ai_editor.core.file_handlers.diff_support import unified_diff_text

from . import write_command_phases as phases

logger = logging.getLogger(__name__)


def _pathlike_value(value: Any) -> Path | None:
    if isinstance(value, Mock):
        return None
    if not isinstance(value, (str, os.PathLike)):
        return None
    return Path(value)


def _is_unavailable_quality_tool(result: Any) -> bool:
    return not result.errors and str(result.error_message or "").lower() in {
        "flake8 not installed",
        "ruff not installed",
        "mypy not installed",
    }


_MYPY_IMPORT_NOT_FOUND_MODULE_RE = re.compile(r'module named "([^"]+)"')


def _is_isolated_project_import_not_found(result: Any, session: EditSession) -> bool:
    if result.success:
        return False

    file_parts = Path(str(session.file_path).replace("\\", "/")).parts
    if len(file_parts) < 2:
        return False
    project_package = file_parts[0]
    if not project_package or project_package in {".", ".."}:
        return False

    errors = [str(error) for error in getattr(result, "errors", []) if str(error)]
    if not errors:
        return False

    saw_import_error = False
    for line in errors:
        lower_line = line.lower()
        if (
            "editor_workspaces" not in lower_line
            or ".ai_editor_write_" not in lower_line
        ):
            return False
        if ": note:" in lower_line:
            if "missing-imports" in lower_line:
                continue
            return False
        if "[import-not-found]" not in lower_line:
            return False
        if "cannot find implementation or library stub" not in lower_line:
            return False
        match = _MYPY_IMPORT_NOT_FOUND_MODULE_RE.search(line)
        if match is None:
            return False
        module = match.group(1)
        if module != project_package and not module.startswith(f"{project_package}."):
            return False
        saw_import_error = True
    return saw_import_error


def _validation_failure_is_non_blocking(
    validation: Any,
    *,
    session: EditSession,
) -> bool:
    failures: list[tuple[str, Any]] = []
    for name, result in validation.quality_results.items():
        if not result.success:
            failures.append((name, result))
    for result in validation.handler_results.values():
        if not result.success:
            failures.append(("handler", result))

    if not failures:
        return False

    for name, result in failures:
        if _is_unavailable_quality_tool(result):
            continue
        if name == "type_checker" and _is_isolated_project_import_not_found(
            result,
            session,
        ):
            continue
        return False
    return True


def _resolve_validation_project_root(
    session: EditSession,
    *,
    project_id: str,
    client: Any,
    command_project_root: Any = None,
) -> Path | None:
    command_root_path = _pathlike_value(command_project_root)
    if command_root_path is not None:
        resolved = command_root_path.resolve()
        if resolved.is_absolute() and resolved.is_dir():
            return resolved

    project_root = getattr(session.core, "project_root", None)
    root_path = _pathlike_value(project_root)
    if root_path is not None:
        resolved = root_path.resolve()
        if not resolved.is_dir():
            return None
        try:
            session.abs_path.resolve().relative_to(resolved)
        except ValueError:
            return None
        return resolved
    return None


def _validation_target_path(session: EditSession, project_root: Path | None) -> Path:
    if project_root is None:
        return session.abs_path

    rel_path = Path(session.file_path.replace("\\", "/"))
    if rel_path.is_absolute() or any(part == ".." for part in rel_path.parts):
        return session.abs_path
    project_target = project_root / rel_path
    if not session.persisted_on_ca or project_target.parent.exists():
        return project_target
    return session.abs_path


def _simple_sibling_import_paths(source_text: str, file_path: str) -> list[str]:
    """Return same-directory module paths imported by a Python draft."""
    try:
        module = ast.parse(source_text)
    except SyntaxError:
        return []
    rel_target = Path(file_path.replace("\\", "/"))
    parent = rel_target.parent
    paths: list[str] = []
    for node in ast.walk(module):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names if "." not in alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if "." not in node.module:
                names.append(node.module)
        for name in names:
            root = name.split(".", 1)[0].strip()
            if not root or root in {"__future__"}:
                continue
            candidate = (parent / f"{root}.py").as_posix()
            if candidate != rel_target.as_posix() and candidate not in paths:
                paths.append(candidate)
    return paths


def _stage_validation_sibling_imports(
    *,
    session: EditSession,
    source_text: str,
    target_path: Path,
    project_root: Path | None,
    project_id: str,
    client: Any,
) -> list[Path]:
    if session.handler_id != HANDLER_PYTHON:
        return []
    if project_root is not None:
        try:
            target_path.resolve().relative_to(project_root.resolve())
            return []
        except ValueError:
            pass
    staged: list[Path] = []
    for rel in _simple_sibling_import_paths(source_text, session.file_path):
        candidate = target_path.parent / Path(rel).name
        if candidate.exists():
            continue
        try:
            content = client.download_without_lock(project_id=project_id, file_path=rel)
        except Exception:
            continue
        if not isinstance(content, (bytes, bytearray)):
            continue
        candidate.write_bytes(content)
        staged.append(candidate)
    return staged


def _run_write_preview(
    session: EditSession,
    *,
    write_mode_explicit: bool,
    format_python: bool = False,
) -> SuccessResult | ErrorResult:
    if session.format_group == FORMAT_TREE_TEMP:
        return phases.tree_temp_preview(session, format_python=format_python)
    if session.format_group == FORMAT_TEXT:
        return phases.text_preview(session, format_python=format_python)

    if write_mode_explicit:
        return phases.sidecar_preview(session, format_python=format_python)
    return phases.sidecar_first_call_preview(
        session,
        os.getpid(),
        format_python=format_python,
    )


def _commit_response_data(
    *,
    session: EditSession,
    project_id: str,
    ca_session_id: str,
    comparison: Any,
    uploaded: bool,
    verify_after_upload: bool,
    format_python: bool,
    client: Any,
) -> Dict[str, Any]:
    diff = ""
    if comparison.result != CompareResult.EQUAL:
        diff = unified_diff_text(
            comparison.origin_bytes.decode("utf-8"),
            comparison.exported_bytes.decode("utf-8"),
            before_label=str(session.abs_path),
            after_label=str(session.abs_path),
        )
    data: Dict[str, Any] = {
        "success": True,
        "phase": "committed",
        "write_mode": "commit",
        "unchanged": comparison.result == CompareResult.EQUAL,
        "uploaded": uploaded,
        "has_changes": comparison.result != CompareResult.EQUAL,
        "diff": diff,
        "preview_diff": {
            **comparison.preview_diff.as_dict(),
            "applied": uploaded and comparison.result != CompareResult.EQUAL,
        },
        "session_id": ca_session_id,
        "project_id": project_id,
        "file_path": session.file_path,
        "format_python": format_python,
    }
    if verify_after_upload and uploaded:
        data["ca_verify"] = verify_ca_readback(
            client,
            project_id=project_id,
            file_path=session.file_path,
            expected_bytes=comparison.exported_bytes,
        )
    return data


def _run_write_commit_ca(
    session: EditSession,
    *,
    project_id: str,
    ca_session_id: str,
    client: Any,
    format_python: bool = False,
    verify_after_upload: bool = False,
    command_project_root: Any = None,
) -> SuccessResult | ErrorResult:
    try:
        comparison = compare_session_to_origin(
            session,
            format_python=format_python,
        )
    except ValueError as exc:
        return error_result_from_make_error(make_error(WRITE_FAILED, str(exc)))
    # R3: a new file (create=true, never committed) is not yet on CA, so the
    # local origin snapshot is not a CA baseline. It must always be persisted on
    # commit even when no edit changed it since open. An already-persisted file
    # with no changes is a true no-op and skips the upload.
    is_new_file = not session.persisted_on_ca
    if comparison.result == CompareResult.EQUAL and not is_new_file:
        try:
            client.ensure_session_file_lock(
                session_id=ca_session_id,
                project_id=project_id,
                file_path=session.file_path,
            )
        except RuntimeError as exc:
            logger.error("universal_file_write lock check failed: %s", exc)
            return ErrorResult(
                message=str(exc),
                code=cast(Any, "UPSTREAM_LOCK_FAILED"),
                details={
                    "upstream_error": str(exc),
                    "preview_diff": failure_preview_diff(
                        PreviewDiffStatus.EDIT_FAILURE,
                        diagnostics=[str(exc)],
                        comparison=comparison,
                    ).as_dict(),
                },
            )
        except Exception as exc:
            logger.error(
                "universal_file_write lock check failed: %s", exc, exc_info=True
            )
            return ErrorResult(
                message=str(exc),
                code=cast(Any, "UPSTREAM_LOCK_FAILED"),
                details={
                    "upstream_error": str(exc),
                    "preview_diff": failure_preview_diff(
                        PreviewDiffStatus.EDIT_FAILURE,
                        diagnostics=[str(exc)],
                        comparison=comparison,
                    ).as_dict(),
                },
            )
        session.modified = False
        session.tree_temp_mutated = False
        return SuccessResult(
            data=_commit_response_data(
                session=session,
                project_id=project_id,
                ca_session_id=ca_session_id,
                comparison=comparison,
                uploaded=False,
                verify_after_upload=False,
                format_python=format_python,
                client=client,
            )
        )

    source_text = comparison.exported_bytes.decode("utf-8")
    project_root = _resolve_validation_project_root(
        session,
        project_id=project_id,
        client=client,
        command_project_root=command_project_root,
    )
    if project_root is None and _pathlike_value(session.abs_path) is not None:
        from ai_editor.commands.universal_file_edit.edit_draft_path_utils import (
            project_root_near,
        )

        try:
            project_root = project_root_near(session.abs_path)
        except ValueError:
            project_root = None
    validation_target = _validation_target_path(session, project_root)
    staged_imports = _stage_validation_sibling_imports(
        session=session,
        source_text=source_text,
        target_path=validation_target,
        project_root=project_root,
        project_id=project_id,
        client=client,
    )
    try:
        validation = phases.validate_draft_in_project_context(
            session.handler_id,
            source_code=source_text,
            target_path=validation_target,
            project_root=project_root,
        )
    finally:
        for staged in staged_imports:
            staged.unlink(missing_ok=True)
    if validation.temp_path is not None:
        validation.temp_path.unlink(missing_ok=True)
    if not validation.success and not _validation_failure_is_non_blocking(
        validation,
        session=session,
    ):
        result = validation_error_result(
            error_message=validation.error_message or "Validation failed",
            quality_results=validation.quality_results,
            handler_results=validation.handler_results,
        )
        result.details = dict(result.details or {})
        result.details["preview_diff"] = failure_preview_diff(
            PreviewDiffStatus.VALIDATION_FAILURE,
            diagnostics=[
                str(validation.error_message or "Validation failed"),
            ],
            comparison=comparison,
        ).as_dict()
        return result

    try:
        if is_new_file:
            # R3 lock-then-transfer: the CA lock row is created before the file is
            # written. upload_create_and_lock saves under lock_mode="full" (lock
            # precedes the save) and registers the file, so a new file never
            # depends on the watcher having pre-indexed the row. The old failure
            # mode "file not found in project index" cannot occur here.
            accepted = client.upload_create_and_lock(
                session_id=ca_session_id,
                project_id=project_id,
                file_path=session.file_path,
                content=comparison.exported_bytes,
            )
        else:
            accepted = client.upload_session_file_content(
                session_id=ca_session_id,
                project_id=project_id,
                file_path=session.file_path,
                content=comparison.exported_bytes,
            )
    except RuntimeError as exc:
        logger.error("universal_file_write upload failed: %s", exc)
        return ErrorResult(
            message=str(exc),
            code=cast(Any, "UPSTREAM_UPLOAD_FAILED"),
            details={
                "upstream_error": str(exc),
                "preview_diff": failure_preview_diff(
                    PreviewDiffStatus.EDIT_FAILURE,
                    diagnostics=[str(exc)],
                    comparison=comparison,
                ).as_dict(),
            },
        )
    except Exception as exc:
        logger.error("universal_file_write upload failed: %s", exc, exc_info=True)
        return ErrorResult(
            message=str(exc),
            code=cast(Any, "UPSTREAM_UPLOAD_FAILED"),
            details={
                "upstream_error": str(exc),
                "preview_diff": failure_preview_diff(
                    PreviewDiffStatus.EDIT_FAILURE,
                    diagnostics=[str(exc)],
                    comparison=comparison,
                ).as_dict(),
            },
        )

    # The file now exists on CA under a session lock; subsequent commits use the
    # update-existing path and close (R4) will release the lock.
    session.persisted_on_ca = True
    try:
        guard_host_file_operation(
            file_name=session.abs_path,
            caller_file=__file__,
            method_name="_run_write_commit_ca:write_origin_snapshot",
            operation=lambda: session.abs_path.write_bytes(accepted),
            logger=logger,
        )
    except HostFileOperationError as exc:
        return ErrorResult(
            message=str(exc),
            code=cast(Any, exc.code or "HOST_FILE_OPERATION_ERROR"),
            details={
                **(exc.details or {}),
                "preview_diff": failure_preview_diff(
                    PreviewDiffStatus.EDIT_FAILURE,
                    diagnostics=[str(exc)],
                    comparison=comparison,
                ).as_dict(),
            },
        )
    session.modified = False
    session.tree_temp_mutated = False
    return SuccessResult(
        data=_commit_response_data(
            session=session,
            project_id=project_id,
            ca_session_id=ca_session_id,
            comparison=comparison,
            uploaded=True,
            verify_after_upload=verify_after_upload,
            format_python=format_python,
            client=client,
        )
    )


def _sidecar_is_second_call(session: EditSession) -> bool:
    current_pid = os.getpid()
    lock = phases._read_session_lockfile(session)
    return (
        lock is not None
        and lock[0] == current_pid
        and lock[1] == session.session_id
        and phases.lockfile_write_preview_ready(session)
    )


async def run_write_execute(
    *,
    project_id: str,
    session_id: str,
    write_mode: str = "preview",
    write_mode_explicit: bool = False,
    file_path: str = "",
    client: Any,
    command_project_root: Any = None,
    **kwargs: Any,
) -> SuccessResult | ErrorResult:
    format_python = bool(kwargs.get("format_python", False))
    verify_after_upload = bool(kwargs.get("verify_after_upload", False))
    try:
        session = resolve_session_for_command(
            session_id,
            file_path or None,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "SESSION_FILE_PATH_REQUIRED":
            return error_result_from_make_error(
                make_error(
                    SESSION_FILE_PATH_REQUIRED,
                    "file_path is required when the session has multiple open files",
                    details={"session_id": session_id},
                )
            )
        return error_result_from_make_error(
            make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
        )
    if session.read_only:
        return error_result_from_make_error(
            make_error(
                READ_ONLY_SESSION,
                session.read_only_reason
                or "Session is read-only; write commands are blocked.",
                details={"session_id": session_id, "file_path": session.file_path},
            )
        )

    if write_mode == "commit":
        return _run_write_commit_ca(
            session,
            project_id=project_id,
            ca_session_id=session_id,
            client=client,
            format_python=format_python,
            verify_after_upload=verify_after_upload,
            command_project_root=command_project_root,
        )

    if write_mode != "preview":
        return ErrorResult(
            message="write_mode must be 'preview' or 'commit'",
            code=cast(Any, "VALIDATION_ERROR"),
        )

    if (
        session.format_group == FORMAT_SIDECAR
        and not write_mode_explicit
        and _sidecar_is_second_call(session)
    ):
        return _run_write_commit_ca(
            session,
            project_id=project_id,
            ca_session_id=session_id,
            client=client,
            format_python=format_python,
            verify_after_upload=verify_after_upload,
        )

    return _run_write_preview(
        session,
        write_mode_explicit=write_mode_explicit,
        format_python=format_python,
    )
