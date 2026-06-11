"""
Resolve OpenAPI / MCP server title, description, and version from config.

Adapter contract (mcp-proxy-adapter >= 8.10.13):
- ``AppFactory.create_app(title=..., description=..., version=...)`` → OpenAPI + ``help`` ``tool_info``.
- Proxy ``list_servers`` description: ``registration.metadata.description`` (see
  ``build_server_metadata`` in the adapter; same pattern as ``mcp_terminal`` /
  ``model_access_core``). Top-level ``registration.description`` is optional legacy
  for ``RegistrationClient`` only.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

_DEFAULT_TITLE = "AI Editor Server"

_DEFAULT_DESCRIPTION = """\
AI Editor server for Python projects: CST editing, code indexes, search, \
refactoring helpers, and quality checks.

### MCP Proxy (recommended)
- Discover servers: `list_servers`
- Discover projects: `list_projects` (use returned `project_id`)
- Call commands: `call_server(server_id="ai-editor-server", copy_number=1, command="<name>", params={...})`
- Use `project_id` and project-relative `file_path`; do not pass host `root_dir`.
- Long-running commands return `job_id`; poll with `queue_get_job_status` / `queue_get_job_logs`.

### Direct API
- Schema: `GET /openapi.json` (transport and mTLS per `config.json`)
"""


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("ai-editor")
    except Exception:
        return "1.0.4"


def resolve_server_presentation(app_config: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Build (title, description, version) for FastAPI and proxy registration.

    Priority:
    1. ``server_presentation`` section (recommended; survives SimpleConfig load)
    2. ``registration.server_name`` / ``registration.description`` / ``registration.version``
    3. Built-in defaults and package version
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
    description = (
        pres.get("description")
        or reg_meta.get("description")
        or reg.get("description")
        or _DEFAULT_DESCRIPTION
    )
    version = (
        pres.get("version")
        or reg_meta.get("version")
        or reg.get("version")
        or _package_version()
    )
    return str(title), str(description), str(version)


def sync_registration_presentation(app_config: Dict[str, Any]) -> None:
    """
    Copy presentation into ``registration.metadata`` for proxy registration.

    ``RegistrationConfig`` (SimpleConfig) only accepts ``metadata`` as an extra
    dict; ``description`` / ``version`` must live there for ``build_server_metadata``.
  """
    title, description, version = resolve_server_presentation(app_config)
    reg = app_config.setdefault("registration", {})
    if not isinstance(reg, dict):
        return

    meta = reg.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        reg["metadata"] = meta

    meta["description"] = description
    meta["version"] = version
    if reg.get("server_id"):
        meta.setdefault("server_id", reg["server_id"])
    if title:
        meta.setdefault("server_name", title)
        if not reg.get("server_name"):
            reg["server_name"] = title

    # Legacy path used by RegistrationClient._prepare_registration_data
    reg["description"] = description
    reg["version"] = version
