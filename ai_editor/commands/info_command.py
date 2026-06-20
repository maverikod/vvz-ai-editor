"""
MCP command: info — detailed AI Editor workflow guide.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.core.errors import ValidationError

from ai_editor.commands.editor_info_content import build_editor_info_payload


class InfoCommand(Command):
    """Return the full thin-server file edit guide for agent models."""

    name = "info"
    version = "1.0.0"
    descr = "Detailed guide: file edit workflow, examples, format groups, errors"
    category = "system"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        from ai_editor.commands.command_metadata_helpers import empty_params_schema

        return empty_params_schema(
            description="No parameters; returns the full editor workflow guide.",
        )

    @classmethod
    def metadata(cls: type["InfoCommand"]) -> Dict[str, Any]:
        from ai_editor.commands.zero_arg_commands_metadata import info_command_metadata

        return info_command_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return super().validate_params(params)

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:
        params = {k: v for k, v in kwargs.items() if k != "context"}
        try:
            self.validate_params(params)
        except ValidationError as exc:
            data = getattr(exc, "data", None) or {}
            return ErrorResult(
                message=str(exc),
                code="VALIDATION_ERROR",
                details={"field": data.get("field")},
            )
        return SuccessResult(data=build_editor_info_payload())
