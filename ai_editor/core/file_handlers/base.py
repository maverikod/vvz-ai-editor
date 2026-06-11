"""
Handler contract for universal file commands: read, save, replace, delete.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional

from .registry import HANDLER_IDS, OPERATIONS


# Canonical error codes for handler / universal command responses (lowercase snake).
UNSUPPORTED_OPERATION = "unsupported_operation"
UNSUPPORTED_EXTENSION = "unsupported_extension"
VALIDATION_FAILED = "validation_failed"
SIDE_EFFECT_BLOCKED = "side_effect_blocked"

STANDARD_HANDLER_ERROR_CODES = frozenset(
    {
        UNSUPPORTED_OPERATION,
        UNSUPPORTED_EXTENSION,
        VALIDATION_FAILED,
        SIDE_EFFECT_BLOCKED,
        "INVALID_RANGE",
        "UNSUPPORTED_FILE_EXTENSION",
        "UNSUPPORTED_FILE_OPERATION",
    },
)


@dataclass
class FileHandlerRequest:
    """Common fields for file handler operations (read or mutating)."""

    project_id: str
    file_path: str
    handler_id: str
    operation: str
    dry_run: bool = False
    diff: bool = False
    backup: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileHandlerResult:
    """
    Normalized handler outcome before wrapping in MCP ``SuccessResult``.

    On failure, ``details`` SHOULD include ``file_path``, ``handler_id``, ``operation``.
    Universal commands SHOULD also expose: ``handler_id``, ``operation``, ``file_path``,
    ``project_id``, ``dry_run``, ``changed``.
    """

    success: bool
    handler_id: str
    operation: str
    file_path: str
    project_id: str
    dry_run: bool
    changed: bool = False
    message: str = ""
    code: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)


def standard_error_result(
    *,
    code: str,
    message: str,
    request: FileHandlerRequest,
    changed: bool = False,
    extra_details: Optional[Dict[str, Any]] = None,
) -> FileHandlerResult:
    """
    Build a failed :class:`FileHandlerResult` with required detail keys.

    ``details`` contains at least ``file_path``, ``handler_id``, ``operation``.
    """

    merged: Dict[str, Any] = {
        "file_path": request.file_path,
        "handler_id": request.handler_id,
        "operation": request.operation,
    }
    if extra_details:
        merged.update(extra_details)

    return FileHandlerResult(
        success=False,
        handler_id=request.handler_id,
        operation=request.operation,
        file_path=request.file_path,
        project_id=request.project_id,
        dry_run=request.dry_run,
        changed=changed,
        message=message,
        code=code,
        details=merged,
    )


def validate_before_side_effects(
    request: FileHandlerRequest,
) -> Optional[FileHandlerResult]:
    """
    Validate common mutating prerequisites before backup, writes, DB, or indexing.

    Call this at the start of every mutating handler path (save, replace, delete).
    Returns a :class:`FileHandlerResult` with ``code`` = :data:`VALIDATION_FAILED` when
    validation fails; returns ``None`` when the request passes.

    Side-effect blocking (e.g. dry-run forbidding persistent mutation) SHOULD surface
    as :data:`SIDE_EFFECT_BLOCKED` via the caller or handler after this passes.
    """

    pid = (request.project_id or "").strip()
    if not pid:
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="project_id is required",
            request=request,
        )

    fp = str(request.file_path or "").strip()
    if not fp:
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="file_path is required",
            request=request,
        )

    hid = (request.handler_id or "").strip()
    if hid not in HANDLER_IDS:
        return standard_error_result(
            code=VALIDATION_FAILED,
            message=f"invalid or unknown handler_id: {request.handler_id!r}",
            request=request,
        )

    return None


class BaseFileHandler(ABC):
    """
    Contract: each handler exposes read/save/replace/delete, per-operation JSON schema,
    and reports which operations are supported for pre-registration checks.

    Implementations MUST call :func:`validate_before_side_effects` at the beginning
    of ``save``, ``replace``, and ``delete`` before any backup, filesystem write,
    database update, or index mutation (unless failing earlier with another error).
    """

    @property
    @abstractmethod
    def handler_id(self) -> str:
        """Registry handler id (e.g. ``\"text\"``)."""

    @abstractmethod
    def json_schema_for(self, operation: str) -> Dict[str, Any]:
        """Return JSON-Schema-like object for MCP registration for ``operation``."""

    @abstractmethod
    def read(self, request: FileHandlerRequest) -> FileHandlerResult: ...

    @abstractmethod
    def save(self, request: FileHandlerRequest) -> FileHandlerResult: ...

    @abstractmethod
    def replace(self, request: FileHandlerRequest) -> FileHandlerResult: ...

    @abstractmethod
    def delete(self, request: FileHandlerRequest) -> FileHandlerResult: ...

    def supported_operations(self) -> FrozenSet[str]:
        """Override to omit operations this handler rejects (documented upfront)."""

        return OPERATIONS

    def supports_operation(self, operation: str) -> bool:
        op = (operation or "").lower().strip()
        return op in self.supported_operations()

    def operation_availability(self) -> Dict[str, bool]:
        """Map each of the four canonical operations to whether this handler supports it."""

        return {op: self.supports_operation(op) for op in sorted(OPERATIONS)}

    def registration_readiness(self) -> Dict[str, Dict[str, Any]]:
        """
        Per-operation readiness for universal command registration.

        ``ready`` indicates both support and presence of an object-shaped JSON schema.
        """

        result: Dict[str, Dict[str, Any]] = {}
        for op in sorted(OPERATIONS):
            supported = self.supports_operation(op)
            schema_ok = False
            schema: Dict[str, Any] = {}
            err: Optional[str] = None
            if supported:
                try:
                    schema = self.json_schema_for(op)
                    schema_ok = bool(
                        isinstance(schema, dict) and schema.get("type") == "object"
                    )
                except Exception as e:  # noqa: BLE001 — surface as non-ready
                    err = str(e)
                    schema_ok = False
            result[op] = {
                "supported": supported,
                "schema_ok": schema_ok,
                "ready": supported and schema_ok,
                "schema_error": err,
                "schema_keys": tuple(schema.keys()) if isinstance(schema, dict) else (),
            }
        return result

    def ready_for_all_operations_schema(self) -> bool:
        """True if every supported operation exposes a valid object schema."""

        r = self.registration_readiness()
        return all(v["ready"] for v in r.values() if v["supported"])

    def mutating_precheck(
        self, request: FileHandlerRequest
    ) -> Optional[FileHandlerResult]:
        """
        Call at the start of save/replace/delete: unsupported operation then validation.

        Returns a failed :class:`FileHandlerResult`, or ``None`` to proceed.
        """

        rop = (request.operation or "").lower().strip()
        if not self.supports_operation(rop):
            return standard_error_result(
                code=UNSUPPORTED_OPERATION,
                message=(
                    f"Handler {self.handler_id!r} does not support operation {rop!r}"
                ),
                request=request,
            )

        return validate_before_side_effects(request)


ERROR_CODES = STANDARD_HANDLER_ERROR_CODES
