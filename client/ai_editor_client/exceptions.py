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
