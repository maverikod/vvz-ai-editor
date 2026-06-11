"""MCP command: universal_file_preview — facade (C-016).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.preview_command_metadata import (
    get_universal_file_preview_metadata,
)
from ai_editor.commands.universal_file_preview_runtime import run_preview_execute
from ai_editor.core.exceptions import ValidationError
from ai_editor.core.upstream.code_analysis_client import get_code_analysis_client
from ai_editor.core.upstream.session_guard import (
    GuardDecision,
    OperationKind,
    SessionGuard,
)

logger = logging.getLogger(__name__)


class UniversalFilePreviewCommand(BaseMCPCommand):
    """Slim facade delegating preview orchestration to run_preview_execute."""

    name = "universal_file_preview"
    version = "1.0.0"
    descr = "Structured read-only file preview"
    category = "universal_file"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "file_path": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["UniversalFilePreviewCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_universal_file_preview_metadata(cls))

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return super().validate_params(params)

    async def execute(  # type: ignore[override]
        self, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        ca_session_id = str(kwargs.get("session_id", "")).strip()
        if ca_session_id:
            guard = SessionGuard(get_code_analysis_client())
            decision = guard.check(OperationKind.PREVIEW, ca_session_id)
            if decision == GuardDecision.REJECT:
                return ErrorResult(
                    message=f"CA session not found or invalid: {ca_session_id}",
                    code=cast(Any, "SESSION_NOT_FOUND"),
                )
        try:
            return run_preview_execute(self, **kwargs)
        except ValidationError as exc:
            return ErrorResult(message=str(exc), code=cast(Any, "VALIDATION_ERROR"))
        except Exception as exc:
            logger.error("universal_file_preview failed: %s", exc, exc_info=True)
            return ErrorResult(message=str(exc), code=cast(Any, "HANDLER_ERROR"))
