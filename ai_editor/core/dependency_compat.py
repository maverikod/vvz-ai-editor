"""
Dependency version compatibility checks for queue subsystem.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any, Dict

MIN_MCP_PROXY_ADAPTER_VERSION = "8.10.15"
MIN_QUEUEMGR_VERSION = "1.0.20"


def _parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in str(version).split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits == "":
            parts.append(0)
        else:
            parts.append(int(digits))
    return tuple(parts)


def _version_gte(actual: str, minimum: str) -> bool:
    return _parse_version(actual) >= _parse_version(minimum)


def _safe_dist_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except Exception:
        return "unknown"


def collect_dependency_compatibility(queue_enabled: bool) -> Dict[str, Any]:
    ai_editor_version = _safe_dist_version("ai-editor")
    adapter_version = _safe_dist_version("mcp-proxy-adapter")
    queuemgr_version = _safe_dist_version("queuemgr")

    adapter_ok = adapter_version != "unknown" and _version_gte(
        adapter_version, MIN_MCP_PROXY_ADAPTER_VERSION
    )
    queuemgr_ok = queuemgr_version != "unknown" and _version_gte(
        queuemgr_version, MIN_QUEUEMGR_VERSION
    )

    errors: list[str] = []
    if queue_enabled and not adapter_ok:
        errors.append(
            "mcp-proxy-adapter is incompatible for truthful queue status lifecycle "
            f"(installed={adapter_version}, required>={MIN_MCP_PROXY_ADAPTER_VERSION})."
        )
    if queue_enabled and not queuemgr_ok:
        errors.append(
            "queuemgr is incompatible for STOPPED/DELETED lifecycle support "
            f"(installed={queuemgr_version}, required>={MIN_QUEUEMGR_VERSION})."
        )

    queue_ready = (not queue_enabled) or (adapter_ok and queuemgr_ok)
    return {
        "queue_enabled": queue_enabled,
        "queue_ready": queue_ready,
        "errors": errors,
        "versions": {
            "ai_editor_server": ai_editor_version,
            "mcp_proxy_adapter": adapter_version,
            "queuemgr": queuemgr_version,
        },
        "minimum_required": {
            "mcp_proxy_adapter": MIN_MCP_PROXY_ADAPTER_VERSION,
            "queuemgr": MIN_QUEUEMGR_VERSION,
        },
        "compatibility": {
            "mcp_proxy_adapter_ok": adapter_ok,
            "queuemgr_ok": queuemgr_ok,
        },
    }


def assert_queue_dependencies_compatible(queue_enabled: bool) -> None:
    check = collect_dependency_compatibility(queue_enabled=queue_enabled)
    if check["queue_ready"]:
        return
    raise RuntimeError("; ".join(check["errors"]))
