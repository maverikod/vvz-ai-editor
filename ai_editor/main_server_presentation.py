"""
Resolve OpenAPI / MCP server title, description, and version from config.

Adapter contract (mcp-proxy-adapter >= 8.10.13):
- ``AppFactory.create_app(title=..., description=..., version=...)`` → OpenAPI +
  ``help`` ``tool_info`` (help tier).
- Proxy ``list_servers`` description:
  ``registration.metadata.description`` (list tier, brief).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ai_editor.commands.universal_file_edit.workflow_brief import (
    SERVER_HELP_DESCRIPTION,
    SERVER_LIST_DESCRIPTION,
)

_DEFAULT_TITLE = "AI Editor Server"


@dataclass(frozen=True)
class ServerPresentation:
    """Resolved server presentation tiers."""

    title: str
    help_description: str
    list_description: str
    version: str


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("ai-editor")
    except Exception:
        return "1.0.4"


def resolve_server_presentation(app_config: Dict[str, Any]) -> ServerPresentation:
    """
    Build presentation tiers for FastAPI/help and proxy list_servers.

    Config keys under ``server_presentation``:
    - ``description`` — help tier (OpenAPI / server help); enough to start working.
    - ``list_description`` — brief card for ``list_servers`` (optional).
    - ``title``

    ``version`` is NEVER read from config — it always comes from the installed
    ``ai-editor`` package (see ``_package_version``), matching what ``health``
    reports, so ``help``/``tool_info``/registration can never drift stale
    against a config file that was not refreshed on deploy (bug 8fefd757).
    """
    pres = app_config.get("server_presentation")
    if not isinstance(pres, dict):
        pres = {}

    reg = app_config.get("registration")
    if not isinstance(reg, dict):
        reg = {}
    reg_meta = reg.get("metadata")
    if not isinstance(reg_meta, dict):
        reg_meta = {}

    title = (
        pres.get("title")
        or reg.get("server_name")
        or reg_meta.get("server_name")
        or reg.get("server_id")
        or reg_meta.get("server_id")
        or _DEFAULT_TITLE
    )
    help_description = (
        pres.get("description")
        or reg_meta.get("help_description")
        or SERVER_HELP_DESCRIPTION
    )
    list_description = (
        pres.get("list_description")
        or reg_meta.get("list_description")
        or SERVER_LIST_DESCRIPTION
    )
    version = _package_version()
    return ServerPresentation(
        title=str(title),
        help_description=str(help_description),
        list_description=str(list_description),
        version=str(version),
    )


def resolve_server_presentation_legacy(
    app_config: Dict[str, Any],
) -> Tuple[str, str, str]:
    """Backward-compatible 3-tuple: title, help_description, version."""
    p = resolve_server_presentation(app_config)
    return p.title, p.help_description, p.version


def sync_registration_presentation(app_config: Dict[str, Any]) -> None:
    """
    Copy presentation into ``registration.metadata`` for proxy registration.

    ``metadata.description`` uses the **list** tier (brief). Help tier is for
    OpenAPI only.
    """
    pres = resolve_server_presentation(app_config)
    reg = app_config.setdefault("registration", {})
    if not isinstance(reg, dict):
        return

    meta = reg.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        reg["metadata"] = meta

    meta["description"] = pres.list_description
    meta["list_description"] = pres.list_description
    meta["help_description"] = pres.help_description
    meta["version"] = pres.version
    if reg.get("server_id"):
        meta.setdefault("server_id", reg["server_id"])
    if pres.title:
        meta.setdefault("server_name", pres.title)
        if not reg.get("server_name"):
            reg["server_name"] = pres.title

    reg["description"] = pres.list_description
    reg["version"] = pres.version
