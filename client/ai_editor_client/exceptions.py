"""Client-side errors (no dependency on ai_editor server package)."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ClientValidationError(ValueError):
    """Parameters do not match the command JSON schema (from server ``help``)."""

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.details = details or {}


class ServerVersionMismatch(RuntimeError):
    """The server on the other end is not the version this client declares.

    Raised before the command is dispatched, so nothing is executed against a
    server whose contract this client has not been built for. The rule is exact
    equality, never a compatible range: "the client number, the engine number
    and the server number must coincide."

    ``health`` and ``info`` are exempt and keep working across a mismatch --
    they are exactly the commands an operator uses to SEE a version mismatch,
    so failing them would remove the tool needed to diagnose the problem. See
    :mod:`ai_editor_client.server_version`.
    """

    def __init__(
        self,
        message: str,
        *,
        client_version: str,
        server_version: Optional[str],
        command: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.client_version = client_version
        self.server_version = server_version
        self.command = command
