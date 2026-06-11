"""Sandbox test module."""

from __future__ import annotations


DEFAULT_TIMEOUT = 60


def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
