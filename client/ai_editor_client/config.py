"""
Map server / adapter-style settings dicts to JsonRpcClient constructor kwargs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _expand_path(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(Path(str(value)).expanduser().resolve())


def _ssl_paths_from_section(ssl_section: Any) -> dict[str, str]:
    if not isinstance(ssl_section, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("cert", "key", "ca", "cert_path", "key_path", "ca_path"):
        raw = ssl_section.get(key)
        expanded = _expand_path(raw) if raw else None
        if expanded:
            out[key] = expanded
    # Normalize aliases to cert/key/ca for downstream comparison / JsonRpcClient
    if "cert" not in out and out.get("cert_path"):
        out["cert"] = out["cert_path"]
    if "key" not in out and out.get("key_path"):
        out["key"] = out["key_path"]
    if "ca" not in out and out.get("ca_path"):
        out["ca"] = out["ca_path"]
    return out


def _network_from_server_config(config: Mapping[str, Any]) -> dict[str, Any]:
    server = config.get("server", {})
    if not isinstance(server, dict):
        server = {}
    host = server.get("host", "127.0.0.1")
    if host in ("0.0.0.0", "::", "[::]"):
        host = "127.0.0.1"
    return {
        "host": host,
        "port": int(server.get("port", 15001)),
        "protocol": server.get("protocol", "http"),
    }


def _client_mtls_paths_from_server_config(config: Mapping[str, Any]) -> dict[str, str]:
    """Prefer client.ssl; fall back to server.ssl (same rules as pipeline)."""
    client_section = config.get("client", {})
    if isinstance(client_section, dict):
        ssl_section = client_section.get("ssl", {})
        if isinstance(ssl_section, dict) and any(
            ssl_section.get(k) for k in ("cert", "cert_path", "key", "key_path")
        ):
            return _ssl_paths_from_section(ssl_section)
    server = config.get("server", {})
    if not isinstance(server, dict):
        return {}
    return _ssl_paths_from_section(server.get("ssl", {}))


def adapter_settings_from_server_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Build adapter-style settings from a ai-editor server config dict."""
    settings = dict(_network_from_server_config(config))
    proto = str(settings.get("protocol", "")).lower()
    if proto == "mtls":
        settings["ssl"] = _client_mtls_paths_from_server_config(config)
    elif proto == "https":
        ssl_paths = _client_mtls_paths_from_server_config(config)
        if ssl_paths.get("cert") and ssl_paths.get("key"):
            settings["ssl"] = ssl_paths
    return settings


def adapter_settings_to_jsonrpc_kwargs(
    settings: Mapping[str, Any],
    *,
    timeout: float | None = 60.0,
    check_hostname: bool = False,
    token_header: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Turn adapter-style settings into keyword args for JsonRpcClient."""
    ssl_section = settings.get("ssl")
    cert = key = ca = None
    if isinstance(ssl_section, dict):
        cert = ssl_section.get("cert") or ssl_section.get("cert_path")
        key = ssl_section.get("key") or ssl_section.get("key_path")
        ca = ssl_section.get("ca") or ssl_section.get("ca_path")
        cert = _expand_path(cert) if cert else None
        key = _expand_path(key) if key else None
        ca = _expand_path(ca) if ca else None

    th = token_header if token_header is not None else settings.get("token_header")
    tok = token if token is not None else settings.get("token")

    return {
        "protocol": str(settings.get("protocol", "http")),
        "host": str(settings.get("host", "127.0.0.1")),
        "port": int(settings.get("port", 8080)),
        "token_header": str(th) if th else None,
        "token": str(tok) if tok else None,
        "cert": cert,
        "key": key,
        "ca": ca,
        "check_hostname": check_hostname,
        "timeout": timeout,
    }


def load_server_config(path: str | Path) -> dict[str, Any]:
    """Load server config.json into a dict."""
    p = Path(path).expanduser()
    with p.open("r", encoding="utf-8") as f:
        data: Any = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Server config must be a JSON object")
    # py3.10: return plain dict for mutability
    return dict(data)
