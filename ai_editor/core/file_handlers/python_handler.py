"""
Python file handler: reads and mutates only via CST-safe paths (compose_cst ops).

Raw plain-text line edits (``start_line`` / ``new_lines`` / …) are rejected for
mutating operations. Writes delegate to :func:`run_ops_mode` (CST replace-ops
pipeline), including parse/lint validation before any backup or filesystem replace
when applying.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..backup_manager import BackupManager
from ...commands.compose_cst_ops_flow import run_ops_mode
from ...commands.line_command_cst_gate import (
    LINE_CMD_DISALLOWED_MSG,
    healthy_parse_blocks_line_ops,
)
from ..cst_tree.tree_builder import get_tree
from ..cst_tree.node_id_markers import strip_persisted_node_ids
from .diff_support import diff_data_for_text_mutation
from .text_handler import diff_context_lines_from_extra
from ..cst_tree.create_python_file import create_new_python_file_from_source
from .path_utils import (
    ensure_parent_directories,
    normalize_trailing_newline,
)
from .base import (
    VALIDATION_FAILED,
    BaseFileHandler,
    FileHandlerRequest,
    FileHandlerResult,
    standard_error_result,
)
from .registry import HANDLER_PYTHON, get_handler_schema

logger = logging.getLogger(__name__)

PYTHON_SUFFIXES = frozenset({".py", ".pyi", ".pyw"})

LINE_RANGE_MUTATION_KEYS = frozenset(
    {"start_line", "end_line", "new_lines", "replacements"}
)


def ensure_python_suffix(file_path: str) -> None:
    suf = Path(file_path).suffix.lower()
    if suf not in PYTHON_SUFFIXES:
        raise ValueError(f"Not a configured Python handler suffix: {suf!r}")


def is_registered_python_suffix(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in PYTHON_SUFFIXES


def _reject_line_mutation_params(
    extra: Dict[str, Any], *, request: FileHandlerRequest
) -> Optional[FileHandlerResult]:
    overlap = LINE_RANGE_MUTATION_KEYS.intersection(extra.keys())
    if not overlap:
        return None
    return standard_error_result(
        code=VALIDATION_FAILED,
        message=(
            "Python files must be edited with CST ops (extra.ops), not plain-text "
            f"line ranges (remove: {sorted(overlap)})"
        ),
        request=request,
        extra_details={"unsupported_keys": sorted(overlap)},
    )


def read_python_lines_payload(
    *,
    project_relative_path: str,
    absolute_path: Path,
    start_line: int,
    end_line: int,
    allow_healthy_line_ops: bool = False,
    allow_line_commands_on_healthy_files: bool = False,
) -> Dict[str, Any]:
    """
    Line-range read aligned with ``get_file_lines`` (clamp, healthy-parse gate).

    Returns a dict with ``success`` bool and either line fields or ``code``/``message``.
    """

    if start_line > end_line:
        return {
            "success": False,
            "code": "INVALID_RANGE",
            "message": f"Invalid range: start_line ({start_line}) > end_line ({end_line})",
        }
    if start_line < 1 or end_line < 1:
        return {
            "success": False,
            "code": "INVALID_RANGE",
            "message": "Line numbers must be >= 1 (1-based)",
        }
    if not absolute_path.exists():
        return {
            "success": False,
            "code": "FILE_NOT_FOUND",
            "message": f"File not found: {absolute_path}",
        }

    text = absolute_path.read_text(encoding="utf-8", errors="replace")
    text, _ = strip_persisted_node_ids(text)
    if healthy_parse_blocks_line_ops(
        text,
        allow_healthy_line_ops=allow_healthy_line_ops,
        allow_line_commands_on_healthy_files=allow_line_commands_on_healthy_files,
        file_path=project_relative_path,
    ):
        return {
            "success": False,
            "code": "USE_CST_COMMANDS",
            "message": LINE_CMD_DISALLOWED_MSG,
        }

    all_lines = text.splitlines(keepends=False)
    total_lines = len(all_lines)
    if total_lines == 0:
        return {
            "success": True,
            "file_path": project_relative_path,
            "start_line": 1,
            "end_line": 0,
            "lines": [],
            "total_lines": 0,
        }

    low = max(1, min(start_line, total_lines))
    high = max(1, min(end_line, total_lines))
    if low > high:
        low, high = high, low
    lines = all_lines[low - 1 : high]
    return {
        "success": True,
        "file_path": project_relative_path,
        "start_line": low,
        "end_line": high,
        "lines": lines,
        "total_lines": total_lines,
    }


def _mcp_to_file_handler_result(
    request: FileHandlerRequest,
    mcp: SuccessResult | ErrorResult,
) -> FileHandlerResult:
    if isinstance(mcp, ErrorResult):
        details = dict(mcp.details or {})
        details.setdefault("file_path", request.file_path)
        details.setdefault("handler_id", request.handler_id)
        details.setdefault("operation", request.operation)
        return FileHandlerResult(
            success=False,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=request.dry_run,
            changed=False,
            message=str(mcp.message),
            code=str(mcp.code),
            details=details,
            data={},
        )

    data = dict(mcp.data or {})
    file_written = bool(data.get("file_written"))
    preview_diff = bool(data.get("diff"))
    changed = file_written or (request.dry_run and bool(preview_diff))
    return FileHandlerResult(
        success=True,
        handler_id=request.handler_id,
        operation=request.operation,
        file_path=request.file_path,
        project_id=request.project_id,
        dry_run=request.dry_run,
        changed=changed,
        message=str(data.get("message", "")),
        data=data,
    )


def _require_root_path(request: FileHandlerRequest) -> Path | FileHandlerResult:
    raw = request.extra.get("root_path")
    if not isinstance(raw, Path):
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="extra.root_path (Path) is required for Python CST operations",
            request=request,
        )
    return raw


def _ops_for_save_new_or_overwrite(
    content: str,
    *,
    root: Path,
    relative_file: str,
) -> List[Dict[str, Any]]:
    """
    Build CST replace ops for full-document save on an **existing** file.

    Uses a line range covering the whole file. Callers that create a new file must
    seed disk content first (see :meth:`PythonFileHandler.save`), then invoke this
    helper so the same overwrite pipeline runs as for established files.
    """
    target = (root / relative_file).resolve()
    if not target.exists():
        return [
            {
                "selector": {"kind": "range", "start_line": 1, "end_line": 1},
                "new_code": content,
            }
        ]
    try:
        existing = target.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    raw_lines = existing.splitlines(keepends=False)
    line_count = max(len(raw_lines), 1)
    return [
        {
            "selector": {"kind": "range", "start_line": 1, "end_line": line_count},
            "new_code": content,
        },
    ]


class PythonFileHandler(BaseFileHandler):
    """
    Python/CST handler: ``read`` (lines or minimal CST view), ``save`` / ``replace``
    / ``delete`` via ``run_ops_mode`` only.

    Mutations require ``extra.root_path`` (project root) and relative ``request.file_path``.

    ``save`` writes ``extra.content`` via CST ops (``module`` selector for new
    files; full line-span ``range`` when overwriting an existing file).
    ``replace`` / non-full ``delete`` use ``extra.ops`` (selector + ``new_code`` per
    :func:`ai_editor.commands.compose_cst_validation.ops_from_params`).
    """

    @property
    def handler_id(self) -> str:
        return HANDLER_PYTHON

    def json_schema_for(self, operation: str) -> Dict[str, Any]:
        return get_handler_schema(HANDLER_PYTHON, operation)

    def read(self, request: FileHandlerRequest) -> FileHandlerResult:
        abs_path = request.extra.get("absolute_path")
        if not isinstance(abs_path, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.absolute_path (Path) is required for Python read",
                request=request,
            )
        try:
            ensure_python_suffix(str(abs_path))
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )

        view_mode = str(request.extra.get("view_mode", "lines")).lower().strip()
        if view_mode in ("cst", "tree", "ast"):
            tree_id = request.extra.get("tree_id")
            if not tree_id or not str(tree_id).strip():
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message=(
                        "view_mode requires extra.tree_id (from cst_load_file) for "
                        "CST tree inspection"
                    ),
                    request=request,
                )
            tree = get_tree(str(tree_id))
            if not tree:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message=f"CST tree not found: {tree_id!r}",
                    request=request,
                    extra_details={"tree_id": str(tree_id)},
                )
            return FileHandlerResult(
                success=True,
                handler_id=self.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=request.dry_run,
                data={
                    "view_mode": view_mode,
                    "tree_id": str(tree_id),
                    "node_count": len(tree.metadata_map),
                },
            )

        try:
            start_line = int(request.extra["start_line"])
            end_line = int(request.extra["end_line"])
        except (KeyError, TypeError, ValueError) as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"read (lines) requires start_line and end_line: {e}",
                request=request,
            )

        allow_healthy = bool(request.extra.get("allow_healthy_line_ops", False))
        allow_on_healthy = bool(
            request.extra.get("allow_line_commands_on_healthy_files", False)
        )
        payload = read_python_lines_payload(
            project_relative_path=request.file_path,
            absolute_path=abs_path,
            start_line=start_line,
            end_line=end_line,
            allow_healthy_line_ops=allow_healthy,
            allow_line_commands_on_healthy_files=allow_on_healthy,
        )
        if not payload.get("success"):
            return FileHandlerResult(
                success=False,
                handler_id=self.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=request.dry_run,
                message=str(payload.get("message", "read failed")),
                code=str(payload.get("code", "INVALID_RANGE")),
                details={
                    "file_path": request.file_path,
                    "handler_id": self.handler_id,
                    "operation": request.operation,
                },
                data=dict(payload),
            )
        payload["handler_id"] = self.handler_id
        payload["operation"] = "read"
        payload["view_mode"] = "lines"
        return FileHandlerResult(
            success=True,
            handler_id=self.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=request.dry_run,
            data=payload,
        )

    def save(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre
        blocked = _reject_line_mutation_params(request.extra, request=request)
        if blocked is not None:
            return blocked

        root = _require_root_path(request)
        if isinstance(root, FileHandlerResult):
            return root

        content = request.extra.get("content")
        if not isinstance(content, str):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.content (str) is required for Python save",
                request=request,
            )

        create_parent_dirs = bool(request.extra.get("create_parent_dirs", True))
        target = (root / request.file_path).resolve()
        existed_before = target.exists()
        parent_err = ensure_parent_directories(
            target, create_parent_dirs=create_parent_dirs
        )
        if parent_err:
            return standard_error_result(
                code="PARENT_DIR_MISSING",
                message=parent_err,
                request=request,
            )

        if not existed_before and request.dry_run:
            label = Path(request.file_path).name
            ctx = diff_context_lines_from_extra(request.extra)
            diff_payload = diff_data_for_text_mutation(
                "",
                normalize_trailing_newline(content),
                include_diff=bool(request.diff),
                before_label=f"a/{label}",
                after_label=f"b/{label}",
                context_lines=ctx,
            )
            normalized = normalize_trailing_newline(content)
            return FileHandlerResult(
                success=True,
                handler_id=self.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=bool(normalized.strip()),
                data={
                    **diff_payload,
                    "would_create": True,
                    "created": True,
                },
            )

        if not existed_before and not request.dry_run:
            database = request.extra.get("database")
            try:
                created = create_new_python_file_from_source(
                    absolute_path=target,
                    project_id=request.project_id,
                    root_dir=root,
                    source_code=content,
                    database=database,
                    create_parent_dirs=create_parent_dirs,
                    backup=bool(request.backup),
                    commit_message=request.extra.get("commit_message"),
                    validate=not bool(request.extra.get("validate_syntax_only", False)),
                )
            except Exception as exc:
                return FileHandlerResult(
                    success=False,
                    error=str(exc),
                    error_code="PYTHON_CREATE_FAILED",
                )

            if not created.get("success"):
                return FileHandlerResult(
                    success=False,
                    handler_id=self.handler_id,
                    operation=request.operation,
                    file_path=request.file_path,
                    project_id=request.project_id,
                    dry_run=False,
                    changed=False,
                    message=str(created.get("error", "create failed")),
                    code=str(created.get("error_code", "CST_CREATE_ERROR")),
                    details=created,
                )

            from ..git_integration import commit_after_write
            from ...commands.base_mcp_command import BaseMCPCommand

            git_cmd = str(
                request.extra.get("git_command_name") or "python_file_handler_save"
            )
            git_ok, git_err = commit_after_write(
                root.resolve(),
                [target],
                git_cmd,
                commit_message_override=request.extra.get("commit_message"),
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after new Python file save: %s", git_err)

            data = dict(created)
            data["handler_id"] = self.handler_id
            data["operation"] = request.operation
            return FileHandlerResult(
                success=True,
                handler_id=self.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=False,
                changed=True,
                data=data,
            )

        ops = _ops_for_save_new_or_overwrite(
            content, root=root, relative_file=request.file_path
        )
        apply = not request.dry_run
        return_diff = bool(request.dry_run or request.diff)
        t0 = time.perf_counter()
        mcp = run_ops_mode(
            project_id=request.project_id,
            file_path=request.file_path,
            root_path=root,
            ops=ops,
            apply=apply,
            create_backup=bool(request.backup) and apply,
            return_diff=return_diff,
            commit_message=request.extra.get("commit_message"),
            t_start=t0,
            t_prev=t0,
            tree_id=request.extra.get("tree_id"),
            validate_syntax_only=bool(request.extra.get("validate_syntax_only", False)),
            validate_docstrings=bool(request.extra.get("validate_docstrings", True)),
        )
        return _mcp_to_file_handler_result(request, mcp)

    def replace(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre
        blocked = _reject_line_mutation_params(request.extra, request=request)
        if blocked is not None:
            return blocked

        root = _require_root_path(request)
        if isinstance(root, FileHandlerResult):
            return root

        raw_ops = request.extra.get("ops")
        if not isinstance(raw_ops, list) or len(raw_ops) == 0:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.ops must be a non-empty list for Python replace",
                request=request,
            )

        apply = not request.dry_run
        return_diff = bool(request.dry_run or request.diff)
        t0 = time.perf_counter()
        mcp = run_ops_mode(
            project_id=request.project_id,
            file_path=request.file_path,
            root_path=root,
            ops=raw_ops,
            apply=apply,
            create_backup=bool(request.backup) and apply,
            return_diff=return_diff,
            commit_message=request.extra.get("commit_message"),
            t_start=t0,
            t_prev=t0,
            tree_id=request.extra.get("tree_id"),
            validate_syntax_only=bool(request.extra.get("validate_syntax_only", False)),
            validate_docstrings=bool(request.extra.get("validate_docstrings", True)),
        )
        return _mcp_to_file_handler_result(request, mcp)

    def delete(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre

        if request.extra.get("delete_full_file"):
            abs_path = request.extra.get("absolute_path")
            if not isinstance(abs_path, Path):
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="extra.absolute_path (Path) is required for full-file delete",
                    request=request,
                )
            try:
                ensure_python_suffix(str(abs_path))
            except ValueError as e:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message=str(e),
                    request=request,
                )
            root = request.extra.get("root_path")
            if not isinstance(root, Path):
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="extra.root_path (Path) is required for backup on delete",
                    request=request,
                )

            if request.dry_run:
                return FileHandlerResult(
                    success=True,
                    handler_id=request.handler_id,
                    operation=request.operation,
                    file_path=request.file_path,
                    project_id=request.project_id,
                    dry_run=True,
                    changed=abs_path.exists(),
                    data={"would_delete_file": True},
                )

            if abs_path.exists() and request.backup:
                bm = BackupManager(root)
                uuid = bm.create_backup(
                    abs_path,
                    command="python_file_handler_delete",
                    comment=str(request.extra.get("commit_message") or ""),
                )
                if not uuid:
                    return standard_error_result(
                        code=VALIDATION_FAILED,
                        message="Backup failed; aborting delete",
                        request=request,
                    )
            if abs_path.exists():
                abs_path.unlink()
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=False,
                changed=True,
                data={"deleted_file": True},
            )

        blocked = _reject_line_mutation_params(request.extra, request=request)
        if blocked is not None:
            return blocked

        root = _require_root_path(request)
        if isinstance(root, FileHandlerResult):
            return root

        raw_ops = request.extra.get("ops")
        if not isinstance(raw_ops, list) or len(raw_ops) == 0:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=(
                    "extra.ops must be a non-empty list for Python delete "
                    "(or set delete_full_file)"
                ),
                request=request,
            )

        apply = not request.dry_run
        return_diff = bool(request.dry_run or request.diff)
        t0 = time.perf_counter()
        mcp = run_ops_mode(
            project_id=request.project_id,
            file_path=request.file_path,
            root_path=root,
            ops=raw_ops,
            apply=apply,
            create_backup=bool(request.backup) and apply,
            return_diff=return_diff,
            commit_message=request.extra.get("commit_message"),
            t_start=t0,
            t_prev=t0,
            tree_id=request.extra.get("tree_id"),
            validate_syntax_only=bool(request.extra.get("validate_syntax_only", False)),
            validate_docstrings=bool(request.extra.get("validate_docstrings", True)),
        )
        return _mcp_to_file_handler_result(request, mcp)
