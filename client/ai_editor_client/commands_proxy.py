"""
Dynamic command wrappers: schema from server ``help``, then local shallow validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

if TYPE_CHECKING:
    from ai_editor_client.client import CodeAnalysisAsyncClient


class ValidatedCommandsProxy:
    """``client.commands.<name>(**params)`` — fetch schema via ``help``, validate, ``execute_command``."""

    __slots__ = ("_client",)

    def __init__(self, client: CodeAnalysisAsyncClient) -> None:
        object.__setattr__(self, "_client", client)

    def clear_schema_cache(self) -> None:
        """Forget cached schemas (e.g. after server ``reload``)."""
        self._client.clear_command_schema_cache()

    async def fetch_schema(
        self, command: str, *, refresh: bool = False
    ) -> Dict[str, Any]:
        """Return input JSON schema for ``command`` (from server ``help``)."""
        return cast(
            Dict[str, Any],
            await self._client.get_command_schema(command, refresh=refresh),
        )

    async def invoke(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Merge ``params`` and ``kwargs``, validate against server schema, execute."""
        merged: Dict[str, Any] = dict(params or {})
        if kwargs:
            merged.update(kwargs)
        return cast(Dict[str, Any], await self._client.call_validated(command, merged))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        async def _bound(**kw: Any) -> Dict[str, Any]:
            return cast(Dict[str, Any], await self._client.call_validated(name, kw))

        _bound.__name__ = name
        _bound.__doc__ = (
            f"Validated call for command {name!r} (schema from server help)."
        )
        return _bound
