"""
JSON file handler: tree load/modify/save aligned with json_load_file / json_modify_tree / json_save_tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..backup_manager import BackupManager
from ..json_tree.json_saver import save_json_tree_to_file
from ..json_tree.tree_builder import (
    build_tree_from_data,
    load_file_to_tree,
    remove_tree,
)
from ..json_tree.tree_modifier import modify_tree
from .base import (
    VALIDATION_FAILED,
    BaseFileHandler,
    FileHandlerRequest,
    FileHandlerResult,
    standard_error_result,
)
from .diff_support import diff_data_for_text_mutation
from .path_utils import ensure_parent_directories
from .registry import HANDLER_JSON, get_handler_schema
from .text_handler import diff_context_lines_from_extra

JSON_SUFFIXES = frozenset({".json"})

LINE_RANGE_EXTRA_KEYS = frozenset(
    {"start_line", "end_line", "new_lines", "replacements"}
)


def ensure_json_suffix(file_path: str) -> None:
    suf = Path(file_path).suffix.lower()
    if suf not in JSON_SUFFIXES:
        raise ValueError(f"Not a configured JSON suffix: {suf!r}")


def is_registered_json_suffix(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in JSON_SUFFIXES


def _serialize_document(root_data: Any) -> str:
    """Same shape as :mod:`ai_editor.core.json_tree.json_saver` output."""
    return json.dumps(root_data, indent=2, ensure_ascii=False) + "\n"


def _reject_line_range_params(
    extra: Dict[str, Any], *, request: FileHandlerRequest
) -> Optional[FileHandlerResult]:
    overlap = LINE_RANGE_EXTRA_KEYS.intersection(extra.keys())
    if not overlap:
        return None
    return standard_error_result(
        code=VALIDATION_FAILED,
        message=(
            "JSON files use json_pointer/node_id/operations for edits, not plain-text "
            f"line ranges (remove: {sorted(overlap)})"
        ),
        request=request,
        extra_details={"unsupported_keys": sorted(overlap)},
    )


def _require_path_extra(request: FileHandlerRequest) -> Path | FileHandlerResult:
    abs_path = request.extra.get("absolute_path")
    if not isinstance(abs_path, Path):
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="extra.absolute_path (Path) is required",
            request=request,
        )
    try:
        ensure_json_suffix(str(abs_path))
    except ValueError as e:
        return standard_error_result(
            code=VALIDATION_FAILED,
            message=str(e),
            request=request,
        )
    return abs_path


def _require_db_and_root(
    request: FileHandlerRequest,
) -> tuple[Any, Path] | FileHandlerResult:
    database = request.extra.get("database")
    root_dir = request.extra.get("root_dir")
    if database is None:
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="extra.database is required for JSON save that syncs file_data",
            request=request,
        )
    if not isinstance(root_dir, Path):
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="extra.root_dir (Path) is required",
            request=request,
        )
    return database, root_dir.resolve()


class JsonFileHandler(BaseFileHandler):
    """
    Structured JSON edits via JSON Pointer / node_id (``json_modify_tree`` semantics).

    Mutating persistence uses :func:`~ai_editor.core.json_tree.json_saver.save_json_tree_to_file`
    (backup, atomic write, ``update_file_data_atomic_batch``). Callers supply ``absolute_path``,
    and for writes ``database`` + ``root_dir`` resolved from the project.
    """

    @property
    def handler_id(self) -> str:
        return HANDLER_JSON

    def json_schema_for(self, operation: str) -> Dict[str, Any]:
        return get_handler_schema(HANDLER_JSON, operation)

    def read(self, request: FileHandlerRequest) -> FileHandlerResult:
        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )

        raw = abs_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"Invalid JSON: {e}",
                request=request,
            )

        tree = build_tree_from_data(str(abs_path.resolve()), data, register=False)
        nodes = [m.to_dict() for m in tree.metadata_map.values()]
        return FileHandlerResult(
            success=True,
            handler_id=self.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=request.dry_run,
            changed=False,
            data={
                "tree_id": tree.tree_id,
                "file_path": tree.file_path,
                "root_node_id": tree.root_node_id,
                "nodes": nodes,
                "total_nodes": len(nodes),
            },
        )

    def save(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre

        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        content = request.extra.get("content")
        if not isinstance(content, str):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.content (str) is required for JSON save",
                request=request,
            )
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"Invalid JSON: {e}",
                request=request,
            )

        label = Path(request.file_path).name
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        ctx = diff_context_lines_from_extra(request.extra)

        before_text = ""
        if abs_path.exists():
            before_text = abs_path.read_text(encoding="utf-8")
        after_text = _serialize_document(data)

        changed = before_text != after_text
        diff_payload = diff_data_for_text_mutation(
            before_text,
            after_text,
            include_diff=bool(request.diff),
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
                    "serialized": after_text,
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

        db_ex = _require_db_and_root(request)
        if isinstance(db_ex, FileHandlerResult):
            return db_ex
        database, root_dir = db_ex

        tree = build_tree_from_data(str(abs_path.resolve()), data, register=True)
        tid = tree.tree_id
        try:
            result = save_json_tree_to_file(
                tree_id=tid,
                file_path=str(abs_path.resolve()),
                root_dir=root_dir,
                project_id=request.project_id,
                database=database,
                backup=request.backup,
                create_parent_dirs=create_parent_dirs,
            )
        finally:
            remove_tree(tid)

        if not result.get("success"):
            return FileHandlerResult(
                success=False,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=False,
                changed=False,
                message=str(result.get("error", "save failed")),
                code=str(result.get("error_code", VALIDATION_FAILED)),
                details={"file_path": request.file_path, **result},
            )

        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        out_data["save_result"] = result
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

        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        operations = request.extra.get("operations")
        if not isinstance(operations, list):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.operations (list of json_modify_tree ops) is required",
                request=request,
            )

        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )

        before_text = abs_path.read_text(encoding="utf-8")

        tree = load_file_to_tree(str(abs_path.resolve()))
        tid = tree.tree_id
        try:
            try:
                modify_tree(tid, operations)
            except (ValueError, KeyError, TypeError) as e:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message=str(e),
                    request=request,
                    extra_details={"error": str(e)},
                )

            after_text = _serialize_document(tree.root_data)
            changed = before_text != after_text

            label = Path(request.file_path).name
            lbl_a = f"a/{label}"
            lbl_b = f"b/{label}"
            ctx = diff_context_lines_from_extra(request.extra)
            diff_payload = diff_data_for_text_mutation(
                before_text,
                after_text,
                include_diff=bool(request.diff),
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
                        "serialized": after_text,
                    },
                )

            db_ex = _require_db_and_root(request)
            if isinstance(db_ex, FileHandlerResult):
                return db_ex
            database, root_dir = db_ex

            result = save_json_tree_to_file(
                tree_id=tid,
                file_path=str(abs_path.resolve()),
                root_dir=root_dir,
                project_id=request.project_id,
                database=database,
                backup=request.backup,
            )
        finally:
            remove_tree(tid)

        if not result.get("success"):
            return FileHandlerResult(
                success=False,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=False,
                changed=False,
                message=str(result.get("error", "replace save failed")),
                code=str(result.get("error_code", VALIDATION_FAILED)),
                details={"file_path": request.file_path, **result},
            )

        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        out_data["save_result"] = result
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

    def delete(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre

        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        delete_full = bool(request.extra.get("delete_full_file"))
        operations = request.extra.get("operations")

        if delete_full:
            root_dir = request.extra.get("root_dir")
            if not isinstance(root_dir, Path):
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="extra.root_dir (Path) is required for JSON delete_full_file",
                    request=request,
                )
            root_dir = root_dir.resolve()

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

            if not abs_path.exists():
                return FileHandlerResult(
                    success=True,
                    handler_id=request.handler_id,
                    operation=request.operation,
                    file_path=request.file_path,
                    project_id=request.project_id,
                    dry_run=False,
                    changed=False,
                    data={"deleted_file": False},
                )

            backup_uuid: Optional[str] = None
            if request.backup:
                bm = BackupManager(root_dir)
                backup_uuid = bm.create_backup(
                    abs_path,
                    command="json_handler_delete",
                    comment=f"Before delete {request.file_path}",
                )
                if not backup_uuid:
                    return standard_error_result(
                        code=VALIDATION_FAILED,
                        message="create_backup failed; refusing to delete without backup",
                        request=request,
                    )

            abs_path.unlink()
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=False,
                changed=True,
                data={"deleted_file": True, "backup_uuid": backup_uuid},
            )

        if not isinstance(operations, list):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=(
                    "JSON delete requires delete_full_file or extra.operations "
                    "(list of delete actions only)"
                ),
                request=request,
            )

        for op in operations:
            if not isinstance(op, dict):
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="each operation must be an object",
                    request=request,
                )
            action = (op.get("action") or "").lower()
            if action != "delete":
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message=f"JSON handler delete() accepts only action=delete, got {action!r}",
                    request=request,
                )

        return self.replace(request)
