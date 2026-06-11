"""
Ops-based CST flow: apply_replace_ops and optionally write to disk.

Runs the ops path (build ReplaceOp list, apply patches, validate, backup, apply).
Used by PythonFileHandler, cst_apply_buffer, and other callers (not a standalone MCP command).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.backup_manager import BackupManager
from ..core.cst_module import ReplaceOp, Selector, apply_replace_ops
from ..core.cst_tree.tree_builder import get_tree
from ..core.exceptions import CSTModulePatchError
from ..core.git_integration import commit_after_write
from .base_mcp_command import BaseMCPCommand
from .compose_cst_validation import ops_from_params
from .project_text_file_guard import reject_if_write_under_project_venv
from .compose_cst_db import backup_file_data
from ..core.database.file_edit_lock import acquire_file_edit_lock_with_retry
from .compose_cst_writer import apply_changes as writer_apply_changes
from .compose_cst_writer import validate_and_write_temp

logger = logging.getLogger(__name__)

_OPS_BACKUP_COMMAND = "run_ops_mode"


def run_ops_mode(
    project_id: str,
    file_path: str,
    root_path: Path,
    ops: List[Dict[str, Any]],
    apply: bool,
    create_backup: bool,
    return_diff: bool,
    commit_message: Optional[str],
    t_start: float,
    t_prev: float,
    tree_id: Optional[str] = None,
    validate_syntax_only: bool = False,
    validate_docstrings: bool = True,
) -> SuccessResult | ErrorResult:
    """
    Execute ops-based compose: build ReplaceOp list, apply_replace_ops, optionally write.

    When apply=false, only return diff/stats. When apply=true, backup + validate + write.
    When ops contain selector kind node_id (UUID4), tree_id from cst_load_file is required.
    When validate_syntax_only=true, skip linter and type checker; docstring
    validation follows validate_docstrings. When validate_syntax_only=false,
    docstring validation is still gated by validate_docstrings.
    """
    target_path = (root_path / file_path).resolve()
    if target_path.suffix.lower() not in (".py", ".pyi", ".pyw"):
        return ErrorResult(
            message="Target file must be a Python source file (.py, .pyi, .pyw)",
            code="INVALID_FILE",
            details={"file_path": str(target_path)},
        )

    if apply:
        blocked = reject_if_write_under_project_venv(target_path, root_path)
        if blocked is not None:
            return blocked

    try:
        replace_ops = ops_from_params(ops)
    except ValueError as e:
        return ErrorResult(
            message=str(e),
            code="INVALID_OPS",
            details={"ops": ops},
        )

    has_node_id_ops = any(
        op.selector.kind == "node_id" and op.selector.node_id for op in replace_ops
    )
    if has_node_id_ops:
        if not tree_id or not str(tree_id).strip():
            return ErrorResult(
                message="tree_id is required when ops contain selector kind node_id (UUID4)",
                code="INVALID_PARAMS",
                details={"hint": "Use tree_id from cst_load_file of the same file"},
            )
        tree = get_tree(tree_id)
        if not tree:
            return ErrorResult(
                message=f"Tree not found: {tree_id}",
                code="TREE_NOT_FOUND",
                details={"tree_id": tree_id},
            )
        resolved: List[ReplaceOp] = []
        for op in replace_ops:
            sel = op.selector
            if sel.kind == "node_id" and sel.node_id:
                meta = tree.metadata_map.get(sel.node_id)
                if not meta:
                    return ErrorResult(
                        message=f"Node not found in tree: {sel.node_id}",
                        code="NODE_NOT_FOUND",
                        details={"node_id": sel.node_id, "tree_id": tree_id},
                    )
                range_sel = Selector(
                    kind="range",
                    start_line=meta.start_line,
                    start_col=meta.start_col,
                    end_line=meta.end_line,
                    end_col=meta.end_col,
                )
                resolved.append(
                    ReplaceOp(
                        selector=range_sel,
                        new_code=op.new_code,
                        file_docstring=op.file_docstring,
                    )
                )
            else:
                resolved.append(op)
        replace_ops = resolved

    if target_path.exists():
        try:
            source = target_path.read_text(encoding="utf-8")
        except Exception as e:
            return ErrorResult(
                message=f"Failed to read file: {e}",
                code="FILE_READ_ERROR",
                details={"file_path": str(target_path)},
            )
    else:
        source = ""

    try:
        new_source, stats = apply_replace_ops(source, replace_ops)
    except CSTModulePatchError as e:
        return ErrorResult(
            message=str(e),
            code="CST_REPLACE_ERROR",
            details=getattr(e, "details", {}),
        )

    new_source = new_source.rstrip("\n\r") + "\n"
    data: Dict[str, Any] = {
        "success": True,
        "file_path": str(target_path),
        "stats": stats,
        "file_written": False,
        "preview_only": False,
    }
    if return_diff:
        diff_lines = difflib.unified_diff(
            source.splitlines(keepends=True),
            new_source.splitlines(keepends=True),
            fromfile=file_path,
            tofile=file_path,
        )
        data["diff"] = "".join(diff_lines)
    if not apply:
        data["applied"] = False
        data["file_written"] = False
        data["preview_only"] = True
        data["message"] = "Preview only; no file written"
        return SuccessResult(data=data)

    file_exists = target_path.exists()
    temp_file, validation_error, validation_results = validate_and_write_temp(
        new_source,
        target_path,
        validate_syntax_only=validate_syntax_only,
        validate_docstrings=validate_docstrings,
    )
    if validation_error:
        return validation_error

    import os

    database = BaseMCPCommand._open_database_from_config(auto_analyze=False)
    backup_manager: Optional[BackupManager] = None
    backup_uuid: Optional[str] = None
    file_data_backup: Optional[Dict[str, Any]] = None
    file_id: Optional[int] = None

    if database is None:
        try:
            if target_path.exists():
                backup_manager = BackupManager(root_path)
                backup_uuid = backup_manager.create_backup(
                    target_path,
                    command=_OPS_BACKUP_COMMAND,
                    comment=commit_message or "",
                )
                if not backup_uuid:
                    if temp_file and temp_file.exists():
                        temp_file.unlink(missing_ok=True)
                    return ErrorResult(
                        message=(
                            "Backup to old_code (versions) is mandatory before write; "
                            f"create_backup failed. Aborting {_OPS_BACKUP_COMMAND}."
                        ),
                        code="BACKUP_REQUIRED",
                        details={"file_path": str(target_path)},
                    )
            os.replace(str(temp_file), str(target_path))
            data.update(
                {
                    "applied": True,
                    "file_written": True,
                    "preview_only": False,
                    "backup_uuid": backup_uuid,
                    "validation_results": validation_results,
                    "skipped_db": True,
                }
            )
            if commit_message:
                commit_after_write(
                    root_path,
                    target_path,
                    _OPS_BACKUP_COMMAND,
                    commit_message_override=commit_message,
                    config_data=BaseMCPCommand._get_raw_config(),
                )
            return SuccessResult(data=data)
        except Exception as err:
            if temp_file and temp_file.exists():
                temp_file.unlink(missing_ok=True)
            return ErrorResult(
                message=str(err),
                code="WRITE_ERROR",
                details={"file_path": str(target_path)},
            )

    try:
        if file_exists:
            from ..core.path_normalization import normalize_path_simple

            normalized_path = normalize_path_simple(str(target_path))
            file_rows = database.select(
                "files",
                where={"path": normalized_path, "project_id": project_id},
                limit=1,
            )
            if file_rows:
                file_record = file_rows[0]
                file_id = file_record["id"]
                file_data_backup = backup_file_data(database, file_id)

        # Mandatory backup before overwriting existing file (versions / old_code)
        if file_exists:
            backup_manager = BackupManager(root_path)
            backup_uuid = backup_manager.create_backup(
                target_path,
                command=_OPS_BACKUP_COMMAND,
                comment=commit_message or "",
            )
            if not backup_uuid:
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                return ErrorResult(
                    message=(
                        "Backup to old_code (versions) is mandatory before write; "
                        f"create_backup failed. Aborting {_OPS_BACKUP_COMMAND}."
                    ),
                    code="BACKUP_REQUIRED",
                    details={"file_path": str(target_path)},
                )

        lock_held = False
        try:
            transaction_id = database.begin_transaction()
            if not transaction_id:
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                return ErrorResult(
                    message="Database transaction could not be started",
                    code="TRANSACTION_ERROR",
                    details={"hint": "Database driver may be busy or unavailable"},
                )

            if file_id:
                if not acquire_file_edit_lock_with_retry(
                    database, file_id, transaction_id=transaction_id
                ):
                    try:
                        database.rollback_transaction(transaction_id)
                    except Exception:
                        pass
                    if temp_file and temp_file.exists():
                        try:
                            temp_file.unlink()
                        except Exception:
                            pass
                    return ErrorResult(
                        message=(
                            f"File is being edited by another process (file_id={file_id}). "
                            "Try again in a moment."
                        ),
                        code="FILE_EDIT_LOCKED",
                        details={"file_id": file_id},
                    )
                lock_held = True

            try:
                result = writer_apply_changes(
                    database=database,
                    transaction_id=transaction_id,
                    project_id=project_id,
                    root_path=root_path,
                    target_path=target_path,
                    source_code=new_source,
                    file_id=file_id,
                    file_data_backup=file_data_backup,
                    backup_uuid=backup_uuid,
                    backup_manager=backup_manager,
                    temp_file=temp_file,
                    _commit_message=commit_message,
                    skip_file_edit_lock=lock_held,
                )
                if isinstance(result, SuccessResult) and result.data:
                    result.data["stats"] = stats
                    if return_diff and "diff" not in result.data:
                        result.data["diff"] = data.get("diff")
                    if validation_results:
                        result.data["validation_results"] = {
                            vt: {
                                "success": vr.success,
                                "error_message": vr.error_message,
                                "errors_count": len(vr.errors),
                            }
                            for vt, vr in validation_results.items()
                        }
                if isinstance(result, SuccessResult):
                    commit_after_write(
                        root_path,
                        [target_path],
                        _OPS_BACKUP_COMMAND,
                        commit_message_override=commit_message,
                        config_data=BaseMCPCommand._get_raw_config(),
                    )
                logger.info(
                    "[PROFILE] %s (ops) total elapsed=%.3fs",
                    _OPS_BACKUP_COMMAND,
                    time.perf_counter() - t_start,
                )
                return result
            except Exception as err:
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                raise err
        finally:
            # Lock is released inside writer_apply_changes before commit when held.
            pass
    finally:
        if database is not None:
            database.disconnect()
