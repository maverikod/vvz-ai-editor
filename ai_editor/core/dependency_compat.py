"""
Dependency version compatibility checks: queue subsystem, and the tree engine.

Two different policies live here, deliberately, because they guard two
different kinds of damage:

* The queue dependencies (``mcp-proxy-adapter``, ``queuemgr``) are checked
  against a MINIMUM version. Too old means a missing lifecycle feature, so a
  floor is the right rule and only matters when the queue is enabled.
* The tree engine (``ai-editor-tree-engine``) is checked for EXACT equality
  with `ai_editor.version.REQUIRED_TREE_ENGINE_VERSION`. The engine owns node
  identity and the on-disk tree file format; a different engine can write a
  tree file this server cannot read back. That is data corruption, not a
  degraded feature, so there is no compatible range and no minimum -- the
  numbers match or the server does not start.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any, Dict, Optional

from ai_editor.version import (
    REQUIRED_TREE_ENGINE_VERSION,
    TREE_ENGINE_DISTRIBUTION,
    VERSION_FILE,
)

MIN_MCP_PROXY_ADAPTER_VERSION = "8.10.21"
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


# ---------------------------------------------------------------------------
# Server <-> engine: exact equality, enforced at startup.
# ---------------------------------------------------------------------------


class EngineVersionMismatch(RuntimeError):
    """The installed tree engine is not the one this build declares.

    Raised at server startup, before any file is opened. It is a hard refusal,
    not a warning: the engine owns node identity and the on-disk tree file, so
    continuing risks corrupting data on disk rather than merely misbehaving.
    """


def installed_tree_engine_version() -> Optional[str]:
    """Version of the INSTALLED ``ai-editor-tree-engine`` distribution.

    ``None`` means the distribution is not installed at all. That happens in a
    bare source checkout with ``src/`` on ``sys.path``: ``import tree_engine``
    then succeeds while nothing states which version that code is. `None` is
    reported so the caller can say exactly that, instead of letting an
    unidentifiable engine through.
    """
    try:
        return metadata.version(TREE_ENGINE_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None


def assert_tree_engine_version_matches() -> None:
    """Refuse to continue unless the installed engine is the declared one."""
    installed = installed_tree_engine_version()
    if installed == REQUIRED_TREE_ENGINE_VERSION:
        return
    if installed is None:
        detail = (
            f"the {TREE_ENGINE_DISTRIBUTION} distribution is NOT INSTALLED, so "
            "the engine's version cannot be established. An importable "
            "tree_engine package on sys.path (for example a source checkout's "
            "src/ directory) is not enough: only an installed distribution "
            "carries the metadata that says which version it is. Install it, "
            f"for example `pip install '{TREE_ENGINE_DISTRIBUTION}=="
            f"{REQUIRED_TREE_ENGINE_VERSION}'` or, from a checkout of this "
            "repository, `pip install ./src[tree-engine]`."
        )
    else:
        detail = (
            f"the installed {TREE_ENGINE_DISTRIBUTION} is version {installed}. "
            "The versions must be EQUAL, not merely compatible: the engine owns "
            "node identity and the on-disk tree file format, so a mismatched "
            "engine can write a tree file this server cannot read back. "
            f"Install {TREE_ENGINE_DISTRIBUTION}=={REQUIRED_TREE_ENGINE_VERSION} "
            "or run a server build of version " + installed + "."
        )
    raise EngineVersionMismatch(
        f"ai-editor {REQUIRED_TREE_ENGINE_VERSION} refuses to start: " + detail +
        f" The requirement is declared in {VERSION_FILE} and read by "
        "ai_editor/version.py as REQUIRED_TREE_ENGINE_VERSION."
    )
