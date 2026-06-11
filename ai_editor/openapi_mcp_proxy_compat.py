"""
Normalize OpenAPI 3.1 schemas for MCP Proxy command discovery.

The proxy's JsonRpcClient schema parser (mcp_proxy_adapter) expects ``type`` to be
a string. Pydantic/FastAPI can emit nullable unions as ``type: ["string", "null"]``,
which makes ``_map_type`` use the list as a dict key and raises
``TypeError: unhashable type: 'list'``, so registration fails with
"returned no commands via get_methods()".

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any


def normalize_openapi_types_for_mcp_proxy(obj: Any) -> Any:
    """
    Recursively rewrite ``type`` keys that are lists (nullable unions) to a single
    OpenAPI 3.0-style string (first non-``null`` entry, else ``string``).
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if key == "type" and isinstance(val, list):
                non_null = [x for x in val if x != "null"]
                out[key] = non_null[0] if non_null else "string"
            else:
                out[key] = normalize_openapi_types_for_mcp_proxy(val)
        return out
    if isinstance(obj, list):
        return [normalize_openapi_types_for_mcp_proxy(x) for x in obj]
    return obj


def patch_app_openapi_for_mcp_proxy(app: Any) -> None:
    """Wrap ``app.openapi`` so returned schema is safe for MCP Proxy get_methods()."""
    orig = app.openapi

    def _wrapped() -> Any:
        schema = orig()
        return normalize_openapi_types_for_mcp_proxy(schema)

    app.openapi = _wrapped
