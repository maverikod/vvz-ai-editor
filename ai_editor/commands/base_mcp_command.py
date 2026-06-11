"""
Base class for MCP commands with common functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.exceptions import AIEditorError, ValidationError
from ..core.storage_paths import load_raw_config, resolve_storage_paths, StoragePaths
from ..core.upstream.code_analysis_client import get_code_analysis_client
from .base_mcp_command_resolve_path import resolve_file_path_from_project

logger = logging.getLogger(__name__)


class BaseMCPCommand(Command):
    """Base class for file-editing MCP commands."""

    @staticmethod
    def _open_database_from_config(auto_analyze: bool = False) -> None:
        """Legacy hook: local SQL removed; returns None for call-site compatibility."""
        _ = auto_analyze
        return None

    def _open_database(
        self: "BaseMCPCommand",
        root_dir: Optional[str] = None,
        auto_analyze: bool = False,
    ) -> None:
        _ = (root_dir, auto_analyze)
        return None

    @staticmethod
    def get_code_analysis_client():
        return get_code_analysis_client()

    @staticmethod
    def _resolve_config_path() -> Path:
        try:
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            cfg_path = getattr(cfg, "config_path", None)
            if isinstance(cfg_path, str) and cfg_path.strip():
                return Path(cfg_path).expanduser().resolve()
        except Exception:
            pass
        return (Path.cwd() / "config.json").resolve()

    @staticmethod
    def _get_raw_config() -> Dict[str, Any]:
        config_path = BaseMCPCommand._resolve_config_path()
        return load_raw_config(config_path)

    @staticmethod
    def _get_shared_storage() -> StoragePaths:
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        return resolve_storage_paths(config_data=config_data, config_path=config_path)

    @staticmethod
    def _validate_project_id_exists(project_id: str) -> None:
        if not project_id or not isinstance(project_id, str):
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        project_id = project_id.strip()
        if not project_id:
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        client = get_code_analysis_client()
        project = client.get_project(project_id)
        if not project:
            hint = ""
            if "-" not in project_id or len(project_id) < 36:
                hint = (
                    " Use list_projects on code-analysis-server to get the project id "
                    "(UUID), or read projectid in the project root."
                )
            raise ValidationError(
                f"Project with ID {project_id!r} not found.{hint}",
                field="project_id",
                details={"project_id": project_id},
            )

    @staticmethod
    def _resolve_project_root(project_id: str) -> Path:
        if not project_id:
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        return get_code_analysis_client().get_project_root(project_id)

    @staticmethod
    def _validate_file_path(file_path: str, root_path: Path) -> Path:
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = root_path / file_path_obj
            if not file_path_obj.exists():
                raise ValidationError(
                    f"File does not exist: {file_path}",
                    field="file_path",
                    details={"file_path": file_path, "resolved": str(file_path_obj)},
                )
            if not file_path_obj.is_file():
                raise ValidationError(
                    f"Path is not a file: {file_path}",
                    field="file_path",
                    details={"file_path": file_path, "resolved": str(file_path_obj)},
                )
            return file_path_obj
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                f"Invalid file path: {str(e)}",
                field="file_path",
                details={"file_path": file_path, "error": str(e)},
            ) from e

    @staticmethod
    def _resolve_file_path_from_project(
        database: object,
        project_id: str,
        relative_file_path: str,
        *,
        require_exists: bool = True,
    ) -> Path:
        return resolve_file_path_from_project(
            database,
            project_id,
            relative_file_path,
            require_exists=require_exists,
        )

    def _handle_error(
        self: "BaseMCPCommand",
        error: Exception,
        error_code: str,
        operation: Optional[str] = None,
    ) -> ErrorResult:
        operation_str = f" ({operation})" if operation else ""
        logger.exception("Command failed%s: %s", operation_str, error)
        if isinstance(error, AIEditorError):
            details = error.details.copy()
            details["error_type"] = type(error).__name__
            if hasattr(error, "operation") and error.operation:
                details["operation"] = error.operation
            if hasattr(error, "field") and error.field:
                details["field"] = error.field
            return ErrorResult(
                message=error.message,
                code=error.code or error_code,  # type: ignore[arg-type]
                details=details,
            )
        return ErrorResult(
            message=str(error),
            code=error_code,  # type: ignore[arg-type]
            details={"error_type": type(error).__name__, "error": str(error)},
        )

    @classmethod
    def _get_base_schema_properties(cls: type["BaseMCPCommand"]) -> Dict[str, Any]:
        return {
            "project_id": {
                "type": "string",
                "description": (
                    "Project UUID (from code-analysis-server list_projects). "
                    "Required for commands that operate on a project."
                ),
            },
        }

    @staticmethod
    def _try_validate_schema_value(
        value: Any,
        prop: Dict[str, Any],
        *,
        field: str,
        command_name: str,
    ) -> bool:
        try:
            BaseMCPCommand._validate_schema_value(
                value, prop, field=field, command_name=command_name
            )
            return True
        except ValidationError:
            return False

    @staticmethod
    def _validate_schema_value(
        value: Any,
        prop: Dict[str, Any],
        *,
        field: str,
        command_name: str,
    ) -> None:
        expected_type = prop.get("type")
        one_of = prop.get("oneOf")
        any_of = prop.get("anyOf")
        if expected_type is None and (one_of or any_of):
            branches: list[Dict[str, Any]] = []
            union_label = ""
            if isinstance(one_of, list):
                branches = [b for b in one_of if isinstance(b, dict)]
                union_label = "oneOf"
            elif isinstance(any_of, list):
                branches = [b for b in any_of if isinstance(b, dict)]
                union_label = "anyOf"
            if not branches:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} has empty {union_label}",
                    field=field,
                    details={union_label: one_of or any_of},
                )
            match_count = sum(
                1
                for branch in branches
                if BaseMCPCommand._try_validate_schema_value(
                    value, branch, field=field, command_name=command_name
                )
            )
            if union_label == "anyOf":
                if match_count < 1:
                    raise ValidationError(
                        f"{command_name}: parameter {field!r} must match at least "
                        f"one branch of anyOf, got {type(value).__name__}",
                        field=field,
                        details={"anyOf": any_of},
                    )
            elif match_count < 1:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must match one branch "
                    f"of oneOf, got {type(value).__name__}",
                    field=field,
                    details={"oneOf": one_of},
                )
            if "enum" in prop and value is not None and value not in prop["enum"]:
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be one of {prop['enum']!r}, got {value!r}",
                    field=field,
                    details={"enum": prop["enum"]},
                )
            return

        expected_type = prop.get("type")
        if expected_type == "string":
            if not isinstance(value, str):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be string, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        elif expected_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be integer, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be boolean, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        elif expected_type == "array":
            if not isinstance(value, list):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be array, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        elif expected_type == "object":
            if not isinstance(value, dict):
                raise ValidationError(
                    f"{command_name}: parameter {field!r} must be object, got {type(value).__name__}",
                    field=field,
                    details={},
                )
        if "enum" in prop and value is not None and value not in prop["enum"]:
            raise ValidationError(
                f"{command_name}: parameter {field!r} must be one of {prop['enum']!r}, got {value!r}",
                field=field,
                details={"enum": prop["enum"]},
            )

    @staticmethod
    def validate_params_against_schema(
        params: Dict[str, Any],
        schema: Dict[str, Any],
        command_name: str = "command",
    ) -> None:
        if not isinstance(params, dict):
            raise ValidationError(
                f"{command_name}: params must be a dict, got {type(params).__name__}",
                field="params",
                details={},
            )
        props = schema.get("properties") or {}
        additional_ok = schema.get("additionalProperties", False)
        required_set = set(schema.get("required") or [])
        for key, value in params.items():
            if key not in props:
                if not additional_ok:
                    raise ValidationError(
                        f"{command_name}: unknown parameter {key!r}. "
                        "Only schema-defined properties are allowed.",
                        field=key,
                        details={"allowed": list(props.keys())},
                    )
                continue
            if value is None:
                continue
            BaseMCPCommand._validate_schema_value(
                value, props[key], field=key, command_name=command_name
            )
        for key in required_set:
            if key not in params or params[key] is None:
                raise ValidationError(
                    f"{command_name}: required parameter {key!r} is missing",
                    field=key,
                    details={},
                )

    def validate_params(
        self: "BaseMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        schema = self.get_schema()
        params = {k: v for k, v in params.items() if k != "context"}
        BaseMCPCommand.validate_params_against_schema(
            params, schema, command_name=getattr(self, "name", "command")
        )
        return params
