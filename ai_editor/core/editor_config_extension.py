"""
AI Editor-specific configuration sections (extension on mcp-proxy-adapter SimpleConfig).

Validates and builds ``code_analysis_server`` and ``ai_editor`` blocks that are
merged into the adapter-generated config.json.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from mcp_proxy_adapter.core.config.simple_config import SSLConfig
from mcp_proxy_adapter.core.config.validators import SSLValidator, ValidationError

from ai_editor.core.config_placeholders import (
    PH_ADVERTISED_HOST,
    PH_CODE_ANALYSIS_HOST,
    build_registration_urls,
)

try:
    from importlib.metadata import version as _pkg_version
except ImportError:  # pragma: no cover
    from importlib_metadata import version as _pkg_version  # type: ignore


def _package_version() -> str:
    try:
        return _pkg_version("ai-editor")
    except Exception:
        return "0.0.0"


LEGACY_CA_HOST = "192.168.254.26"
LEGACY_CA_PORT = 15001
CURRENT_CA_PORT = 15010
DEFAULT_CA_SERVER_ID = "code-analysis-server"
DEFAULT_CA_TIMEOUT = 60.0
DEFAULT_WORKSPACE_ROOT = "data/editor_workspaces"
DEFAULT_AI_EDITOR_LOG = "logs/ai_editor.log"
FORBIDDEN_CA_HOSTS = frozenset({"0.0.0.0", "::", "[::]", ""})


@dataclass(frozen=True)
class EditorConfigValidationIssue:
    """One editor-extension validation finding."""

    level: str
    message: str
    section: Optional[str] = None
    key: Optional[str] = None
    suggestion: Optional[str] = None


class EditorExtensionValidator:
    """Validate ``code_analysis_server`` and ``ai_editor`` sections."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = config_path
        self._ssl = SSLValidator(config_path)

    @staticmethod
    def _coerce_port(value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value if 1 <= value <= 65535 else None
        if isinstance(value, str) and value.strip().isdigit():
            port = int(value.strip())
            return port if 1 <= port <= 65535 else None
        return None

    def validate(
        self, config_data: Mapping[str, Any]
    ) -> List[EditorConfigValidationIssue]:
        issues: List[EditorConfigValidationIssue] = []
        if not isinstance(config_data, Mapping):
            return [
                EditorConfigValidationIssue(
                    level="error",
                    message="Configuration root must be a JSON object",
                )
            ]

        if "upstream" in config_data and "code_analysis_server" not in config_data:
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message=(
                        "Deprecated top-level key 'upstream'; use "
                        "'code_analysis_server' instead"
                    ),
                    section="upstream",
                    suggestion=(
                        "Rename upstream to code_analysis_server or regenerate "
                        "with: python -m ai_editor.cli.config_cli generate"
                    ),
                )
            )

        issues.extend(self._validate_code_analysis_server(config_data))
        issues.extend(self._validate_ai_editor(config_data))
        return issues

    def _validate_code_analysis_server(
        self, config_data: Mapping[str, Any]
    ) -> List[EditorConfigValidationIssue]:
        issues: List[EditorConfigValidationIssue] = []
        section = config_data.get("code_analysis_server")
        if not isinstance(section, dict):
            return [
                EditorConfigValidationIssue(
                    level="error",
                    message="Missing required section: code_analysis_server",
                    section="code_analysis_server",
                    suggestion=(
                        "Add code_analysis_server with host/port/protocol pointing "
                        "to Code Analysis Server (direct JSON-RPC, not MCP proxy URL)"
                    ),
                )
            ]

        host = str(section.get("host") or "").strip()
        if not host:
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message="code_analysis_server.host is required",
                    section="code_analysis_server",
                    key="host",
                )
            )
        elif host in FORBIDDEN_CA_HOSTS:
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message=f"code_analysis_server.host must be reachable: {host!r}",
                    section="code_analysis_server",
                    key="host",
                    suggestion="Use the CA host/IP registered in MCP proxy (not 0.0.0.0)",
                )
            )

        port_raw = section.get("port")
        port = self._coerce_port(port_raw)
        if port is None:
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message=(
                        "code_analysis_server.port must be an integer 1..65535 "
                        "(or ${AI_EDITOR_CODE_ANALYSIS_PORT} placeholder)"
                    ),
                    section="code_analysis_server",
                    key="port",
                )
            )

        protocol = str(section.get("protocol") or "").strip().lower()
        if protocol not in ("http", "https"):
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message="code_analysis_server.protocol must be http or https",
                    section="code_analysis_server",
                    key="protocol",
                )
            )

        timeout = section.get("timeout", DEFAULT_CA_TIMEOUT)
        if timeout is not None:
            try:
                if float(timeout) <= 0:
                    raise ValueError("non-positive")
            except (TypeError, ValueError):
                issues.append(
                    EditorConfigValidationIssue(
                        level="error",
                        message="code_analysis_server.timeout must be a positive number",
                        section="code_analysis_server",
                        key="timeout",
                    )
                )

        transport = section.get("command_transport")
        if transport is not None and str(transport).strip() != "direct":
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message="code_analysis_server.command_transport must be 'direct'",
                    section="code_analysis_server",
                    key="command_transport",
                )
            )

        if host == LEGACY_CA_HOST and port == LEGACY_CA_PORT:
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message=(
                        f"code_analysis_server points to legacy default "
                        f"{LEGACY_CA_HOST}:{LEGACY_CA_PORT}; verify against the "
                        f"registered code-analysis-server URL in MCP proxy"
                    ),
                    section="code_analysis_server",
                    suggestion=(
                        "Set --code-analysis-host/--code-analysis-port to match "
                        "list_servers() server_url for code-analysis-server "
                        f"(expected port {CURRENT_CA_PORT})"
                    ),
                )
            )
        elif port == LEGACY_CA_PORT:
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message=(
                        f"code_analysis_server.port is legacy {LEGACY_CA_PORT}; "
                        f"code-analysis-server listens on {CURRENT_CA_PORT}"
                    ),
                    section="code_analysis_server",
                    key="port",
                    suggestion=(
                        f"Set port to {CURRENT_CA_PORT} or "
                        "${{AI_EDITOR_CODE_ANALYSIS_PORT}} in the container config"
                    ),
                )
            )

        if protocol == "https":
            ssl_raw = section.get("ssl")
            if not isinstance(ssl_raw, dict):
                issues.append(
                    EditorConfigValidationIssue(
                        level="error",
                        message="code_analysis_server.ssl is required for https",
                        section="code_analysis_server",
                        key="ssl",
                    )
                )
            else:
                ssl_cfg = SSLConfig(**ssl_raw)
                for err in self._ssl.validate_ssl_files(
                    ssl_cfg, "code_analysis_server", enabled=True
                ):
                    issues.append(
                        EditorConfigValidationIssue(
                            level="error",
                            message=err.message,
                            section="code_analysis_server",
                        )
                    )
                if not ssl_cfg.cert or not ssl_cfg.key or not ssl_cfg.ca:
                    issues.append(
                        EditorConfigValidationIssue(
                            level="error",
                            message=(
                                "code_analysis_server.ssl requires cert, key, and ca "
                                "for mTLS upstream"
                            ),
                            section="code_analysis_server",
                            key="ssl",
                        )
                    )

        return issues

    def _validate_ai_editor(
        self, config_data: Mapping[str, Any]
    ) -> List[EditorConfigValidationIssue]:
        issues: List[EditorConfigValidationIssue] = []
        section = config_data.get("ai_editor")
        if not isinstance(section, dict):
            return [
                EditorConfigValidationIssue(
                    level="error",
                    message="Missing required section: ai_editor",
                    section="ai_editor",
                )
            ]

        storage = section.get("storage")
        if storage is not None and not isinstance(storage, dict):
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message="ai_editor.storage must be an object",
                    section="ai_editor",
                    key="storage",
                )
            )
        elif isinstance(storage, dict):
            if "editor_workspace_dir" in storage and "workspace_root" not in storage:
                issues.append(
                    EditorConfigValidationIssue(
                        level="error",
                        message=(
                            "ai_editor.storage.editor_workspace_dir is deprecated; "
                            "use workspace_root"
                        ),
                        section="ai_editor",
                        key="storage.editor_workspace_dir",
                        suggestion="Rename to ai_editor.storage.workspace_root",
                    )
                )
            workspace_root = storage.get("workspace_root")
            if workspace_root is not None and not str(workspace_root).strip():
                issues.append(
                    EditorConfigValidationIssue(
                        level="error",
                        message="ai_editor.storage.workspace_root must be non-empty",
                        section="ai_editor",
                        key="storage.workspace_root",
                    )
                )

        log_path = section.get("log")
        if log_path is not None and not str(log_path).strip():
            issues.append(
                EditorConfigValidationIssue(
                    level="error",
                    message="ai_editor.log must be non-empty when set",
                    section="ai_editor",
                    key="log",
                )
            )

        return issues


