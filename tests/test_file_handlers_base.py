"""
Minimal tests for :mod:`ai_editor.core.file_handlers.base` contract.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ai_editor.core.file_handlers.base import (
    BaseFileHandler,
    FileHandlerRequest,
    FileHandlerResult,
    UNSUPPORTED_OPERATION,
    VALIDATION_FAILED,
    validate_before_side_effects,
)
from ai_editor.core.file_handlers.registry import HANDLER_TEXT, get_handler_schema


class _MinimalHandler(BaseFileHandler):
    @property
    def handler_id(self) -> str:
        return HANDLER_TEXT

    def json_schema_for(self, operation: str) -> dict:
        return dict(get_handler_schema(HANDLER_TEXT, operation))

    def read(self, request: FileHandlerRequest) -> FileHandlerResult:
        raise NotImplementedError

    def save(self, request: FileHandlerRequest) -> FileHandlerResult:
        raise NotImplementedError

    def replace(self, request: FileHandlerRequest) -> FileHandlerResult:
        raise NotImplementedError

    def delete(self, request: FileHandlerRequest) -> FileHandlerResult:
        raise NotImplementedError


def test_validate_before_side_effects_empty_project() -> None:
    req = FileHandlerRequest(
        project_id="   ",
        file_path="x.md",
        handler_id="text",
        operation="save",
    )
    out = validate_before_side_effects(req)
    assert out is not None
    assert out.success is False
    assert out.code == VALIDATION_FAILED
    assert out.details["file_path"] == "x.md"


def test_operation_availability_all_four() -> None:
    h = _MinimalHandler()
    avail = h.operation_availability()
    assert set(avail.keys()) == {"delete", "read", "replace", "save"}
    assert all(avail[k] for k in avail)


def test_registration_readiness_uses_json_schema_all_ops() -> None:
    h = _MinimalHandler()
    r = h.registration_readiness()
    assert all(entry["supported"] for entry in r.values())
    assert all(entry["schema_ok"] and entry["ready"] for entry in r.values())


def test_mutating_precheck_rejects_unknown_operation() -> None:
    h = _MinimalHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="a.md",
        handler_id="text",
        operation="warp",
    )
    failed = h.mutating_precheck(req)
    assert failed is not None
    assert failed.code == UNSUPPORTED_OPERATION
