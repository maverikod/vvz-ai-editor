"""Probe script for universal_file_* lifecycle exercise."""

from __future__ import annotations

APP_NAME = "mcp_create_probe_v1"


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("probe"))


def farewell(name: str) -> str:
    """Return a farewell."""
    return f"Goodbye, {name}!"