def adapter_validation_errors_to_issues(
    errors: List[ValidationError],
) -> List[EditorConfigValidationIssue]:
    """Map mcp-proxy-adapter ValidationError list to editor issues."""
    return [
        EditorConfigValidationIssue(level="error", message=err.message)
        for err in errors
    ]


def build_code_analysis_server_section(
    *,
    host: str,
    port: int,
    protocol: str = "https",
    timeout: float = DEFAULT_CA_TIMEOUT,
    server_id: str = DEFAULT_CA_SERVER_ID,
    cert_file: Optional[str] = None,
    key_file: Optional[str] = None,
    ca_cert_file: Optional[str] = None,
    crl_file: Optional[str] = None,
    check_hostname: bool = False,
) -> Dict[str, Any]:
    """Build code_analysis_server block for config.json."""
    section: Dict[str, Any] = {
        "host": host,
        "port": int(port),
        "protocol": protocol,
        "timeout": float(timeout),
        "check_hostname": check_hostname,
        "server_id": server_id,
        "command_transport": "direct",
    }
    if protocol in ("https", "mtls"):
        section["ssl"] = {
            "cert": cert_file,
            "key": key_file,
            "ca": ca_cert_file,
            "crl": crl_file,
            "dnscheck": check_hostname,
            "check_hostname": check_hostname,
        }
    return section


