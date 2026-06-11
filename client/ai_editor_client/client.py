"""
Async façade over mcp-proxy-adapter JsonRpcClient for ai-editor-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

try:
    from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient
except Exception:  # pragma: no cover - compatibility with older layouts
    from mcp_proxy_adapter.client.jsonrpc_client import JsonRpcClient

from ai_editor_client.commands_proxy import ValidatedCommandsProxy
from ai_editor_client.config import (
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
    load_server_config,
)
from ai_editor_client.editor_file import EditorFileClient
from ai_editor_client.file_session import FileSessionClient
from ai_editor_client.universal_file import UniversalFileClient
from ai_editor_client.server_schema import fetch_command_schema_from_server
from ai_editor_client.validation import (
    prepare_params_for_schema,
    validate_params_against_schema,
)


def _warn_deprecated_facade(name: str, replacement: str) -> None:
    """Emit a deprecation warning for legacy file-workflow facades."""
    warnings.warn(
        (
            f"{name} is deprecated; use {replacement} "
            "(thin MCP workflow C-016). Removal planned under Legacy Removal Scope (C-020)."
        ),
        DeprecationWarning,
        stacklevel=3,
    )


class CodeAnalysisAsyncClient:
    """Async client: domain commands via :meth:`call` / :meth:`call_unified`; full adapter API on :attr:`rpc`."""

    __slots__ = ("_rpc", "_command_schema_cache", "_commands_proxy")

    def __init__(self, **jsonrpc_kwargs: Any) -> None:
        """Same keyword arguments as ``JsonRpcClient`` (``protocol``, ``host``, ``port``, ``cert``, …)."""
        self._rpc = JsonRpcClient(**jsonrpc_kwargs)
        self._command_schema_cache: Dict[str, Dict[str, Any]] = {}
        self._commands_proxy: Optional[ValidatedCommandsProxy] = None

    @classmethod
    def from_jsonrpc_kwargs(cls, **kwargs: Any) -> CodeAnalysisAsyncClient:
        """Alias for ``CodeAnalysisAsyncClient(**kwargs)``."""
        return cls(**kwargs)

    @classmethod
    def from_adapter_settings(
        cls,
        settings: Mapping[str, Any],
        *,
        timeout: float | None = 60.0,
        check_hostname: bool = False,
        token_header: str | None = None,
        token: str | None = None,
    ) -> CodeAnalysisAsyncClient:
        """Build from a dict like ``PipelineConfig.generate_adapter_client_settings()``."""
        kwargs = adapter_settings_to_jsonrpc_kwargs(
            settings,
            timeout=timeout,
            check_hostname=check_hostname,
            token_header=token_header,
            token=token,
        )
        return cls(**kwargs)

    @classmethod
    def from_server_config(
        cls,
        config: Mapping[str, Any],
        *,
        timeout: float | None = 60.0,
        check_hostname: bool = False,
        token_header: str | None = None,
        token: str | None = None,
    ) -> CodeAnalysisAsyncClient:
        """Derive connection settings from a ai-editor server config object."""
        settings = adapter_settings_from_server_config(config)
        return cls.from_adapter_settings(
            settings,
            timeout=timeout,
            check_hostname=check_hostname,
            token_header=token_header,
            token=token,
        )

    @classmethod
    def from_server_config_path(
        cls,
        path: str | Path,
        *,
        timeout: float | None = 60.0,
        check_hostname: bool = False,
        token_header: str | None = None,
        token: str | None = None,
    ) -> CodeAnalysisAsyncClient:
        """Load ``config.json`` and connect."""
        return cls.from_server_config(
            load_server_config(path),
            timeout=timeout,
            check_hostname=check_hostname,
            token_header=token_header,
            token=token,
        )

    @property
    def rpc(self) -> JsonRpcClient:
        """Underlying mcp-proxy-adapter client (queue, transfer, ``help``, ``execute_command``, …)."""
        return self._rpc

    @property
    def commands(self) -> ValidatedCommandsProxy:
        """Dynamic validated wrappers: schema is loaded from the server via ``help`` (cached)."""
        if self._commands_proxy is None:
            self._commands_proxy = ValidatedCommandsProxy(self)
        return self._commands_proxy

    def clear_command_schema_cache(self) -> None:
        """Drop cached command schemas (after ``reload`` or when server definitions change)."""
        self._command_schema_cache.clear()

    @property
    def file_sessions(self) -> FileSessionClient:
        """Session workflow: ``session_*``, ``subordinate_session_*``, transfer, advisory locks."""
        _warn_deprecated_facade(
            "CodeAnalysisAsyncClient.file_sessions",
            "CodeAnalysisAsyncClient.universal_files",
        )
        return FileSessionClient(self)

    @property
    def universal_files(self) -> UniversalFileClient:
        """Sole supported file-workflow facade for MCP Workflow Surface (C-016).

        Use ``universal_file_*`` commands via :class:`~ai_editor_client.universal_file.UniversalFileClient`.
        """
        return UniversalFileClient(self)

    @property
    def editor_files(self) -> EditorFileClient:
        """Editor workflow via transfer (remote client staging paths)."""
        _warn_deprecated_facade(
            "CodeAnalysisAsyncClient.editor_files",
            "CodeAnalysisAsyncClient.universal_files",
        )
        return EditorFileClient(self.file_sessions)

    async def get_command_schema(
        self, command: str, *, refresh: bool = False
    ) -> Dict[str, Any]:
        """Fetch input JSON schema for ``command`` using server ``help`` (with in-memory cache)."""
        if not refresh and command in self._command_schema_cache:
            return self._command_schema_cache[command]
        schema = await fetch_command_schema_from_server(self._rpc, command)
        self._command_schema_cache[command] = schema
        return schema

    async def call_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        refresh_schema: bool = False,
    ) -> Dict[str, Any]:
        """``help`` → schema on server, shallow local validation, then ``execute_command``."""
        schema = await self.get_command_schema(command, refresh=refresh_schema)
        merged = dict(params or {})
        prepared = prepare_params_for_schema(merged, schema)
        validate_params_against_schema(prepared, schema, command_name=command)
        return await self._rpc.execute_command(
            command,
            prepared,
            use_cmd_endpoint=use_cmd_endpoint,
        )

    async def call_unified_validated(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        refresh_schema: bool = False,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: bool = True,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        """Same as :meth:`call_validated` but uses ``execute_command_unified``."""
        schema = await self.get_command_schema(command, refresh=refresh_schema)
        merged = dict(params or {})
        prepared = prepare_params_for_schema(merged, schema)
        validate_params_against_schema(prepared, schema, command_name=command)
        return await self._rpc.execute_command_unified(
            command,
            prepared,
            use_cmd_endpoint=use_cmd_endpoint,
            expect_queue=expect_queue,
            auto_poll=auto_poll,
            poll_interval=poll_interval,
            timeout=timeout,
            status_hook=status_hook,
        )

    async def call(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
    ) -> Dict[str, Any]:
        """Run any registered server command (sync completion)."""
        return await self._rpc.execute_command(
            command,
            params or {},
            use_cmd_endpoint=use_cmd_endpoint,
        )

    async def call_unified(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cmd_endpoint: bool = False,
        expect_queue: Optional[bool] = None,
        auto_poll: bool = True,
        poll_interval: float = 1.0,
        timeout: Optional[float] = None,
        status_hook: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        """Run a command with optional queue detection and polling (adapter unified path)."""
        return await self._rpc.execute_command_unified(
            command,
            params or {},
            use_cmd_endpoint=use_cmd_endpoint,
            expect_queue=expect_queue,
            auto_poll=auto_poll,
            poll_interval=poll_interval,
            timeout=timeout,
            status_hook=status_hook,
        )

    async def close(self) -> None:
        await self._rpc.close()

    async def __aenter__(self) -> CodeAnalysisAsyncClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()
