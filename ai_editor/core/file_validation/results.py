"""
Shared validation result type for pre-write checks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of a single validation step."""

    success: bool
    error_message: str | None = None
    errors: list[str] = field(default_factory=list)
