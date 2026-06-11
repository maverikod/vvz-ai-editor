"""
Public async client for ai-editor-server (JSON-RPC via mcp-proxy-adapter).

``UniversalFileClient`` (via :attr:`~ai_editor_client.client.CodeAnalysisAsyncClient.universal_files`)
is the single supported file-workflow facade for the thin MCP Workflow Surface (C-016).
``FileSessionClient``, ``EditorFileClient``, ``EditorFileHandle``, and ``LocalEditWorkspace``
are deprecated parallel facades (C-020) and emit :class:`DeprecationWarning` on instantiation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

from ai_editor_client.client import CodeAnalysisAsyncClient
from ai_editor_client.commands_proxy import ValidatedCommandsProxy
from ai_editor_client.config import (
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
    load_server_config,
)
from ai_editor_client.editor_file import (
    EditorFileClient as _EditorFileClient,
    EditorFileHandle as _EditorFileHandle,
)
from ai_editor_client.exceptions import ClientValidationError
from ai_editor_client.file_session import (
    FileSessionClient as _FileSessionClient,
    SessionNotFoundError,
)
from ai_editor_client.local_edit_workspace import (
    EditorFileWorkflowError,
    LocalEditWorkspace as _LocalEditWorkspace,
)
from ai_editor_client.server_api import (
    CLIENT_FACADE_COMMANDS,
    CST_REMOVED_COMMANDS,
    FILE_SESSION_COMMANDS,
    FILE_SESSION_FACADE_METHODS,
    LEGACY_REMOVED_COMMANDS,
    REMOVED_COMMANDS,
    TRANSFER_FACADE_METHODS,
    UNIVERSAL_FILE_COMMANDS,
)
from ai_editor_client.universal_file import UniversalFileClient
from ai_editor_client.server_schema import (
    fetch_command_schema_from_server,
    parse_schema_from_help_payload,
)
from ai_editor_client.validation import (
    prepare_params_for_schema,
    validate_params_against_schema,
)

_DEPRECATED_EXPORTS: frozenset[str] = frozenset(
    {
        "FileSessionClient",
        "EditorFileClient",
        "EditorFileHandle",
        "LocalEditWorkspace",
    }
)


def _emit_deprecated_export_warning(class_name: str) -> None:
    warnings.warn(
        (
            f"{class_name} export is deprecated; use UniversalFileClient via "
            "CodeAnalysisAsyncClient.universal_files (C-016). Removal under C-020."
        ),
        DeprecationWarning,
        stacklevel=3,
    )


class _DeprecatedFileSessionClient(_FileSessionClient):
    def __init__(self, client: CodeAnalysisAsyncClient) -> None:
        _emit_deprecated_export_warning("FileSessionClient")
        super().__init__(client)


class _DeprecatedEditorFileClient(_EditorFileClient):
    def __init__(self, file_sessions: FileSessionClient) -> None:
        _emit_deprecated_export_warning("EditorFileClient")
        super().__init__(file_sessions)


class _DeprecatedEditorFileHandle(_EditorFileHandle):
    def __init__(
        self,
        ca_session_id: str,
        project_id: str,
        file_id: str,
        file_path: str,
        baseline_path: Path,
        workspace: Optional[_LocalEditWorkspace] = None,
        is_closed: bool = False,
    ) -> None:
        _emit_deprecated_export_warning("EditorFileHandle")
        super().__init__(
            ca_session_id=ca_session_id,
            project_id=project_id,
            file_id=file_id,
            file_path=file_path,
            baseline_path=baseline_path,
            workspace=workspace,
            is_closed=is_closed,
        )


class _DeprecatedLocalEditWorkspace(_LocalEditWorkspace):
    def __init__(
        self,
        workspace_id: str,
        baseline_path: Path,
        session_dir: Path,
        working_path: Path,
        is_open: bool = True,
    ) -> None:
        _emit_deprecated_export_warning("LocalEditWorkspace")
        super().__init__(
            workspace_id=workspace_id,
            baseline_path=baseline_path,
            session_dir=session_dir,
            working_path=working_path,
            is_open=is_open,
        )


FileSessionClient = _DeprecatedFileSessionClient
EditorFileClient = _DeprecatedEditorFileClient
EditorFileHandle = _DeprecatedEditorFileHandle
LocalEditWorkspace = _DeprecatedLocalEditWorkspace

__all__ = [
    "CLIENT_FACADE_COMMANDS",
    "CST_REMOVED_COMMANDS",
    "ClientValidationError",
    "CodeAnalysisAsyncClient",
    "EditorFileClient",
    "EditorFileHandle",
    "EditorFileWorkflowError",
    "FILE_SESSION_COMMANDS",
    "FILE_SESSION_FACADE_METHODS",
    "FileSessionClient",
    "LEGACY_REMOVED_COMMANDS",
    "LocalEditWorkspace",
    "REMOVED_COMMANDS",
    "SessionNotFoundError",
    "TRANSFER_FACADE_METHODS",
    "UNIVERSAL_FILE_COMMANDS",
    "UniversalFileClient",
    "ValidatedCommandsProxy",
    "adapter_settings_from_server_config",
    "adapter_settings_to_jsonrpc_kwargs",
    "fetch_command_schema_from_server",
    "load_server_config",
    "parse_schema_from_help_payload",
    "prepare_params_for_schema",
    "validate_params_against_schema",
]


def _read_package_version() -> str:
    vf = Path(__file__).resolve().parent / "version.txt"
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip()
    try:
        import importlib.metadata as _imd

        return _imd.version("ai-editor-client")
    except Exception:
        return "0.0.0"


__version__ = _read_package_version()
