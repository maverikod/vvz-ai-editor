"""
Plain-text file handler: strict suffix allowlist; no Python AST/CST/index parsing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .base import (
    VALIDATION_FAILED,
    BaseFileHandler,
    FileHandlerRequest,
    FileHandlerResult,
    standard_error_result,
)
from .diff_support import diff_data_for_text_mutation
from .path_utils import ensure_parent_directories
from .registry import HANDLER_TEXT, get_handler_schema
from .text_ranges import (
    LineRange,
    clamp_read_range,
    merge_adjacent_ranges_for_replace,
    validate_non_overlapping,
    validate_range_against_length,
)

TEXT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc", ".jsonl", ".ndjson"})


def ensure_text_suffix(file_path: str) -> None:
    suf = Path(file_path).suffix.lower()
    if suf not in TEXT_SUFFIXES:
        raise ValueError(f"Not a configured plain-text suffix: {suf}")


def is_registered_plain_text_suffix(file_path: str) -> bool:
    """True when ``file_path`` uses a plain-text suffix handled by this module."""
    return Path(file_path).suffix.lower() in TEXT_SUFFIXES


def read_lines_range_ok(
    absolute_path: Path,
    start_line: int,
    end_line: int,
) -> Dict[str, Any]:
    """Stable payload including clamped lines (read compat; clamp documented in MCP schema)."""
    ensure_text_suffix(str(absolute_path))
    text = absolute_path.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines(keepends=False)
    total_lines = len(all_lines)

    if start_line > end_line:
        return {
            "success": False,
            "code": "INVALID_RANGE",
            "handler_id": HANDLER_TEXT,
            "operation": "read",
            "message": "start_line > end_line",
        }
    if start_line < 1 or end_line < 1:
        return {
            "success": False,
            "code": "INVALID_RANGE",
            "handler_id": HANDLER_TEXT,
            "operation": "read",
            "message": "Lines must be >= 1",
        }

    if total_lines == 0:
        return {
            "success": True,
            "handler_id": HANDLER_TEXT,
            "operation": "read",
            "start_line": 1,
            "end_line": 0,
            "lines": [],
            "total_lines": 0,
        }

    low, high = clamp_read_range(start_line, end_line, total_lines)
    slice_lines = all_lines[low - 1 : high]
    return {
        "success": True,
        "handler_id": HANDLER_TEXT,
        "operation": "read",
        "start_line": low,
        "end_line": high,
        "lines": slice_lines,
        "total_lines": total_lines,
    }


def compute_replace_lines_single_range(
    all_lines: List[str],
    start_line: int,
    end_line: int,
    new_lines: List[str],
) -> List[str]:
    """Replace one inclusive range; strict bounds; bottom-up merge with one pair."""
    lr = LineRange(start_line, end_line)
    return merge_adjacent_ranges_for_replace(all_lines, [(lr, new_lines)])


def compute_replace_lines_multi(
    all_lines: List[str],
    replacements: Sequence[Tuple[int, int, List[str]]],
) -> List[str]:
    """
    Replace many disjoint ranges (1-based inclusive per triple).

    Validates every range before mutating; rejects overlaps (including duplicates).
    """
    pairs = [(LineRange(a, b), nl) for a, b, nl in replacements]
    validate_non_overlapping([r for r, _ in pairs])
    return merge_adjacent_ranges_for_replace(all_lines, pairs)


def join_lines_unix(lines: List[str]) -> str:
    """Join logical lines with ``\\n`` (same convention as legacy text commands)."""
    return "\n".join(lines)


def diff_context_lines_from_extra(extra: Dict[str, Any]) -> int:
    """``extra.diff_context_lines`` for unified diff context (default 3); clamped >= 0."""
    raw = extra.get("diff_context_lines", 3)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 3
    return max(0, n)


def validate_write_range(start_line: int, end_line: int, total_lines: int) -> None:
    validate_range_against_length(start_line, end_line, total_lines, strict=True)


def preview_ranges_replace_lines(
    all_lines: List[str],
    replacements: Sequence[Tuple[int, int, List[str]]],
) -> List[str]:
    """Ranges as triple (start_line, end_line, new_lines) 1-based inclusive."""
    pairs = [(LineRange(a, b), nl) for a, b, nl in replacements]
    return merge_adjacent_ranges_for_replace(all_lines, pairs)


def save_preview(
    before_text: str,
    after_full_text: str,
    *,
    diff: bool,
    before_label: str,
    after_label: str,
    context_lines: int = 3,
) -> Tuple[bool, Dict[str, Any]]:
    """Whether content changed plus stable ``diff`` / ``changed_line_ranges`` payload."""
    changed = before_text != after_full_text
    payload = diff_data_for_text_mutation(
        before_text,
        after_full_text,
        include_diff=diff,
        before_label=before_label,
        after_label=after_label,
        context_lines=context_lines,
    )
    return changed, payload


def lines_after_delete_range(
    all_lines: List[str],
    start_line: int,
    end_line: int,
) -> List[str]:
    """Remove inclusive line range from logical lines."""
    validate_range_against_length(start_line, end_line, len(all_lines), strict=True)
    lo = start_line - 1
    hi = end_line - 1
    return all_lines[:lo] + all_lines[hi + 1 :]


def persist_plain_text_file_metadata(
    database: Any,
    project_id: str,
    absolute_path: Path,
    normalized_path: str,
    source_code: str,
    *,
    skip_file_edit_lock: bool = False,
) -> Dict[str, Any]:
    """
    Update the ``files`` table row only (line count, mtime, ``has_docstring=False``).

    Does not call ``update_file_data_atomic_batch``, AST, CST, or entity indexing.

    When ``skip_file_edit_lock`` is False (default), acquires ``files.editing_pid`` on the
    same open DB transaction as the metadata UPDATE so PostgreSQL does not mix pool
    connections with the transaction connection (deadlock risk with the indexer).

    When ``skip_file_edit_lock`` is True, the caller must already hold ``files.editing_pid``
    (legacy path: single-shot ``update_file`` / ``create_file`` without a nested lock txn).
    """
    if database is None:
        return {"success": True, "skipped_db": True}
    from ..database.file_edit_lock import (
        acquire_file_edit_lock_with_retry,
        release_file_edit_lock,
    )
    from ..database_client.objects.base import BaseObject
    from ..database_client.objects.file import File
    from ..sql_portable import sql_julian_timestamp_now_expr

    existing = database.select(
        "files",
        where={
            "path": normalized_path,
            "project_id": project_id,
        },
    )
    logical_lines = source_code.splitlines(keepends=False)
    lines_count = len(logical_lines)
    last_modified = datetime.fromtimestamp(absolute_path.stat().st_mtime)
    lm_julian = BaseObject._to_timestamp(last_modified)

    base: Dict[str, Any] = {"file_path": str(absolute_path)}

    def _locked_response() -> Dict[str, Any]:
        return {
            "success": False,
            "error": (
                "File is being edited by another live process (file edit lock). "
                "Try again shortly."
            ),
            "error_code": "FILE_EDIT_LOCKED",
            **base,
        }

    if skip_file_edit_lock:
        file_id: Any = None
        try:
            if existing:
                file_record = existing[0]
                file_id = file_record["id"]
                file_obj = File(
                    id=file_id,
                    project_id=project_id,
                    path=normalized_path,
                    lines=lines_count,
                    last_modified=last_modified,
                    has_docstring=False,
                )
                database.update_file(file_obj)
            else:
                file_obj = File(
                    project_id=project_id,
                    path=normalized_path,
                    lines=lines_count,
                    last_modified=last_modified,
                    has_docstring=False,
                )
                created = database.create_file(file_obj)
                file_id = created.id
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": str(e), **base}
        return {
            "success": True,
            "file_id": file_id,
            **base,
            "metadata_only": True,
        }

    now_sql = sql_julian_timestamp_now_expr(database)

    if existing:
        file_record = existing[0]
        file_id = file_record["id"]
        tid = database.begin_transaction()
        if not tid:
            return {
                "success": False,
                "error": "Database transaction could not be started",
                "error_code": "TRANSACTION_ERROR",
                **base,
            }
        try:
            if not acquire_file_edit_lock_with_retry(
                database, file_id, transaction_id=tid
            ):
                database.rollback_transaction(tid)
                return _locked_response()
            update_sql = (
                f"UPDATE files SET lines = ?, last_modified = ?, has_docstring = ?, "
                f"updated_at = {now_sql} WHERE id = ?"
            )
            database.execute(
                update_sql,
                (lines_count, lm_julian, False, file_id),
                transaction_id=tid,
            )
            release_file_edit_lock(database, file_id, transaction_id=tid)
            database.commit_transaction(tid)
        except Exception as e:  # noqa: BLE001
            try:
                database.rollback_transaction(tid)
            except Exception:
                pass
            return {"success": False, "error": str(e), **base}
        return {
            "success": True,
            "file_id": file_id,
            **base,
            "metadata_only": True,
        }

    file_obj = File(
        project_id=project_id,
        path=normalized_path,
        lines=lines_count,
        last_modified=last_modified,
        has_docstring=False,
    )
    try:
        created = database.create_file(file_obj)
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e), **base}
    file_id = created.id

    tid = database.begin_transaction()
    if not tid:
        return {
            "success": False,
            "error": "Database transaction could not be started",
            "error_code": "TRANSACTION_ERROR",
            **base,
        }
    try:
        if not acquire_file_edit_lock_with_retry(database, file_id, transaction_id=tid):
            database.rollback_transaction(tid)
            return _locked_response()
        release_file_edit_lock(database, file_id, transaction_id=tid)
        database.commit_transaction(tid)
    except Exception as e:  # noqa: BLE001
        try:
            database.rollback_transaction(tid)
        except Exception:
            pass
        return {"success": False, "error": str(e), **base}
    return {
        "success": True,
        "file_id": file_id,
        **base,
        "metadata_only": True,
    }


class TextFileHandler(BaseFileHandler):
    """
    Plain-text handler: ``read`` / ``save`` / ``replace`` / ``delete``.

    Mutating operations expect ``request.extra`` to include ``absolute_path`` (:class:`~pathlib.Path`)
    for filesystem access; callers resolve project-relative paths.
    """

    @property
    def handler_id(self) -> str:
        return HANDLER_TEXT

    def json_schema_for(self, operation: str) -> Dict[str, Any]:
        return get_handler_schema(HANDLER_TEXT, operation)

    def read(self, request: FileHandlerRequest) -> FileHandlerResult:
        abs_path = request.extra.get("absolute_path")
        if not isinstance(abs_path, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.absolute_path (Path) is required for text read",
                request=request,
            )
        try:
            ensure_text_suffix(str(abs_path))
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )
        start_line = int(request.extra["start_line"])
        end_line = int(request.extra["end_line"])
        payload = read_lines_range_ok(abs_path, start_line, end_line)
        if not payload.get("success"):
            return FileHandlerResult(
                success=False,
                handler_id=self.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=request.dry_run,
                changed=False,
                message=str(payload.get("message", "read failed")),
                code=str(payload.get("code", "INVALID_RANGE")),
                details={
                    "file_path": request.file_path,
                    "handler_id": self.handler_id,
                    "operation": request.operation,
                },
                data=dict(payload),
            )
        return FileHandlerResult(
            success=True,
            handler_id=self.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=request.dry_run,
            changed=False,
            data=dict(payload),
        )

    def save(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre
        abs_path = request.extra.get("absolute_path")
        if not isinstance(abs_path, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.absolute_path (Path) is required for text save",
                request=request,
            )
        try:
            ensure_text_suffix(str(abs_path))
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )
        content = request.extra.get("content")
        if not isinstance(content, str):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.content (str) is required for text save",
                request=request,
            )
        label = Path(request.file_path).name
        before_text = ""
        if abs_path.exists():
            before_text = abs_path.read_text(encoding="utf-8", errors="replace")

        ctx = diff_context_lines_from_extra(request.extra)
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        changed, diff_payload = save_preview(
            before_text,
            content,
            diff=bool(request.diff),
            before_label=lbl_a,
            after_label=lbl_b,
            context_lines=ctx,
        )

        if request.dry_run:
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=changed,
                data={
                    **diff_payload,
                    "would_change": changed,
                    "would_create": not abs_path.exists(),
                },
            )

        create_parent_dirs = bool(request.extra.get("create_parent_dirs", True))
        parent_err = ensure_parent_directories(
            abs_path, create_parent_dirs=create_parent_dirs
        )
        if parent_err:
            return standard_error_result(
                code="PARENT_DIR_MISSING",
                message=parent_err,
                request=request,
            )

        abs_path.write_text(content, encoding="utf-8")
        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        return FileHandlerResult(
            success=True,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=False,
            changed=changed,
            data=out_data,
        )

    def replace(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre
        abs_path = request.extra.get("absolute_path")
        if not isinstance(abs_path, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.absolute_path (Path) is required for text replace",
                request=request,
            )
        try:
            ensure_text_suffix(str(abs_path))
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )
        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )

        text = abs_path.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines(keepends=False)
        label = Path(request.file_path).name

        multi = request.extra.get("replacements")
        if multi is not None:
            if not isinstance(multi, list):
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="extra.replacements must be a list of [start,end,new_lines]",
                    request=request,
                )
            try:
                triples: List[Tuple[int, int, List[str]]] = []
                for item in multi:
                    if not isinstance(item, (list, tuple)) or len(item) != 3:
                        raise ValueError(
                            "each replacement must be [start_line,end_line,new_lines]"
                        )
                    a, b, nl = item
                    triples.append((int(a), int(b), list(nl)))
                new_lines_out = compute_replace_lines_multi(all_lines, triples)
            except ValueError as e:
                return standard_error_result(
                    code="INVALID_RANGE",
                    message=str(e),
                    request=request,
                    extra_details={"reason": str(e)},
                )
        else:
            try:
                sl = int(request.extra["start_line"])
                el = int(request.extra["end_line"])
                nl = list(request.extra["new_lines"])
            except (KeyError, TypeError, ValueError) as e:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message=f"replace requires start_line, end_line, new_lines: {e}",
                    request=request,
                )
            try:
                new_lines_out = compute_replace_lines_single_range(
                    all_lines, sl, el, nl
                )
            except ValueError as e:
                return standard_error_result(
                    code="INVALID_RANGE",
                    message=str(e),
                    request=request,
                    extra_details={"reason": str(e)},
                )

        after_text = join_lines_unix(new_lines_out)
        ctx = diff_context_lines_from_extra(request.extra)
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        _, diff_payload = save_preview(
            text,
            after_text,
            diff=bool(request.diff),
            before_label=lbl_a,
            after_label=lbl_b,
            context_lines=ctx,
        )

        if request.dry_run:
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=(text != after_text),
                data={**diff_payload, "new_lines": new_lines_out},
            )

        abs_path.write_text(after_text, encoding="utf-8")
        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        out_data["new_lines"] = new_lines_out
        return FileHandlerResult(
            success=True,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=False,
            changed=(text != after_text),
            data=out_data,
        )

    def delete(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre
        abs_path = request.extra.get("absolute_path")
        if not isinstance(abs_path, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.absolute_path (Path) is required for text delete",
                request=request,
            )
        try:
            ensure_text_suffix(str(abs_path))
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )

        delete_full = bool(request.extra.get("delete_full_file"))
        if delete_full:
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

        try:
            sl = int(request.extra["start_line"])
            el = int(request.extra["end_line"])
        except (KeyError, TypeError, ValueError) as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"delete range requires start_line and end_line: {e}",
                request=request,
            )

        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines(keepends=False)
        label = Path(request.file_path).name
        try:
            new_lines_out = lines_after_delete_range(all_lines, sl, el)
        except ValueError as e:
            return standard_error_result(
                code="INVALID_RANGE",
                message=str(e),
                request=request,
                extra_details={"reason": str(e)},
            )
        after_text = join_lines_unix(new_lines_out)
        ctx = diff_context_lines_from_extra(request.extra)
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        _, diff_payload = save_preview(
            text,
            after_text,
            diff=bool(request.diff),
            before_label=lbl_a,
            after_label=lbl_b,
            context_lines=ctx,
        )

        if request.dry_run:
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=(text != after_text),
                data=dict(diff_payload),
            )

        abs_path.write_text(after_text, encoding="utf-8")
        return FileHandlerResult(
            success=True,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=False,
            changed=(text != after_text),
            data=(
                dict(diff_payload)
                if request.diff
                else {"diff": "", "changed_line_ranges": []}
            ),
        )
