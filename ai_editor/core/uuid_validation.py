"""
UUID4 validation helper for mutation targets and identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Optional


def is_valid_uuid4(value: Optional[str]) -> bool:
    """
    Return True if value is non-empty and valid UUID4 string; otherwise False.
    """
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    try:
        u = uuid.UUID(s, version=4)
        return str(u) == s
    except (ValueError, TypeError):
        return False
