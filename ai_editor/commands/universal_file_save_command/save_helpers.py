"""Helpers for universal_file_save handler results."""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.core.file_handlers.base import FileHandlerResult


def _success_from_handler(fr: FileHandlerResult, *, operation: str) -> SuccessResult:
    data: Dict[str, Any] = {
        "success": True,
        "handler_id": fr.handler_id,
        "operation": operation,
        "file_path": fr.file_path,
        "project_id": fr.project_id,
        "dry_run": fr.dry_run,
        "changed": fr.changed,
    }
    data.update(fr.data)
    return SuccessResult(data=data)


def _error_from_handler(fr: FileHandlerResult) -> ErrorResult:
    # FileHandlerResult.code is a string semantic code; ErrorResult is typed as int for
    # JSON-RPC but this codebase uses str codes end-to-end for universal save.
    return ErrorResult(
        message=fr.message or fr.code,
        code=fr.code or "VALIDATION_FAILED",  # type: ignore[arg-type]
        details=fr.details
        or {
            "file_path": fr.file_path,
            "handler_id": fr.handler_id,
            "operation": fr.operation,
        },
    )
