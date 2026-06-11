"""
Pytest fixtures for AI Editor (file-editing server).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest


def pytest_configure(config) -> None:
    """Register custom marks."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration (slower, external services).",
    )
    config.addinivalue_line(
        "markers",
        "legacy_db: tests that required the removed local database stack.",
    )