def build_ai_editor_section(
    *,
    server_host: str,
    server_port: int,
    workspace_root: str = DEFAULT_WORKSPACE_ROOT,
    log_path: str = DEFAULT_AI_EDITOR_LOG,
    git_commit_on_write: bool = True,
) -> Dict[str, Any]:
    """Build ai_editor block for config.json."""
    return {
        "git_commit_on_write": git_commit_on_write,
        "host": server_host,
        "port": int(server_port),
        "log": log_path,
        "dirs": [],
        "storage": {"workspace_root": workspace_root},
    }


def merge_editor_extensions(
    config_data: Dict[str, Any],
    *,
    code_analysis_server: Dict[str, Any],
    ai_editor: Dict[str, Any],
    enable_qa_mcp_hooks: bool = False,
    advertised_host: Optional[str] = None,
    registration_protocol: str = "https",
    use_network_placeholders: bool = True,
) -> Dict[str, Any]:
    """Merge editor extension sections into adapter-generated config."""
    merged = dict(config_data)
    merged["code_analysis_server"] = code_analysis_server
    merged["ai_editor"] = ai_editor
    merged["enable_qa_mcp_hooks"] = enable_qa_mcp_hooks

    if use_network_placeholders:
        server = merged.get("server")
        if isinstance(server, dict):
            server = dict(server)
            server["advertised_host"] = advertised_host or PH_ADVERTISED_HOST
            merged["server"] = server

        registration = merged.get("registration")
        if isinstance(registration, dict):
            registration = dict(registration)
            register_url, unregister_url, heartbeat_url = build_registration_urls(
                protocol=registration_protocol
            )
            registration["register_url"] = register_url
            registration["unregister_url"] = unregister_url
            heartbeat = registration.get("heartbeat")
            if isinstance(heartbeat, dict):
                registration["heartbeat"] = {**heartbeat, "url": heartbeat_url}
            else:
                registration["heartbeat"] = {"url": heartbeat_url, "interval": 30}
            merged["registration"] = registration
    elif advertised_host is not None:
        server = merged.get("server")
        if isinstance(server, dict):
            server = dict(server)
            server["advertised_host"] = advertised_host
            merged["server"] = server

    merged.setdefault(
        "server_presentation",
        {
            "title": "AI Editor Server",
            "version": _package_version(),
            "description": (
                "AI Editor server: universal file preview, open, edit, write, and close"
            ),
        },
    )
    merged.setdefault("process_management", {"shutdown_grace_seconds": 10.0})
    merged.setdefault(
        "transport",
        {"type": "https", "verify_client": True, "chk_hostname": False},
    )
    return merged
