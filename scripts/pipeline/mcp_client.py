"""
Pipeline client: thin wrapper around mcp-proxy-adapter JsonRpcClient.

Used to poll the running ai-editor-server (started by pipeline). All command
calls go through this client; no direct HTTP or other transport.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient
except Exception:  # pragma: no cover - compatibility fallback
    from mcp_proxy_adapter.client.jsonrpc_client import JsonRpcClient

from scripts.pipeline.config import PipelineConfig

_IMPORT_ERROR: Optional[Exception]

_DIRECT_CLIENT_AVAILABLE = True


try:
    JsonRpcClient  # noqa: B018 - import check
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - depends on environment
    _DIRECT_CLIENT_AVAILABLE = False
    _IMPORT_ERROR = exc


def is_available() -> bool:
    """Return True when mcp-proxy-adapter direct client is importable."""
    return _DIRECT_CLIENT_AVAILABLE


def run_preflight_checks(
    config: Optional[PipelineConfig] = None,
    adapter_settings: Optional[Dict[str, Any]] = None,
    server_config: Optional[Dict[str, Any]] = None,
) -> None:
    """Validate adapter settings against server config before any command call.

    Args:
        config: Shared pipeline configuration instance.
        adapter_settings: Optional explicit adapter settings for validation.
        server_config: Optional explicit server config for validation.

    Raises:
        ValueError: If network or mTLS SSL settings mismatch.
    """
    pipeline_config = config or PipelineConfig()
    reference_server_config = deepcopy(
        server_config or pipeline_config.build_test_config()
    )
    generated_adapter_settings = (
        deepcopy(adapter_settings)
        if adapter_settings is not None
        else pipeline_config.generate_adapter_client_settings()
    )

    try:
        pipeline_config.validate_adapter_settings(
            adapter_settings=generated_adapter_settings,
            server_config=reference_server_config,
        )
    except ValueError as exc:
        raise ValueError(f"MCP preflight failed: {exc}") from exc


class MCPClientWrapper:
    """Sync wrapper around mcp-proxy-adapter JsonRpcClient; pipeline polls server via this.

    Attributes:
        config: Shared pipeline configuration.
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        """Initialize wrapper with deterministic server identity.

        Args:
            config: Shared pipeline configuration.
        """
        self.config = config or PipelineConfig()
        self._preflight_done = False
        self._client: Optional[JsonRpcClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _run_async(self, coroutine: Any) -> Any:
        """Run async coroutine on dedicated loop for wrapper lifetime."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            return self._loop.run_until_complete(coroutine)
        raise RuntimeError(
            "MCPClientWrapper.call_command() cannot run inside an active event loop"
        )

    def _build_direct_client(self) -> JsonRpcClient:
        """Build direct JSON-RPC client from unified network settings."""
        adapter_settings = self.config.generate_adapter_client_settings()
        ssl_settings = adapter_settings.get("ssl", {})
        if not isinstance(ssl_settings, dict):
            ssl_settings = {}
        cert = ssl_settings.get("cert") or ssl_settings.get("cert_path")
        key = ssl_settings.get("key") or ssl_settings.get("key_path")
        ca = ssl_settings.get("ca") or ssl_settings.get("ca_path")
        return JsonRpcClient(
            protocol=str(adapter_settings.get("protocol", "http")),
            host=str(adapter_settings.get("host", "127.0.0.1")),
            port=int(adapter_settings.get("port", 15001)),
            cert=str(cert) if cert else None,
            key=str(key) if key else None,
            ca=str(ca) if ca else None,
            timeout=float(self.config.timeout),
        )

    def _ensure_ready(self) -> None:
        """Validate environment and configuration before first call."""
        if not _DIRECT_CLIENT_AVAILABLE:
            import_error_message = (
                f"{type(_IMPORT_ERROR).__name__}: {_IMPORT_ERROR}"
                if _IMPORT_ERROR is not None
                else "Unknown import error"
            )
            raise RuntimeError(
                "mcp-proxy-adapter direct client is unavailable. "
                "Expected import: mcp_proxy_adapter.client.jsonrpc_client.client.JsonRpcClient. "
                f"Import error: {import_error_message}"
            )
        if not self._preflight_done:
            run_preflight_checks(config=self.config)
            self._client = self._build_direct_client()
            self._preflight_done = True

    @staticmethod
    def _annotate_timing(
        response: Any,
        *,
        command: str,
        use_queue: Optional[bool],
        elapsed_seconds: float,
    ) -> Any:
        """Attach timing metadata and emit deterministic timing trace."""
        mode = "queue" if use_queue else "direct"
        print(
            f"[PIPELINE_TIMING] command={command} mode={mode} elapsed={elapsed_seconds:.3f}s",
            flush=True,
        )
        if isinstance(response, dict):
            response.setdefault("_timing", {})
            timing = response.get("_timing")
            if isinstance(timing, dict):
                timing["command"] = command
                timing["mode"] = mode
                timing["elapsed_seconds"] = elapsed_seconds
        return response

    def call_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_queue: Optional[bool] = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke real server command via direct JsonRpcClient.

        Args:
            command: Registered command name on ai-editor-server.
            params: Command parameters dictionary.
            use_queue: If True, require queued execution and return job info.
            **kwargs: Reserved for backward compatibility.

        Returns:
            Raw command response dictionary.
        """
        self._ensure_ready()
        request_params = params or {}

        client = self._client
        if client is None:
            raise RuntimeError("Direct JsonRpcClient is unavailable after preflight")

        if use_queue is True:
            started = time.perf_counter()
            response = self._run_async(
                client.execute_command_unified(
                    command=command,
                    params=request_params,
                    expect_queue=True,
                    auto_poll=True,
                    timeout=float(self.config.timeout),
                )
            )
            elapsed = time.perf_counter() - started
            return self._annotate_timing(
                response,
                command=command,
                use_queue=use_queue,
                elapsed_seconds=elapsed,
            )

        started = time.perf_counter()
        response = self._run_async(
            client.execute_command(command=command, params=request_params)
        )
        elapsed = time.perf_counter() - started
        return self._annotate_timing(
            response,
            command=command,
            use_queue=use_queue,
            elapsed_seconds=elapsed,
        )


def preflight_check_detects_network_mismatch(
    config: Optional[PipelineConfig] = None,
) -> None:
    """Raise ValueError when host/port/protocol mismatch is not detected."""
    pipeline_config = config or PipelineConfig()
    adapter_settings = pipeline_config.generate_adapter_client_settings()
    bad_settings = deepcopy(adapter_settings)
    bad_settings["port"] = int(adapter_settings.get("port", 15001)) + 1

    try:
        run_preflight_checks(config=pipeline_config, adapter_settings=bad_settings)
    except ValueError:
        return
    raise ValueError("Expected preflight network mismatch was not detected")


def preflight_check_detects_mtls_path_mismatch(
    config: Optional[PipelineConfig] = None,
) -> None:
    """Raise ValueError when mTLS path mismatch is not detected."""
    pipeline_config = config or PipelineConfig()
    server_config = deepcopy(pipeline_config.build_test_config())
    server_section = server_config.setdefault("server", {})
    if not isinstance(server_section, dict):
        server_section = {}
        server_config["server"] = server_section
    server_section["protocol"] = "mtls"
    ssl_section = server_section.setdefault("ssl", {})
    if not isinstance(ssl_section, dict):
        ssl_section = {}
        server_section["ssl"] = ssl_section

    ssl_section["cert"] = ssl_section.get("cert", "/tmp/pipeline-client.crt")
    ssl_section["key"] = ssl_section.get("key", "/tmp/pipeline-client.key")
    ssl_section["ca"] = ssl_section.get("ca", "/tmp/pipeline-client-ca.crt")

    adapter_settings = deepcopy(
        pipeline_config._extract_network_settings(server_config)
    )
    adapter_settings["ssl"] = {
        key: str(Path(str(value)).expanduser().resolve())
        for key, value in pipeline_config._extract_mtls_ssl_paths(server_config).items()
    }

    bad_settings = deepcopy(adapter_settings)
    bad_ssl = deepcopy(adapter_settings["ssl"])
    cert_value = str(bad_ssl.get("cert") or "")
    wrong_cert = str(Path(cert_value).expanduser().resolve()) + ".invalid"
    bad_ssl["cert"] = wrong_cert
    bad_settings["ssl"] = bad_ssl

    try:
        run_preflight_checks(
            config=pipeline_config,
            adapter_settings=bad_settings,
            server_config=server_config,
        )
    except ValueError:
        return
    raise ValueError("Expected preflight mTLS mismatch was not detected")


def call_server_command(
    command: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    use_queue: Optional[bool] = None,
    config: Optional[PipelineConfig] = None,
    **kwargs: Any,
) -> Any:
    """Convenience function to execute command through MCP wrapper."""
    wrapper = MCPClientWrapper(config=config)
    return wrapper.call_command(
        command=command,
        params=params,
        use_queue=use_queue,
        **kwargs,
    )
